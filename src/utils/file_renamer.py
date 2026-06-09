import os
import re
from datetime import datetime


# Caracteres no permitidos en nombres de archivo en Windows: < > : " / \ | ? *
_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Meses en español para fechas tipo "12 de mayo de 2026"
_MESES_ES = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "setiembre": 9, "sept": 9, "sep": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}


def _sanitizar_componente(valor):
    """Limpia un valor para que sea seguro como parte de un nombre de archivo."""
    if valor is None:
        return ""

    texto = str(valor).strip()
    if not texto or texto.lower() in ("null", "none", "nan"):
        return ""

    # Reemplaza caracteres inválidos por guion
    texto = _INVALID_CHARS_RE.sub("-", texto)
    # Convierte separadores de fecha y espacios en guiones
    texto = re.sub(r"[\s/\\.]+", "-", texto)
    # Colapsa guiones repetidos
    texto = re.sub(r"-+", "-", texto)
    # Quita guiones, puntos y espacios al inicio/fin (Windows no acepta puntos finales)
    texto = texto.strip("-. ")

    return texto


def _normalizar_fecha(fecha):
    """Convierte cualquier fecha reconocible al formato dd-mm-aaaa.

    Si no logra interpretarla, devuelve la fecha sanitizada como fallback
    para no perder la posibilidad de renombrar el archivo.
    """
    if fecha is None:
        return ""

    texto = str(fecha).strip()
    if not texto or texto.lower() in ("null", "none", "nan"):
        return ""

    # Quitar acentos básicos para que "Mayo" / "máyo" matcheen igual
    texto_norm = (
        texto.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u")
    )

    # Caso "12 de mayo de 2026" / "12 mayo 2026"
    match_es = re.search(
        r"(\d{1,2})\s*(?:de\s+)?([a-z]+)\s*(?:de\s+)?(\d{2,4})",
        texto_norm,
    )
    if match_es:
        dia_s, mes_s, anio_s = match_es.groups()
        mes = _MESES_ES.get(mes_s)
        if mes:
            try:
                dia = int(dia_s)
                anio = int(anio_s)
                if anio < 100:
                    anio += 2000
                fecha_dt = datetime(anio, mes, dia)
                return fecha_dt.strftime("%d-%m-%Y")
            except ValueError:
                pass

    # Caso numérico: separadores /, -, ., espacios
    partes = re.split(r"[\s/\-.]+", texto_norm.strip("-. "))
    partes = [p for p in partes if p.isdigit()]

    if len(partes) >= 3:
        a, b, c = partes[0], partes[1], partes[2]
        candidatos = []
        # dd-mm-yyyy o dd-mm-yy
        candidatos.append((a, b, c))
        # yyyy-mm-dd
        if len(a) == 4:
            candidatos = [(c, b, a)] + candidatos

        for dia_s, mes_s, anio_s in candidatos:
            try:
                dia = int(dia_s)
                mes = int(mes_s)
                anio = int(anio_s)
                if anio < 100:
                    anio += 2000
                fecha_dt = datetime(anio, mes, dia)
                return fecha_dt.strftime("%d-%m-%Y")
            except ValueError:
                continue

    # Fallback: usar la versión sanitizada (no se pudo parsear como fecha)
    return _sanitizar_componente(texto)


def construir_nuevo_nombre(niu, fecha, extension):
    """Construye el nuevo nombre con formato NIU_dd-mm-aaaa_acta.ext.

    Devuelve None si falta el NIU o la Fecha (no se puede renombrar).
    """
    niu_limpio = _sanitizar_componente(niu)
    fecha_limpia = _normalizar_fecha(fecha)

    if not niu_limpio or not fecha_limpia:
        return None

    extension = extension.lower() if extension else ""
    return f"{niu_limpio}_{fecha_limpia}_acta{extension}"


def renombrar_archivo(file_path, data):
    """Renombra el archivo original a NIU_dd-mm-aaaa_acta.ext usando NIU y Fecha extraídos.

    Reglas:
    - Si NIU o Fecha no se pudieron extraer, no hace nada.
    - Si el archivo ya tiene el nombre correcto, no hace nada.
    - Si ya existe otro archivo con ese nombre en la misma carpeta,
      añade un sufijo numérico (_2, _3, ...).

    Devuelve la ruta final del archivo (nueva o la original si no se renombró).
    """
    if not file_path or not os.path.exists(file_path):
        return file_path

    if not isinstance(data, dict):
        return file_path

    niu = data.get("NIU")
    fecha = data.get("Fecha")

    directorio = os.path.dirname(file_path)
    nombre_actual = os.path.basename(file_path)
    _, extension = os.path.splitext(nombre_actual)

    nuevo_nombre = construir_nuevo_nombre(niu, fecha, extension)
    if not nuevo_nombre:
        print(f"⚠️ No se renombró '{nombre_actual}': falta NIU o Fecha en los datos extraídos.")
        return file_path

    # Si ya tiene el nombre correcto, no hacer nada
    if nombre_actual.lower() == nuevo_nombre.lower():
        return file_path

    nueva_ruta = os.path.join(directorio, nuevo_nombre)

    # Evitar colisiones con otros archivos existentes
    if os.path.exists(nueva_ruta):
        base, ext = os.path.splitext(nuevo_nombre)
        contador = 2
        while True:
            candidato = f"{base}_{contador}{ext}"
            ruta_candidata = os.path.join(directorio, candidato)
            if not os.path.exists(ruta_candidata):
                nueva_ruta = ruta_candidata
                nuevo_nombre = candidato
                break
            contador += 1

    try:
        os.rename(file_path, nueva_ruta)
        print(f"📝 Renombrado: '{nombre_actual}' -> '{nuevo_nombre}'")
        return nueva_ruta
    except OSError as e:
        print(f"❌ No se pudo renombrar '{nombre_actual}': {e}")
        return file_path
