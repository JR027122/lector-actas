"""
Limpieza y validación posterior a la extracción con IA.

Dos cosas distintas, a propósito:

1. Corrección de ortografía por catálogo cerrado: el campo "Estado" solo
   puede valer Bueno/Regular/Malo, y las observaciones repiten palabras
   técnicas conocidas (Falta, Revisar, Falla...). Los errores de OCR tipo
   "Regulor" o "Fata" se corrigen por coincidencia difusa contra ese
   vocabulario, sin tocar el resto del texto libre.

2. Detección de filas sospechosas: si dos equipos de FAMILIAS distintas
   (p. ej. un panel y una batería) terminan con el mismo Estado y una
   Observación casi idéntica, es una señal típica de que el modelo
   "inventó" una fila copiando/parafraseando otra (visto en pruebas con
   Gemini Flash Lite: un panel fantasma con el mismo estado/observación
   que una batería real). No se comparan los seriales directamente:
   probamos que dos seriales de la MISMA familia (dos paneles del mismo
   lote) se parecen tanto o más que un caso real de alucinación, así que
   la similitud de texto libre (Observaciones) es la señal fiable, no el
   serial. Esto no es un error de ortografía y ningún corrector de
   palabras lo puede arreglar; lo único sensato es marcar el documento
   para revisión manual en vez de confiar en el dato.
"""

import difflib
import re

# Valores válidos del campo "Estado" de cada equipo.
CATALOGO_ESTADOS = ["Bueno", "Regular", "Malo"]

# Palabras técnicas frecuentes en las observaciones manuscritas. Ajusta esta
# lista con el vocabulario real que veas repetirse en tus actas.
VOCABULARIO_OBSERVACIONES = [
    "Falta", "Falla", "Fallas", "Revisar", "Revisión", "Tomar", "Medidas",
    "Medidos", "Cambiar", "Cambio", "Sin", "Problema", "Novedad", "Bueno",
    "Regular", "Malo", "Dañado", "Dañada", "Daño", "Corrosión", "Sulfatado",
    "Sulfatada", "Ajustar", "Limpiar", "Limpieza", "Reemplazar", "Conexión",
    "Suelto", "Suelta", "Floja", "Flojo", "Oxidado", "Oxidada",
]

UMBRAL_SIMILITUD_ESTADO = 0.6
UMBRAL_SIMILITUD_PALABRA = 0.75
UMBRAL_SIMILITUD_OBS_DUPLICADA = 0.85

# Slots de equipo que se corrigen (ortografía) y se consideran para detectar duplicados.
EQUIPOS = [
    "Panel_1", "Panel_2", "Panel_3",
    "Bateria_1", "Bateria_2",
    "Controlador", "Inversor", "Medidor",
]

# Familia de cada equipo: dentro de la MISMA familia es normal que los
# seriales se parezcan (mismo lote, numeración secuencial: SR-238-1-0733,
# SR-238-2-0733...), así que esos pares NO se comparan. Solo se compara
# entre familias distintas (p. ej. un panel contra una batería), donde no
# hay ninguna razón para que coincidan.
FAMILIA = {
    "Panel_1": "panel", "Panel_2": "panel", "Panel_3": "panel",
    "Bateria_1": "bateria", "Bateria_2": "bateria",
    "Controlador": "controlador",
    "Inversor": "inversor",
    "Medidor": "medidor",
}


def _valor_valido(valor) -> bool:
    if valor is None:
        return False
    texto = str(valor).strip().lower()
    return texto not in ("", "nan", "none", "null")


def _mejor_coincidencia(valor: str, catalogo: list, umbral: float) -> str | None:
    if not valor:
        return None
    coincidencias = difflib.get_close_matches(valor, catalogo, n=1, cutoff=umbral)
    return coincidencias[0] if coincidencias else None


def corregir_estado(valor):
    """Normaliza el campo Estado contra el catálogo (Bueno/Regular/Malo).

    Si no se parece lo suficiente a ningún valor del catálogo, se deja
    intacto (mejor no tocar algo que no reconocemos que forzar un valor).
    """
    if not _valor_valido(valor):
        return valor
    corregido = _mejor_coincidencia(str(valor).strip(), CATALOGO_ESTADOS, UMBRAL_SIMILITUD_ESTADO)
    return corregido or valor


