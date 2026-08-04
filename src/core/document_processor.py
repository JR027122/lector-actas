import os
import threading
import time
import pandas as pd

from src.core.openrouter_processor import extract_data_with_ai
from src.core.processing_modes import OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.file_renamer import construir_nuevo_nombre, renombrar_archivo as renombrar_en_disco
from src.utils.niu_lookup import completar_niu
from src.utils.post_procesado import post_procesar
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.progress_tracker import ProgressTracker


class ProcessControl:
    """Control cooperativo de pausa/detención para el procesamiento por lotes.

    El hilo de la interfaz llama a pausar()/reanudar()/detener(); el bucle de
    procesamiento llama a punto_de_control() entre archivos: ese método bloquea
    mientras esté en pausa y devuelve False si se pidió detener (para salir del
    bucle conservando lo ya procesado).
    """

    def __init__(self):
        self._detener = threading.Event()
        # "Continuar" arranca activo (procesando). Al pausar se limpia, lo que
        # bloquea el bucle en punto_de_control() hasta reanudar o detener.
        self._continuar = threading.Event()
        self._continuar.set()

    def pausar(self):
        if not self._detener.is_set():
            self._continuar.clear()

    def reanudar(self):
        self._continuar.set()

    def detener(self):
        self._detener.set()
        # Desbloquear el bucle si estaba esperando en pausa.
        self._continuar.set()

    @property
    def pausado(self) -> bool:
        return not self._continuar.is_set() and not self._detener.is_set()

    @property
    def detenido(self) -> bool:
        return self._detener.is_set()

    def punto_de_control(self) -> bool:
        """Bloquea mientras esté en pausa. Devuelve False si se pidió detener."""
        self._continuar.wait()
        return not self._detener.is_set()


def nombre_sugerido(data: dict, nombre_original: str) -> str | None:
    """Devuelve el nombre sugerido para descarga web (sin renombrar en disco)."""
    _, extension = os.path.splitext(nombre_original)
    return construir_nuevo_nombre(data.get("NIU"), data.get("Fecha"), extension)


def process_document(
    file_path: str,
    filename: str,
    mode: str = OCR_AND_RENAME,
    api_key: str | None = None,
    user_db=None,
    modelo: str | None = None,
) -> dict:
    """Procesa un documento según el modo seleccionado.

    user_db: base de usuarios opcional (src.utils.niu_lookup.UserDatabase)
    para completar el NIU por cédula o nombre cuando no aparece en el documento.
    modelo: slug de OpenRouter elegido por el usuario (ver openrouter_processor.MODELOS_DISPONIBLES).
    """
    data = extract_data_with_ai(file_path, filename, api_key=api_key, modelo=modelo)

    if "Error" in data:
        return data

    # Corregir ortografía de vocabulario cerrado y detectar filas
    # sospechosas (posibles datos inventados por el modelo)
    data = post_procesar(data)

    # Completar NIU: primero desde el nombre del archivo original; si no,
    # desde el propio acta (validando el rango); y como último recurso, desde
    # la base de usuarios (cédula/nombre).
    data = completar_niu(data, user_db, nombre_archivo=filename)

    if renombra_archivo(mode):
        nueva_ruta = renombrar_en_disco(file_path, data)
        if nueva_ruta != file_path:
            data["Archivo"] = os.path.basename(nueva_ruta)
            data["__ruta_actualizada__"] = nueva_ruta
            data["__renombrado__"] = True
        else:
            data["__renombrado__"] = False
            sugerido = nombre_sugerido(data, filename)
            if sugerido and sugerido.lower() != filename.lower():
                data["__nombre_sugerido__"] = sugerido

    if exporta_excel(mode):
        data["__incluir_excel__"] = True
    else:
        data["__incluir_excel__"] = False

    return data


