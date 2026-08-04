"""
Búsqueda de NIU en una base de datos de usuarios (Excel o CSV).

Cuando el OCR no encuentra el NIU en el documento (p. ej. registros
fotográficos), se busca por cédula o por nombre en la base cargada
por el usuario y se completa el NIU para poder renombrar el archivo.

Columnas esperadas (detección flexible de nombres):
- NIU         (también: niu, codigo, código)
- Cédula      (también: cedula, cc, documento, identificacion, identificación)
- Nombre      (también: nombre, usuario, nombre_usuario, cliente)
"""

import difflib
import os
import re
import unicodedata

import pandas as pd

# Umbral de similitud para coincidencia de nombres (0-1)
NAME_MATCH_CUTOFF = 0.87

# Rango vigente de NIU de la organización (ambos límites inclusive). Ajusta
# estos límites si el rango cambia; se usan para reconocer un NIU válido tanto
# en el nombre del archivo como dentro del acta. Fuera de este rango un número
# NO se considera un NIU (ni un número menos, ni uno más).
NIU_MIN = 86320021
NIU_MAX = 99024940

_DIGIT_RUN = re.compile(r"\d+")
_SUFIJO_DUPLICADO = re.compile(r"\s*\(\d+\)\s*$")

_NIU_COLS = ("niu", "codigo", "código")
_CEDULA_COLS = ("cedula", "cédula", "cc", "documento", "identificacion", "identificación", "cedula_usuario")
_NOMBRE_COLS = ("nombre", "usuario", "nombre_usuario", "nombre_completo", "cliente")


def _normalizar_texto(valor) -> str:
    """Mayúsculas, sin acentos, espacios colapsados."""
    if valor is None:
        return ""
    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _solo_digitos(valor) -> str:
    if valor is None:
        return ""
    return re.sub(r"\D", "", str(valor))


def niu_en_rango(valor) -> bool:
    """True si `valor` es un NIU dentro del rango válido [NIU_MIN, NIU_MAX].

    Toma solo los dígitos del valor recibido. Fuera del rango (o sin dígitos)
    el número no se considera un NIU válido: ni un número menos, ni uno más.
    """
    digitos = _solo_digitos(valor)
    if not digitos:
        return False
    try:
        return NIU_MIN <= int(digitos) <= NIU_MAX
    except ValueError:
        return False


def _detectar_columna(df: pd.DataFrame, candidatas: tuple) -> str | None:
    normalizadas = {_normalizar_texto(c).lower().replace(" ", "_"): c for c in df.columns}
    for cand in candidatas:
        clave = _normalizar_texto(cand).lower().replace(" ", "_")
        if clave in normalizadas:
            return normalizadas[clave]
    # Coincidencia parcial (p. ej. "No. Cedula")
    for clave, original in normalizadas.items():
        for cand in candidatas:
            if _normalizar_texto(cand).lower().replace(" ", "_") in clave:
                return original
    return None


class UserDatabase:
    """Índice en memoria: cédula → NIU y nombre normalizado → NIU."""

    def __init__(self, por_cedula: dict, por_nombre: dict, total: int):
        self.por_cedula = por_cedula
        self.por_nombre = por_nombre
        self.total = total
        self._nombres = list(por_nombre.keys())
        self.nius_validos = {
            _solo_digitos(n)
            for n in set(por_cedula.values()) | set(por_nombre.values())
        }

    def contiene_niu(self, niu) -> bool:
        return _solo_digitos(niu) in self.nius_validos

    def buscar_por_cedula(self, cedula) -> str | None:
        digitos = _solo_digitos(cedula)
        if not digitos:
            return None
        return self.por_cedula.get(digitos)

    def buscar_por_nombre(self, nombre) -> str | None:
        nombre_norm = _normalizar_texto(nombre)
        if not nombre_norm:
            return None
        # Coincidencia exacta primero
        if nombre_norm in self.por_nombre:
            return self.por_nombre[nombre_norm]
        # Coincidencia aproximada (errores de OCR / orden de apellidos)
        candidatos = difflib.get_close_matches(
            nombre_norm, self._nombres, n=1, cutoff=NAME_MATCH_CUTOFF
        )
        if candidatos:
            return self.por_nombre[candidatos[0]]
        return None

    def buscar_niu(self, cedula=None, nombre=None) -> tuple[str | None, str | None]:
        """Devuelve (niu, metodo) donde metodo es 'cedula' o 'nombre'."""
        niu = self.buscar_por_cedula(cedula)
        if niu:
            return niu, "cedula"
        niu = self.buscar_por_nombre(nombre)
        if niu:
            return niu, "nombre"
        return None, None


