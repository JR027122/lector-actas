import base64
import json
import os
import sys
import threading

from dotenv import load_dotenv
from openai import OpenAI

if getattr(sys, "frozen", False):
    # Carpeta del .exe: .env opcional junto al binario
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Carga .env desde la carpeta del ejecutable (empaquetado) o del proyecto (desarrollo)
ruta_env = os.path.join(base_dir, ".env")
load_dotenv(ruta_env)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# --- Cache de clientes OpenAI (reutilización de conexiones HTTP) ---
# El cliente OpenAI (httpx) mantiene un pool de conexiones y es thread-safe.
# Reutilizarlo evita el overhead de TLS handshake en cada llamada a la API.
_cliente_cache: dict[str, OpenAI] = {}
_cliente_lock = threading.Lock()


def _obtener_cliente(api_key: str) -> OpenAI:
    """Devuelve un cliente OpenAI reutilizable por API key (thread-safe)."""
    cliente = _cliente_cache.get(api_key)
    if cliente is not None:
        return cliente
    with _cliente_lock:
        # Doble verificación por si otro thread lo creó mientras esperábamos el lock.
        cliente = _cliente_cache.get(api_key)
        if cliente is not None:
            return cliente
        cliente = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        _cliente_cache[api_key] = cliente
        return cliente


def _resolve_openrouter_api_key():
    """Variable de entorno / .env primero; si no, almacén seguro del sistema."""
    from src.utils.secure_api_key import resolve_api_key

    return resolve_api_key()


# Modelos disponibles para que el usuario elija, con una etiqueta legible.
MODELOS_DISPONIBLES = {
    "google/gemini-2.5-flash": "Gemini 2.5 Flash (más preciso, recomendado)",
    "google/gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite (más económico)",
}

MODELO_POR_DEFECTO = "google/gemini-2.5-flash"

# Extensiones soportadas y su mime type
_MIME_POR_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _orden_modelos(modelo_elegido: str) -> list:
    """Modelo elegido primero; el resto queda como respaldo si ese deja de existir (404)."""
    if modelo_elegido not in MODELOS_DISPONIBLES:
        modelo_elegido = MODELO_POR_DEFECTO
    resto = [m for m in MODELOS_DISPONIBLES if m != modelo_elegido]
    return [modelo_elegido] + resto


def _sin_creditos(mensaje: str) -> bool:
    """True si el error indica que la key de OpenRouter se quedó sin crédito."""
    mensaje_low = mensaje.lower()
    return "402" in mensaje or "insufficient" in mensaje_low or "credit" in mensaje_low


def _normalizar_a_dict(parseado):
    """Asegura que el resultado del parseo sea un dict con los campos del acta.

    A veces el modelo (o la reparación automática de un JSON roto) envuelve
    el objeto en una lista, p. ej. [{...}] en vez de {...}. En ese caso se
    toma el primer elemento que sea un dict. Si no hay forma razonable de
    obtener un dict, se lanza un error claro en vez de dejar pasar una lista
    que rompería el resto del procesamiento (rename, Excel, etc.).
    """
    if isinstance(parseado, dict):
        return parseado

    if isinstance(parseado, list):
        for elemento in parseado:
            if isinstance(elemento, dict):
                return elemento
        raise ValueError(
            "La IA devolvió una lista sin ningún objeto JSON válido dentro."
        )

    raise ValueError(
        f"La IA devolvió un JSON de tipo inesperado ({type(parseado).__name__}), no un objeto."
    )


def _parsear_json(texto: str) -> dict:
    """Parsea el JSON que devuelve el modelo, con reparación automática.

    Es común que el modelo transcriba una observación manuscrita con una
    comilla suelta (p. ej. marcas de pulgadas, un apodo entre comillas) o un
    salto de línea sin escapar, lo que rompe el JSON estricto. En vez de
    perder todo el documento por un carácter, se intenta reparar el texto
    antes de rendirse.

    Siempre devuelve un dict (ver _normalizar_a_dict) o lanza ValueError.
    """
    try:
        return _normalizar_a_dict(json.loads(texto))
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        # Tolera caracteres de control literales (saltos de línea/tabs) dentro de strings.
        return _normalizar_a_dict(json.loads(texto, strict=False))
    except (json.JSONDecodeError, ValueError):
        pass

    from json_repair import repair_json

    reparado = repair_json(texto)
    return _normalizar_a_dict(json.loads(reparado))


def _codificar_archivo(ruta_archivo: str) -> dict:
    """Codifica el archivo en base64 y arma el content part que espera OpenRouter."""
    extension = os.path.splitext(ruta_archivo)[1].lower()
    mime = _MIME_POR_EXTENSION.get(extension, "application/octet-stream")

    with open(ruta_archivo, "rb") as f:
        contenido_b64 = base64.b64encode(f.read()).decode("ascii")

    data_uri = f"data:{mime};base64,{contenido_b64}"

    if extension == ".pdf":
        return {
            "type": "file",
            "file": {
                "filename": os.path.basename(ruta_archivo),
                "file_data": data_uri,
            },
        }

    return {"type": "image_url", "image_url": {"url": data_uri}}


