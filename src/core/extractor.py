import re

def extract_all_entities(text):
    data = {}
    
    if not text:
        return data


    text_clean = text.upper()
    text_clean = re.sub(r'[\n\r]', ' ', text_clean)
    text_clean = re.sub(r'[~*#\-_:;]', ' ', text_clean)
    text_clean = text_clean.replace("Á", "A").replace("É", "E").replace("Í", "I").replace("Ó", "O").replace("Ú", "U")
    text_clean = re.sub(r'\s+', ' ', text_clean).strip()

    def buscar(patron):
        match = re.search(patron, text_clean)
        return match.group(1).strip() if match else None


    data["NIU"] = buscar(r'N[I1L]?\s*U\D*?(\d{5,10})')

    match_cedula = re.search(r'([A-Z\s]{5,40}?)\s+CEDULA\D*(\d{6,12})', text_clean)
    if match_cedula:
        nombre_crudo = match_cedula.group(1)

        nombre_limpio = re.split(r'(?:LONGITUD|COORDENADA|NOMBRE)\s*', nombre_crudo)[-1]
        data["Nombre_Usuario"] = nombre_limpio.strip()
        data["Cedula_Usuario"] = match_cedula.group(2)
        

    data["Municipio"] = buscar(r'MUNICIPIO\s+([A-Z\s]{3,20}?)\s+VERED')

    data["Vereda"] = buscar(r'VERED[AOA]?\s+([A-Z\s]{3,20}?)\s+FECHA')
    

    data["Fecha"] = buscar(r'FECHA\s+([A-Z0-9\s/]+?)\s+HORA')
    data["Hora"] = buscar(r'HORA\s+([0-9\.\s]+?)\s+CONDICION')
    data["Condicion_Climatica"] = buscar(r'CONDICION.*?([A-Z]{3,15})\s+(?:ESTADO|ADO|TADO)') 


    data["Panel_1_Serie"] = buscar(r'(?:SERIE|PANEL|FOTOVOLTAICO)\s*([A-Z0-9\s]{8,25}?)\s+(?:ESTADO|ADO|TADO) EQUIPO 1')
    data["Panel_1_Estado"] = buscar(r'(?:ESTADO|ADO|TADO) EQUIPO 1\s+([A-Z]{4,10})')

    data["Panel_2_Serie"] = buscar(r'(?:SERIE|PANEL)\s*([A-Z0-9\s]{8,25}?)\s+(?:ESTADO|ADO|TADO) EQUIPO 2')
    data["Panel_2_Estado"] = buscar(r'(?:ESTADO|ADO|TADO) EQUIPO 2\s+([A-Z]{4,10})')

    data["Panel_3_Serie"] = buscar(r'(?:SERIE|PANEL)\s*([A-Z0-9\s]{8,25}?)\s+(?:ESTADO|ADO|TADO) EQUIPO 3')
    data["Panel_3_Estado"] = buscar(r'(?:ESTADO|ADO|TADO) EQUIPO 3\s+([A-Z]{4,10})')


    data["Bateria_1_Serie"] = buscar(r'BATERIA 1\s*([A-Z0-9\s]{10,25}?)\s+(?:ESTADO|ADO|TADO) EQUIPO 4')
    data["Bateria_1_Estado"] = buscar(r'(?:ESTADO|ADO|TADO) EQUIPO 4\s+([A-Z]{4,10})')
    data["Bateria_1_Obs"] = buscar(r'EQUIPO 4\s+([A-Z\s]+?)\s+BATERIA 2')

    data["Bateria_2_Serie"] = buscar(r'BATERIA 2\s*([A-Z0-9\s]{10,25}?)\s+(?:ESTADO|ADO|TADO) EQUIPO 5')
    data["Bateria_2_Estado"] = buscar(r'(?:ESTADO|ADO|TADO) EQUIPO 5\s+([A-Z]{4,10})')
    data["Bateria_2_Obs"] = buscar(r'EQUIPO 5\s+([A-Z\s]+?)\s+(?:ESTADO|ADO|TADO) LIMPIEZA')

    data["Latitud"] = buscar(r'LATITUD\D*(-?\d+[\.,]\d+)')
    data["Longitud"] = buscar(r'LONGITUD\D*(-?\d+[\.,]\d+)')

    return data