def corregir_texto_libre(texto):
    """Corrige palabra por palabra contra el vocabulario técnico conocido.

    Solo reemplaza palabras muy parecidas a una del vocabulario (Fata ->
    Falta, Revisor -> Revisar); el resto del texto (nombres propios,
    cifras, palabras sin parecido cercano) se deja intacto para no
    inventar contenido que no estaba en el acta.
    """
    if not _valor_valido(texto):
        return texto

    tokens = re.findall(r"\w+|\W+", str(texto))
    resultado = []
    for token in tokens:
        if token.isalpha():
            corregida = _mejor_coincidencia(token.capitalize(), VOCABULARIO_OBSERVACIONES, UMBRAL_SIMILITUD_PALABRA)
            if corregida and corregida.lower() != token.lower():
                resultado.append(corregida if token[0].isupper() else corregida.lower())
                continue
        resultado.append(token)
    return "".join(resultado)


def detectar_filas_sospechosas(data: dict) -> list[str]:
    """Detecta equipos de familias distintas con Estado igual y Observación casi idéntica.

    IMPORTANTE: se llama DESPUÉS de corregir_estado/corregir_texto_libre,
    para que errores de OCR (Regulor/Regular, Fata/Falta) no impidan ver
    que en realidad dicen lo mismo.

    Devuelve una lista de descripciones legibles (una por cada par
    sospechoso encontrado). Lista vacía si no hay nada raro.
    """
    equipos_validos = []
    for equipo in EQUIPOS:
        estado = data.get(f"{equipo}_Estado")
        obs = data.get(f"{equipo}_Obs")
        if not _valor_valido(estado) or not _valor_valido(obs):
            continue
        equipos_validos.append((equipo, str(estado).strip().lower(), str(obs).strip().lower()))

    hallazgos: list[str] = []
    for i in range(len(equipos_validos)):
        nombre_a, estado_a, obs_a = equipos_validos[i]
        for j in range(i + 1, len(equipos_validos)):
            nombre_b, estado_b, obs_b = equipos_validos[j]

            if FAMILIA[nombre_a] == FAMILIA[nombre_b]:
                continue  # misma familia: normal que se parezcan (mismo lote)

            if estado_a != estado_b:
                continue

            if estado_a == "bueno":
                # "Todo bien, sin novedad" repetido en varios equipos es lo
                # normal y esperable; no es señal de nada raro. Lo que sí
                # llama la atención es que un problema puntual (Regular/Malo)
                # se repita idéntico en equipos que no tienen por qué compartir
                # nada.
                continue

            ratio = difflib.SequenceMatcher(None, obs_a, obs_b).ratio()
            if ratio >= UMBRAL_SIMILITUD_OBS_DUPLICADA:
                hallazgos.append(
                    f"{nombre_a} y {nombre_b} tienen el mismo estado y una observación "
                    "casi idéntica (posible dato duplicado o inventado por el modelo)"
                )

    return hallazgos


def post_procesar(data: dict) -> dict:
    """Aplica correcciones de vocabulario y marca el registro si hay filas sospechosas.

    Agrega dos columnas visibles en el Excel final: Revisar_Manual (Sí/No)
    y Motivo_Revision (por qué se marcó), para que el usuario pueda
    filtrar y revisar solo esos casos en vez de todo el lote.
    """
    for equipo in EQUIPOS:
        campo_estado = f"{equipo}_Estado"
        campo_obs = f"{equipo}_Obs"
        if campo_estado in data:
            data[campo_estado] = corregir_estado(data[campo_estado])
        if campo_obs in data:
            data[campo_obs] = corregir_texto_libre(data[campo_obs])

    if "Observacion_General" in data:
        data["Observacion_General"] = corregir_texto_libre(data["Observacion_General"])

    motivos = detectar_filas_sospechosas(data)
    data["Revisar_Manual"] = "Sí" if motivos else "No"
    data["Motivo_Revision"] = "; ".join(motivos)

    return data
