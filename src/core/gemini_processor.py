from google import genai
import json
import os
import sys
import re
from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    # Carpeta del .exe: .env opcional junto al binario
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Carga .env desde la carpeta del ejecutable (empaquetado) o del proyecto (desarrollo)
ruta_env = os.path.join(base_dir, ".env")
load_dotenv(ruta_env)


def _resolve_gemini_api_key():
    """Variable de entorno / .env primero; si no, almacén seguro del sistema."""
    from src.utils.secure_api_key import resolve_api_key

    return resolve_api_key()


def extract_data_with_gemini(file_path, filename, api_key=None):
    print(f"🚀 Procesando {filename} con Gemini...")
    
    try:
        api_key_segura = (api_key or "").strip() or _resolve_gemini_api_key()
        if not api_key_segura:
            return {
                "Archivo": filename,
                "Error": (
                    "⚠️ No hay API key de Gemini. Configúrala en la aplicación "
                    f"o crea un archivo .env en: {ruta_env}"
                ),
            }
            
        cliente = genai.Client(api_key=api_key_segura)

        uploaded_file = cliente.files.upload(file=file_path)
        
        prompt = """
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
        
        response = cliente.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=[uploaded_file, prompt]
        )
        
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:-3] 
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
            
        data = json.loads(response_text)
        data["Archivo"] = filename
        
        cliente.files.delete(name=uploaded_file.name)
        
        return data

    except Exception as e:
        print(f"❌ Error procesando con Gemini: {e}")
        return {"Archivo": filename, "Error": str(e)}