def cargar_base_usuarios(ruta_o_buffer) -> UserDatabase:
    """Carga un Excel (.xlsx/.xls) o CSV con columnas NIU, Cédula y/o Nombre.

    Lanza ValueError con mensaje claro si faltan columnas indispensables.
    """
    nombre_archivo = str(getattr(ruta_o_buffer, "name", ruta_o_buffer)).lower()
    if nombre_archivo.endswith(".csv"):
        df = pd.read_csv(ruta_o_buffer, dtype=str)
    else:
        df = pd.read_excel(ruta_o_buffer, dtype=str)

    col_niu = _detectar_columna(df, _NIU_COLS)
    if not col_niu:
        raise ValueError(
            "La base de usuarios debe tener una columna 'NIU'. "
            f"Columnas encontradas: {list(df.columns)}"
        )

    col_cedula = _detectar_columna(df, _CEDULA_COLS)
    col_nombre = _detectar_columna(df, _NOMBRE_COLS)
    if not col_cedula and not col_nombre:
        raise ValueError(
            "La base de usuarios debe tener al menos una columna de 'Cédula' o 'Nombre'. "
            f"Columnas encontradas: {list(df.columns)}"
        )

    por_cedula: dict = {}
    por_nombre: dict = {}
    total = 0

    for _, fila in df.iterrows():
        niu = str(fila[col_niu]).strip() if pd.notna(fila[col_niu]) else ""
        if not niu or niu.lower() in ("nan", "none", "null"):
            continue
        total += 1
        if col_cedula and pd.notna(fila[col_cedula]):
            digitos = _solo_digitos(fila[col_cedula])
            if digitos:
                por_cedula[digitos] = niu
        if col_nombre and pd.notna(fila[col_nombre]):
            nombre_norm = _normalizar_texto(fila[col_nombre])
            if nombre_norm:
                por_nombre[nombre_norm] = niu

    if total == 0:
        raise ValueError("La base de usuarios no tiene filas con NIU válido.")

    return UserDatabase(por_cedula, por_nombre, total)


def extraer_niu_de_nombre_archivo(nombre_archivo) -> str | None:
    """Busca un NIU válido (NIU_MIN-NIU_MAX) en el nombre original del archivo.

    Útil cuando el acta no trae el campo NIU diligenciado, pero quien
    organizó los archivos ya lo incluyó en el nombre (p. ej.
    "01. Cumaribo 426_99000100.pdf" -> NIU 99000100).

    Ignora el sufijo que Windows agrega a archivos duplicados, como
    "86320021 (2).pdf" -> igual reconoce 86320021.
    """
    if not nombre_archivo:
        return None

    base = os.path.splitext(str(nombre_archivo))[0]
    base = _SUFIJO_DUPLICADO.sub("", base)

    for run in _DIGIT_RUN.findall(base):
        candidatos = set()
        if len(run) == 8:
            candidatos.add(run)
        elif len(run) > 8:
            # El NIU podría venir pegado a otro número (fecha, consecutivo...)
            candidatos.add(run[:8])
            candidatos.add(run[-8:])
        for candidato in candidatos:
            if NIU_MIN <= int(candidato) <= NIU_MAX:
                return candidato

    return None


def _marcar_para_revisar(data: dict, mensaje: str) -> None:
    data["Revisar_Manual"] = "Sí"
    existente = data.get("Motivo_Revision") or ""
    data["Motivo_Revision"] = "; ".join(p for p in (existente, mensaje) if p)