_PROMPT_COMPLETO = """
        Eres un asistente experto en extracción de datos de actas técnicas de energía solar.
        Analiza el documento adjunto y extrae la información solicitada.

        Reglas estrictas:
        1. Devuelve ÚNICAMENTE un objeto JSON válido, sin formato markdown y sin texto adicional.
        2. Si no encuentras un dato o la celda está vacía, asigna el valor null.
        3. Si el número de serie tiene notación científica o está cortado, intenta reconstruirlo basándote en el contexto, y agrégale el prefijo 'SR-'.
        4. Limpia los nombres propios de basura (ej. si dice '~CEDULA' ignora ese símbolo).
        5. Presta extrema atención a la diferencia entre números y letras (ej. el número 0 y la letra O) específicamente en Cédula, NIU y Seriales.
        6. Transcribe las 'Observaciones' exactamente como están escritas, incluso si contienen errores ortográficos propios de la escritura a mano.
        7. MUY IMPORTANTE sobre 'Observacion_General': busca el campo etiquetado literalmente 'Observaciones:' (suele estar en la última página o junto a las firmas, con texto MANUSCRITO por el técnico). Transcribe únicamente ese texto manuscrito. NUNCA uses como observación el texto impreso de secciones como 'CONTRATO DE CONDICIONES UNIFORMES', 'CUADRO DE CARGAS' ni ningún otro texto legal o impreso del formato — eso NO es una observación. La observación general es SIEMPRE un texto escrito a mano, nunca texto impreso del formulario.
        8. MUY IMPORTANTE sobre el NIU: extráelo SOLO si aparece explícitamente en el documento con la etiqueta 'NIU' (suele ser un número de 6 a 10 dígitos). NUNCA uses como NIU el número del acta, el consecutivo del documento, la numeración de páginas ni ningún número del nombre del archivo. Si no hay un campo NIU visible y diligenciado, devuelve null.
        9. Sistema_Activo: busca el checkbox '¿Operativo el sistema?' que suele estar en la primera página. Devuelve 'Sí' o 'No' según esté marcado. Si no encuentras el campo, devuelve null.

        Estructura JSON requerida:
        {
            "NIU": "número",
            "Nombre_Usuario": "nombre completo limpio",
            "Cedula_Usuario": "solo números",
            "Municipio": "nombre",
            "Vereda": "nombre",
            "Fecha": "fecha",
            "Hora": "hora",
            "Condicion_Climatica": "clima",
            "Sistema_Activo": "Sí o No",
            "Panel_1_Serie": "SR-número",
            "Panel_1_Estado": "estado",
            "Panel_1_Obs": "observación",
            "Panel_2_Serie": "SR-número",
            "Panel_2_Estado": "estado",
            "Panel_2_Obs": "observación",
            "Panel_3_Serie": "SR-número",
            "Panel_3_Estado": "estado",
            "Panel_3_Obs": "observación",
            "Bateria_1_Serie": "SR-número",
            "Bateria_1_Estado": "estado",
            "Bateria_1_Obs": "observación",
            "Bateria_2_Serie": "SR-número",
            "Bateria_2_Estado": "estado",
            "Bateria_2_Obs": "observación",
            "Controlador_Serie": "SR-número",
            "Controlador_Estado": "estado",
            "Controlador_Obs": "observación",
            "Inversor_Serie": "SR-número",
            "Inversor_Estado": "estado",
            "Inversor_Obs": "observación",
            "Medidor_Serie": "SR-número",
            "Medidor_Estado": "estado",
            "Medidor_Obs": "observación",
            "Corriente_Entrada_Bateria": "medición numérica",
            "Corriente_Salida_Bateria": "medición numérica",
            "Voltaje_Toma_1": "medición numérica",
            "Voltaje_Toma_2": "medición numérica",
            "Voltaje_Toma_3": "medición numérica",
            "Voltaje_Toma_4": "medición numérica",
            "Voltaje_Tierra_Neutro": "medición numérica",
            "Latitud": "coordenada",
            "Longitud": "coordenada",
            "Observacion_General": "texto manuscrito bajo el label 'Observaciones:' (NO texto impreso del formulario)"
        }
        """

