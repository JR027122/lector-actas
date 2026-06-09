import os
import time

from src.core.gemini_processor import extract_data_with_gemini
from src.core.processing_modes import OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.file_renamer import construir_nuevo_nombre, renombrar_archivo as renombrar_en_disco


def nombre_sugerido(data: dict, nombre_original: str) -> str | None:
    """Devuelve el nombre sugerido para descarga web (sin renombrar en disco)."""
    _, extension = os.path.splitext(nombre_original)
    return construir_nuevo_nombre(data.get("NIU"), data.get("Fecha"), extension)


def process_document(
    file_path: str,
    filename: str,
    mode: str = OCR_AND_RENAME,
    api_key: str | None = None,
) -> dict:
    """Procesa un documento según el modo seleccionado."""
    data = extract_data_with_gemini(file_path, filename, api_key=api_key)

    if "Error" in data:
        return data

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
) -> list:
    """Procesa una carpeta completa con reintentos ante límites de la API."""
    resultados = []

    if not os.path.exists(folder_path):
        print(f"Error: La carpeta '{folder_path}' no existe.")
        return resultados

    archivos = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith((".pdf", ".jpg", ".png", ".jpeg"))
    ]
    total_archivos = len(archivos)

    if total_archivos == 0:
        return resultados

    for i, filename in enumerate(archivos):
        file_path = os.path.join(folder_path, filename)
        exito = False
        intentos = 0

        while not exito and intentos < 3:
            data = process_document(file_path, filename, mode, api_key=api_key)

            if "Error" in data and (
                "429" in str(data["Error"]) or "503" in str(data["Error"])
            ):
                print(
                    f"⚠️ Servidor ocupado o límite alcanzado. "
                    f"Esperando 60 s para reanudar {filename}..."
                )
                time.sleep(60)
                intentos += 1
                continue

            resultados.append(data)
            exito = True

            if progress_callback:
                progress_callback(i + 1, total_archivos, filename)

            if i < total_archivos - 1:
                time.sleep(4)

    return resultados
