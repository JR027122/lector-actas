"""
Compara la extracción de un acta entre google/gemini-2.5-flash y
google/gemini-2.5-flash-lite (vía OpenRouter), para decidir qué modelo
usar por defecto en la app.

Uso:
    python scripts/comparar_modelos.py "ruta\\al\\acta.pdf"

Usa automáticamente la misma API key que ya tienes guardada para la app
(Administrador de credenciales de Windows o tu .env). No hace falta
pegarla de nuevo aquí.
"""

import base64
import json
import os
import sys
import time

# Para poder importar src.* al correr este script directamente desde scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from openai import OpenAI

from src.utils.secure_api_key import resolve_api_key

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

MODELOS = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
]

# Precios oficiales en OpenRouter, USD por 1M de tokens (input, output)
PRECIOS = {
    "google/gemini-2.5-flash": (0.30, 2.50),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
}

PROMPT = """
Eres un asistente experto en extracción de datos de actas técnicas de energía solar.
Analiza el documento adjunto y extrae la información solicitada.

Reglas estrictas:
1. Devuelve ÚNICAMENTE un objeto JSON válido, sin formato markdown y sin texto adicional.
2. Si no encuentras un dato o la celda está vacía, asigna el valor null.
3. Si el número de serie tiene notación científica o está cortado, intenta reconstruirlo basándote en el contexto, y agrégale el prefijo 'SR-'.
4. Limpia los nombres propios de basura (ej. si dice '~CEDULA' ignora ese símbolo).
5. Presta extrema atención a la diferencia entre números y letras (ej. el número 0 y la letra O) específicamente en Cédula, NIU y Seriales.
6. Transcribe las 'Observaciones' exactamente como están escritas, incluso si contienen errores ortográficos propios de la escritura a mano.
7. Busca la 'Observacion_General' en la última página del documento, suele ser un párrafo manuscrito importante.
8. MUY IMPORTANTE sobre el NIU: extráelo SOLO si aparece explícitamente en el documento con la etiqueta 'NIU' (suele ser un número de 6 a 10 dígitos). NUNCA uses como NIU el número del acta, el consecutivo del documento, la numeración de páginas ni ningún número del nombre del archivo. Si no hay un campo NIU visible y diligenciado, devuelve null.

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
    "Observacion_General": "texto completo de la observación al final del documento"
}
"""


def procesar(cliente, modelo, parte_archivo):
    inicio = time.time()
    response = cliente.chat.completions.create(
        model=modelo,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    parte_archivo,
                ],
            }
        ],
    )
    duracion = time.time() - inicio
    texto = (response.choices[0].message.content or "").strip()
    if texto.startswith("```json"):
        texto = texto[7:-3]
    elif texto.startswith("```"):
        texto = texto[3:-3]

    data = json.loads(texto)
    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0
    precio_in, precio_out = PRECIOS.get(modelo, (0, 0))
    costo = (tokens_in / 1_000_000) * precio_in + (tokens_out / 1_000_000) * precio_out

    return {
        "data": data,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "duracion_s": round(duracion, 1),
        "costo_usd": round(costo, 5),
    }


def main():
    if len(sys.argv) < 2:
        print('Uso: python scripts/comparar_modelos.py "ruta\\al\\acta.pdf"')
        sys.exit(1)

    archivo = sys.argv[1]
    if not os.path.exists(archivo):
        print(f"No se encontró el archivo: {archivo}")
        sys.exit(1)

    api_key = resolve_api_key()
    if not api_key:
        print("No se encontró ninguna API key de OpenRouter guardada. Configúrala primero en la app.")
        sys.exit(1)

    cliente = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    extension = os.path.splitext(archivo)[1].lower()
    mime = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
        extension.lstrip("."), "application/octet-stream"
    )
    with open(archivo, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    if extension == ".pdf":
        parte_archivo = {"type": "file", "file": {"filename": os.path.basename(archivo), "file_data": data_uri}}
    else:
        parte_archivo = {"type": "image_url", "image_url": {"url": data_uri}}

    resultados = {}
    for modelo in MODELOS:
        print(f"\nProcesando con {modelo}...")
        try:
            resultados[modelo] = procesar(cliente, modelo, parte_archivo)
        except Exception as e:
            resultados[modelo] = {"error": str(e)}
            print(f"  Error: {e}")

    # Comparación campo por campo
    print("\n" + "=" * 90)
    print(f"{'Campo':<28} | {'Flash':<28} | {'Flash Lite':<28}")
    print("=" * 90)
    campos = set()
    for modelo in MODELOS:
        if "data" in resultados.get(modelo, {}):
            campos.update(resultados[modelo]["data"].keys())
    for campo in sorted(campos):
        v_flash = str(resultados.get(MODELOS[0], {}).get("data", {}).get(campo, "—"))[:28]
        v_lite = str(resultados.get(MODELOS[1], {}).get("data", {}).get(campo, "—"))[:28]
        marca = "  <-- distinto" if v_flash != v_lite else ""
        print(f"{campo:<28} | {v_flash:<28} | {v_lite:<28}{marca}")

    print("\n" + "-" * 90)
    for modelo in MODELOS:
        r = resultados.get(modelo, {})
        if "error" in r:
            print(f"{modelo}: ERROR - {r['error']}")
        else:
            print(
                f"{modelo}: {r['tokens_in']} tokens entrada, {r['tokens_out']} salida, "
                f"${r['costo_usd']} este documento, {r['duracion_s']}s"
            )

    salida = os.path.join(os.path.dirname(archivo), "comparacion_modelos.json")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)
    print(f"\nDetalle completo guardado en: {salida}")


if __name__ == "__main__":
    main()