# Solo lo necesario para renombrar a NIU_dd-mm-aaaa_acta (mucho más rápido).
_PROMPT_RENOMBRE = """
        Eres un asistente experto en lectura de actas técnicas de energía solar.
        Tu ÚNICO objetivo es obtener los datos para renombrar el archivo.
        Analiza la portada / primera página del documento adjunto.

        Reglas estrictas:
        1. Devuelve ÚNICAMENTE un objeto JSON válido, sin markdown ni texto adicional.
        2. Si no encuentras un dato, usa null.
        3. Fecha: busca el campo Fecha del acta (suele estar arriba o en el encabezado).
           Devuélvela preferiblemente como dd-mm-aaaa o dd/mm/aaaa. No inventes el mes ni el año.
        4. NIU: extráelo SOLO si aparece con la etiqueta 'NIU' en el documento
           (número de 6 a 10 dígitos). NUNCA uses el número del acta, consecutivos,
           páginas ni números del nombre del archivo. Si no hay NIU visible, null.
        5. Nombre_Usuario y Cedula_Usuario: extráelos si están visibles (sirven de respaldo
           para completar el NIU con la base de usuarios). Limpia basura del nombre;
           cédula solo números. Distingue 0/O y 1/I/l.
        6. NO extraigas paneles, baterías, mediciones, coordenadas ni observaciones.

        Estructura JSON requerida:
        {
            "NIU": "número o null",
            "Fecha": "dd-mm-aaaa o null",
            "Nombre_Usuario": "nombre completo limpio o null",
            "Cedula_Usuario": "solo números o null"
        }
        """


def extract_data_with_ai(file_path, filename, api_key=None, modelo=None, solo_renombre=False):
    """Extrae los datos del acta usando un modelo de OpenRouter (por defecto Gemini).

    Usa la API de OpenRouter (compatible con OpenAI), que no tiene una API de
    archivos propia como la de Google, así que el documento se envía
    codificado en base64 dentro del mensaje.

    modelo: slug de OpenRouter elegido por el usuario (ver MODELOS_DISPONIBLES).
    Si no se indica, o ya no existe (404), se usa MODELO_POR_DEFECTO / el
    siguiente modelo disponible.

    solo_renombre: si True, usa prompt corto y solo la 1ª página del PDF
    (mucho más rápido; basta para NIU + Fecha).
    """
    modo = "renombre rápido" if solo_renombre else "OCR completo"
    print(f"Procesando {filename} con OpenRouter ({modo})...")

    ruta_subida = file_path
    es_temporal = False
    try:
        api_key_segura = (api_key or "").strip() or _resolve_openrouter_api_key()
        if not api_key_segura:
            return {
                "Archivo": filename,
                "Error": (
                    "No hay API key de OpenRouter. Configúrala en la aplicación "
                    f"o crea un archivo .env en: {ruta_env}"
                ),
            }

        cliente = _obtener_cliente(api_key_segura)

        # Los PDFs muy pesados (registros fotográficos escaneados) conviene
        # comprimirlos antes de codificarlos en base64.
        # En renombre solo se envía la 1ª página (NIU/Fecha suelen estar ahí).
        from src.utils.pdf_compressor import preparar_para_envio

        ruta_subida, es_temporal = preparar_para_envio(
            file_path, solo_primera_pagina=solo_renombre
        )

        parte_archivo = _codificar_archivo(ruta_subida)
        prompt = _PROMPT_RENOMBRE if solo_renombre else _PROMPT_COMPLETO

        # Generar con el modelo elegido por el usuario; si ya no existe (404),
        # pasar al siguiente de la lista de respaldo.
        orden_modelos = _orden_modelos(modelo)
        indice = 0
        response = None
        while True:
            modelo_actual = orden_modelos[indice]
            try:
                response = cliente.chat.completions.create(
                    model=modelo_actual,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                parte_archivo,
                            ],
                        }
                    ],
                )
                break
            except Exception as e:
                mensaje_error = str(e)
                hay_siguiente = indice < len(orden_modelos) - 1
                if "404" in mensaje_error and hay_siguiente:
                    indice += 1
                    print(
                        f"El modelo '{modelo_actual}' ya no está disponible en OpenRouter. "
                        f"Cambiando al modelo '{orden_modelos[indice]}'..."
                    )
                    continue
                if "response_format" in mensaje_error.lower():
                    # Algunos modelos/proveedores no aceptan json_object: reintentar sin él.
                    response = cliente.chat.completions.create(
                        model=modelo_actual,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    parte_archivo,
                                ],
                            }
                        ],
                    )
                    break
                raise

        response_text = (response.choices[0].message.content or "").strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:-3]
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
        response_text = response_text.strip()

        data = _parsear_json(response_text)
        data["Archivo"] = filename

        return data

    except Exception as e:
        mensaje = str(e)
        print(f"Error procesando con OpenRouter: {mensaje}")
        resultado = {"Archivo": filename, "Error": mensaje}
        if "429" in mensaje:
            resultado["__retry_s__"] = 30
        if _sin_creditos(mensaje):
            resultado["__sin_creditos__"] = True
        return resultado
    finally:
        # Borrar la copia comprimida temporal si se creó
        if es_temporal and ruta_subida != file_path and os.path.exists(ruta_subida):
            os.remove(ruta_subida)
