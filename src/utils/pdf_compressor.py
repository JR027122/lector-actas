"""
Compresión de PDFs pesados antes de enviarlos codificados en base64 a OpenRouter
(el modelo detrás es Gemini, con límite práctico de 50 MB por documento).

Los registros fotográficos escaneados suelen superar el límite; aquí se
re-renderizan las páginas como JPEG con calidad decreciente hasta que el
archivo quede por debajo del umbral.
"""

import os
import tempfile

import fitz  # PyMuPDF

# Límite práctico para el envío (50 MB); margen de seguridad
MAX_PDF_BYTES = 48 * 1024 * 1024

# Intentos de compresión: (escala de render, calidad JPEG)
_NIVELES = [
    (2.0, 75),
    (1.5, 70),
    (1.5, 55),
    (1.0, 60),
    (1.0, 45),
]


def necesita_compresion(file_path: str) -> bool:
    return (
        file_path.lower().endswith(".pdf")
        and os.path.getsize(file_path) > MAX_PDF_BYTES
    )


def comprimir_pdf(file_path: str) -> str:
    """Comprime un PDF re-renderizando sus páginas como JPEG.

    Devuelve la ruta de un PDF temporal por debajo del límite.
    Lanza RuntimeError si ni el nivel más agresivo lo logra.
    El llamador es responsable de borrar el archivo temporal.
    """
    documento = fitz.open(file_path)
    try:
        for escala, calidad in _NIVELES:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(tmp_fd)

            salida = fitz.open()
            try:
                for pagina in documento:
                    pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala))
                    img_bytes = pix.tobytes("jpeg", jpg_quality=calidad)
                    nueva = salida.new_page(width=pagina.rect.width, height=pagina.rect.height)
                    nueva.insert_image(nueva.rect, stream=img_bytes)
                salida.save(tmp_path, garbage=4, deflate=True)
            finally:
                salida.close()

            tamano = os.path.getsize(tmp_path)
            if tamano <= MAX_PDF_BYTES:
                print(
                    f"PDF comprimido: {os.path.getsize(file_path) / 1e6:.1f} MB "
                    f"-> {tamano / 1e6:.1f} MB (escala {escala}, calidad {calidad})"
                )
                return tmp_path

            os.remove(tmp_path)

        raise RuntimeError(
            "No se pudo comprimir el PDF por debajo de 50 MB; "
            "divídelo en partes más pequeñas."
        )
    finally:
        documento.close()


def extraer_primera_pagina(file_path: str) -> tuple[str, bool]:
    """Extrae solo la primera página de un PDF a un archivo temporal.

    Para renombre basta con NIU y Fecha, que suelen estar en la portada.
    Enviar 1 página en vez del PDF completo (a veces 10+ páginas escaneadas)
    reduce mucho el tiempo y el costo de la API.

    Devuelve (ruta, es_temporal). Si no es PDF o falla, devuelve el original.
    """
    if not file_path.lower().endswith(".pdf"):
        return file_path, False

    try:
        documento = fitz.open(file_path)
    except Exception as e:
        print(f"No se pudo abrir el PDF para extraer la 1ª página: {e}")
        return file_path, False

    try:
        if documento.page_count <= 1:
            return file_path, False

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(tmp_fd)

        salida = fitz.open()
        try:
            salida.insert_pdf(documento, from_page=0, to_page=0)
            salida.save(tmp_path, garbage=4, deflate=True)
        finally:
            salida.close()

        print(
            f"Renombre rápido: enviando solo 1ª página "
            f"(de {documento.page_count}) de {os.path.basename(file_path)}"
        )
        return tmp_path, True
    except Exception as e:
        print(f"No se pudo extraer la 1ª página: {e}")
        return file_path, False
    finally:
        documento.close()


def preparar_para_envio(file_path: str, solo_primera_pagina: bool = False) -> tuple[str, bool]:
    """Devuelve (ruta_a_subir, es_temporal).

    Si solo_primera_pagina=True (modo renombre), reduce el PDF a la portada.
    Si el PDF supera el límite práctico, devuelve una copia comprimida temporal.
    """
    if solo_primera_pagina and file_path.lower().endswith(".pdf"):
        ruta, es_temp = extraer_primera_pagina(file_path)
        # Si la 1ª página sigue pesando (poco habitual), comprimirla
        if necesita_compresion(ruta):
            comprimido = comprimir_pdf(ruta)
            if es_temp and os.path.exists(ruta):
                os.remove(ruta)
            return comprimido, True
        return ruta, es_temp

    if necesita_compresion(file_path):
        return comprimir_pdf(file_path), True
    return file_path, False
