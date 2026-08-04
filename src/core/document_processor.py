import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from src.core.openrouter_processor import extract_data_with_ai
from src.core.processing_modes import (
    OCR_AND_RENAME,
    RENAME_ONLY,
    exporta_excel,
    renombra_archivo,
)
from src.utils.file_renamer import construir_nuevo_nombre, renombrar_archivo as renombrar_en_disco
from src.utils.niu_lookup import completar_niu
from src.utils.post_procesado import post_procesar
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.progress_tracker import ProgressTracker

# Número de archivos que se procesan en paralelo.
# Las llamadas a OpenRouter son I/O-bound (espera de red), así que múltiples
# hilos pueden esperar respuestas simultáneamente sin saturar la CPU.
# 3 es un balance entre velocidad y respeto a los límites de rate de la API.
_MAX_WORKERS_DEFAULT = 3


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

    En modo Solo renombrar se usa extracción rápida (1ª página + prompt corto).
    """
    solo_renombre = mode == RENAME_ONLY
    data = extract_data_with_ai(
        file_path, filename, api_key=api_key, modelo=modelo, solo_renombre=solo_renombre
    )

    if "Error" in data:
        return data

    # El post-procesado (ortografía de estados/obs y detección de filas
    # inventadas) solo aplica al OCR completo; en renombre no hay equipos.
    if not solo_renombre:
        data = post_procesar(data)

    # Completar NIU: primero desde el nombre del archivo original, y si no,
    # desde la base de usuarios (cédula/nombre), cuando el OCR no lo encontró
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
    max_workers: int = _MAX_WORKERS_DEFAULT,
) -> list:
    """Procesa una carpeta completa con reintentos ante límites de la API.

    Procesa varios archivos en paralelo (ThreadPoolExecutor) para aprovechar
    el tiempo de espera de red de cada llamada a OpenRouter.  Esto reduce
    drásticamente el tiempo total en lotes grandes sin afectar la precisión:
    los prompts, modelos y post-procesado son idénticos al flujo secuencial.

    quota_callback: función sin argumentos que se invoca cuando la API key
    de OpenRouter se queda sin créditos. Si devuelve una nueva API key,
    el procesamiento se reanuda con ella; si devuelve None, se detiene.
    modelo: slug de OpenRouter elegido por el usuario (ver openrouter_processor.MODELOS_DISPONIBLES).
    progress_tracker: ProgressTracker para guardar progreso y permitir reanudación.
    excel_callback: función(resultados_acumulados, ruta_carpeta) que actualiza el Excel incrementalmente.
    max_workers: número de archivos que se procesan simultáneamente.
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

    # --- Estado compartido entre hilos ---
    lock = threading.Lock()          # Protege resultados, completed_count, excel
    api_key_lock = threading.Lock()   # Protege api_key_shared
    quota_lock = threading.Lock()     # Garantiza que solo un hilo invoque quota_callback
    stop_event = threading.Event()    # Detiene los hilos pendientes si no hay créditos

    # Variables mutables compartidas (listas de 1 elemento para closures)
    api_key_shared = [api_key]
    cuota_agotada = [False]
    quota_triggered = [False]
    completed_count = [0]

    def procesar_uno(filename: str) -> dict:
        """Procesa un archivo con reintentos. Pensada para ejecutarse en un hilo."""
        if stop_event.is_set():
            return {
                "Archivo": filename,
                "Error": "No procesado: la API key de OpenRouter se quedó sin créditos.",
            }

        file_path = os.path.join(folder_path, filename)

        intentos = 0
        while intentos < 4:
            if stop_event.is_set():
                return {
                    "Archivo": filename,
                    "Error": "No procesado: la API key de OpenRouter se quedó sin créditos.",
                }

            with api_key_lock:
                current_api_key = api_key_shared[0]

            data = process_document(
                file_path, filename, mode,
                api_key=current_api_key, user_db=user_db, modelo=modelo,
            )
            error = str(data.get("Error", ""))

            if not error:
                break

            # Sin créditos en la cuenta de OpenRouter: esperar no sirve.
            if data.get("__sin_creditos__"):
                with quota_lock:
                    # Si la key ya fue actualizada por otro hilo, reintentar
                    if current_api_key != api_key_shared[0]:
                        continue
                    # Solo un hilo invoca el quota_callback
                    if not quota_triggered[0]:
                        quota_triggered[0] = True
                        print(
                            "La API key de OpenRouter se quedó sin créditos. "
                            "Proceso en pausa..."
                        )
                        nueva_key = quota_callback() if quota_callback else None
                        if nueva_key:
                            with api_key_lock:
                                api_key_shared[0] = nueva_key
                            quota_triggered[0] = False
                            print("API key cambiada. Reanudando el procesamiento...")
                            continue
                        else:
                            cuota_agotada[0] = True
                            stop_event.set()
                            data["Error"] = (
                                "La API key de OpenRouter se quedó sin créditos. "
                                "Recárgala o usa otra API key."
                            )
                            print(data["Error"])
                return data

            # Límite por minuto (429) o servidor ocupado (503): backoff y reintentar
            if "429" in error or "503" in error:
                intentos += 1
                if intentos >= 4:
                    break
                espera = data.get("__retry_s__") or 30
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

        # --- Registrar resultado (thread-safe) ---
        with lock:
            resultados.append(data)
            completed_count[0] += 1
            current = completed_count[0]

            if progress_tracker and not data.get("Error"):
                progress_tracker.register_processed_file(filename)

            if excel_callback and exporta_excel(mode) and not data.get("Error"):
                registros_limpios = [limpiar_registro(r) for r in resultados if not r.get("Error")]
                excel_callback(registros_limpios, folder_path)

        if progress_callback:
            progress_callback(current, total_archivos, filename)

        return data

    # --- Procesar concurrentemente ---
    workers = min(max_workers, total_archivos)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(procesar_uno, f): f for f in archivos}
        for future in as_completed(futures):
            filename = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Error inesperado procesando {filename}: {e}")
                with lock:
                    resultados.append({"Archivo": filename, "Error": str(e)})
                    completed_count[0] += 1
                    current = completed_count[0]
                if progress_callback:
                    progress_callback(current, total_archivos, filename)

    # Limpiar checkpoint si se completó exitosamente
    if progress_tracker and not cuota_agotada[0] and total_archivos > 0:
        progress_tracker.delete()

    return resultados