def _validar_niu_contra_base(
    data: dict, niu: str, user_db: "UserDatabase | None", fuente: str
) -> None:
    """Valida un NIU (ya en rango) contra la base de usuarios y marca revisión.

    `fuente` es un texto legible del origen del NIU ("nombre del archivo" o
    "acta") que se usa en los mensajes y en el motivo de revisión.

    - Sin base cargada: no hay nada contra qué contrastar, se acepta.
    - El NIU aparece en la base: confirmado.
    - La base tiene otro NIU para esa cédula/nombre: se conserva el de la
      `fuente` (es la fuente directa) pero se marca para revisión manual.
    - No aparece por ningún lado: se conserva pero se marca para revisión.
    """
    if user_db is None:
        print(f"NIU {niu} tomado del {fuente}.")
        return

    if user_db.contiene_niu(niu):
        print(f"NIU {niu} tomado del {fuente} (validado contra la base).")
        return

    niu_bd, metodo_bd = user_db.buscar_niu(
        cedula=data.get("Cedula_Usuario"),
        nombre=data.get("Nombre_Usuario"),
    )
    if niu_bd and _solo_digitos(niu_bd) == _solo_digitos(niu):
        print(f"NIU {niu} tomado del {fuente} (confirmado por {metodo_bd} en la base).")
        return

    if niu_bd:
        print(
            f"Advertencia: el NIU '{niu}' del {fuente} no coincide con el NIU "
            f"'{niu_bd}' de la base (por {metodo_bd}). Se usa el del {fuente}."
        )
        _marcar_para_revisar(
            data,
            f"NIU del {fuente} ({niu}) no coincide con el de la base de usuarios "
            f"({niu_bd}, por {metodo_bd})",
        )
        return

    print(
        f"Advertencia: NIU '{niu}' del {fuente} no aparece en la base de usuarios "
        "y no se encontró por cédula ni nombre."
    )
    _marcar_para_revisar(
        data, f"NIU del {fuente} ({niu}) no está en la base de usuarios"
    )


def completar_niu(
    data: dict,
    user_db: "UserDatabase | None" = None,
    nombre_archivo: str | None = None,
) -> dict:
    """Determina el NIU del registro para poder renombrar el acta.

    Orden de búsqueda:
    1. Nombre del archivo original — fuente PRIORITARIA. Quien organizó las
       actas suele poner ahí el NIU; se reconoce un número dentro del rango
       válido [NIU_MIN, NIU_MAX]. Funciona incluso sin base de usuarios.
    2. Dentro del acta — el NIU que extrajo el OCR, aceptado SOLO si cae en el
       rango válido [NIU_MIN, NIU_MAX]. Un número fuera del rango no es un NIU.
    3. Base de usuarios por cédula o nombre (si se cargó una), como último
       recurso cuando ni el nombre ni el acta dieron un NIU válido.

    IMPORTANTE: si hay una base de usuarios cargada, el NIU tomado del nombre
    del archivo o del acta SIEMPRE se valida contra ella. Si no coincide, se
    conserva el de la fuente directa pero el registro queda marcado en
    Revisar_Manual/Motivo_Revision para confirmarlo a mano.

    Marca data['__niu_origen__'] = 'nombre_archivo' | 'cedula' | 'nombre'
    cuando el NIU se recuperó de una fuente distinta al propio acta.
    """
    niu_acta = str(data.get("NIU") or "").strip()
    if niu_acta.lower() in ("nan", "none", "null"):
        niu_acta = ""

    # 1. Nombre del archivo (fuente prioritaria). extraer_niu_de_nombre_archivo
    #    solo devuelve números dentro del rango válido.
    niu_archivo = extraer_niu_de_nombre_archivo(nombre_archivo)
    if niu_archivo:
        data["NIU"] = niu_archivo
        data["__niu_origen__"] = "nombre_archivo"
        _validar_niu_contra_base(data, niu_archivo, user_db, "nombre del archivo")
        return data

    # 2. Dentro del acta: solo se acepta si está en el rango válido.
    if niu_acta and niu_en_rango(niu_acta):
        data["NIU"] = niu_acta
        _validar_niu_contra_base(data, niu_acta, user_db, "acta")
        return data

    if niu_acta:
        print(
            f"NIU '{niu_acta}' del acta está fuera del rango válido "
            f"({NIU_MIN}-{NIU_MAX}); no se usa como NIU."
        )

    # 3. Base de usuarios por cédula o nombre (último recurso).
    if user_db is not None:
        niu_bd, metodo = user_db.buscar_niu(
            cedula=data.get("Cedula_Usuario"),
            nombre=data.get("Nombre_Usuario"),
        )
        if niu_bd:
            print(f"NIU {niu_bd} recuperado de la base de usuarios (por {metodo}).")
            data["NIU"] = niu_bd
            data["__niu_origen__"] = metodo
            return data

    # No se pudo determinar un NIU válido. Si el acta traía uno fuera de rango,
    # se conserva para no perder el dato, pero se marca para revisión manual.
    if niu_acta and not niu_en_rango(niu_acta):
        _marcar_para_revisar(
            data,
            f"NIU '{niu_acta}' del acta está fuera del rango válido "
            f"({NIU_MIN}-{NIU_MAX})",
        )
    return data