def process_folder(
    folder_path: str,
    mode: str = OCR_AND_RENAME,
    progress_callback=None,
    api_key: str | None = None,
    user_db=None,
    quota_callback=None,
    modelo: str | None = None,
    progress_tracker: ProgressTracker | None = None,
    excel_callback=None,
    control: "ProcessControl | None" = None,
) -> list:
    """Procesa una carpeta completa con reintentos ante límites de la API.

    quota_callback: función sin argumentos que se invoca cuando la API key
    de OpenRouter se queda sin créditos. Si devuelve una nueva API key,
    el procesamiento se reanuda con ella; si devuelve None, se detiene.
    modelo: slug de OpenRouter elegido por el usuario (ver openrouter_processor.MODELOS_DISPONIBLES).
    progress_tracker: ProgressTracker para guardar progreso y permitir reanudación.
    excel_callback: función(resultados_acumulados, ruta_carpeta) que actualiza el Excel incrementalmente.
    control: ProcessControl opcional para pausar/detener el lote desde la UI.
    Al detener, se sale conservando lo procesado y sin borrar el checkpoint,
    de modo que el lote pueda reanudarse después.
    """
    resultados = []

    if not os.path.exists(folder_path):
        print(f"Error: La carpeta '{folder_path}' no existe.")
        return resultados

    archivos = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith((".pdf", ".jpg", ".png", ".jpeg"))
    ]

    # Filtrar archivos ya procesados si hay checkpoint anterior
    if progress_tracker:
        procesados = progress_tracker.get_processed_files()
        archivos = [f for f in archivos if f not in procesados]
        if procesados:
            print(f"Reanudando desde {len(procesados)} archivos procesados.")

    total_archivos = len(archivos)

    if total_archivos == 0:
        # Si no hay archivos nuevos y hay tracker, limpiar
        if progress_tracker and progress_tracker.has_previous_progress():
            progress_tracker.delete()
        return resultados

    cuota_diaria_agotada = False
    detenido_por_usuario = False

    for i, filename in enumerate(archivos):
        # Pausa / detención cooperativa solicitada desde la UI. punto_de_control
        # bloquea mientras esté en pausa y devuelve False si se pidió detener.
        if control is not None and not control.punto_de_control():
            detenido_por_usuario = True
            break

        file_path = os.path.join(folder_path, filename)

        if cuota_diaria_agotada:
            resultados.append({
                "Archivo": filename,
                "Error": "No procesado: la API key de OpenRouter se quedó sin créditos.",
            })
            if progress_callback:
                progress_callback(i + 1, total_archivos, filename)
            continue

        data = None
        intentos = 0
        while intentos < 4:
            data = process_document(file_path, filename, mode, api_key=api_key, user_db=user_db, modelo=modelo)
            error = str(data.get("Error", ""))

            if not error:
                break

            # Sin créditos en la cuenta de OpenRouter: esperar no sirve.
            # Se pausa y se pregunta si hay otra API key.
            # (No cuenta como intento: la pausa puede durar lo que el usuario quiera.)
            if data.get("__sin_creditos__"):
                print(
                    "La API key de OpenRouter se quedó sin créditos. "
                    "Proceso en pausa..."
                )
                nueva_key = quota_callback() if quota_callback else None
                if nueva_key:
                    api_key = nueva_key
                    print("API key cambiada. Reanudando el procesamiento...")
                    continue
                cuota_diaria_agotada = True
                data["Error"] = (
                    "La API key de OpenRouter se quedó sin créditos. "
                    "Recárgala o usa otra API key."
                )
                print(data["Error"])
                break

            # Límite por minuto (429) o servidor ocupado (503): esperar y reintentar
            if "429" in error or "503" in error:
                intentos += 1
                if intentos >= 4:
                    break
                espera = data.get("__retry_s__") or 60
                espera = max(espera, 15)
                print(
                    f"Servidor ocupado o límite por minuto alcanzado. "
                    f"Esperando {espera} s para reanudar {filename}... "
                    f"(intento {intentos}/4)"
                )
                time.sleep(espera)
                continue

            # Otro tipo de error: no tiene sentido reintentar
            break

        resultados.append(data)

        # Registrar progreso y actualizar Excel si se solicita
        if progress_tracker and not data.get("Error"):
            progress_tracker.register_processed_file(filename)
            # Si se proporciona callback para actualizar Excel, hacerlo incrementalmente
            if excel_callback and exporta_excel(mode):
                registros_limpios = [limpiar_registro(r) for r in resultados if not r.get("Error")]
                excel_callback(registros_limpios, folder_path)

        if progress_callback:
            progress_callback(i + 1, total_archivos, filename)

        if i < total_archivos - 1 and not cuota_diaria_agotada:
            time.sleep(4)

    # Limpiar checkpoint solo si se completó todo el lote. Si el usuario detuvo
    # o se agotó la cuota, se conserva para poder reanudar más tarde.
    if (
        progress_tracker
        and not cuota_diaria_agotada
        and not detenido_por_usuario
        and total_archivos > 0
    ):
        progress_tracker.delete()

    return resultados
