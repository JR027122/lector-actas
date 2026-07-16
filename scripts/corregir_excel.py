"""
Corrige un Excel consolidado que ya tienes (de un lote ya procesado):

1. Coordenadas mal diligenciadas por temas de punto decimal: falta el
   punto, o el número quedó pegado sin separador ("00.28888889" -> el
   heurístico prueba dónde debería ir el punto según el rango típico de
   Colombia: longitud siempre negativa entre -66 y -80, latitud entre
   -5 y 13.5 aprox.). Si no se puede reconstruir con confianza, NO se
   inventa un valor: se deja igual y se marca para que la revises a mano.

2. Estado (Bueno/Regular/Malo) y palabras técnicas mal transcritas en las
   observaciones (mismo corrector por catálogo que ya usa la app en cada
   acta nueva).

3. Vuelve a correr la detección de filas sospechosas (posible dato
   inventado por el modelo) sobre los datos ya corregidos.

Uso:
    python scripts/corregir_excel.py "ruta\\al\\consolidado.xlsx"

Genera "<nombre>_corregido.xlsx" junto al original (el original NO se
toca). Las celdas que se corrigieron quedan resaltadas en amarillo; las
filas que necesitas revisar a mano (coordenadas dudosas o posibles datos
inventados), en rojo claro.
"""

import os
import re
import sys

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# Para poder importar src.* al correr este script directamente desde scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.post_procesado import corregir_estado, corregir_texto_libre, detectar_filas_sospechosas

CAMPOS_ESTADO = [
    "Panel_1_Estado", "Panel_2_Estado", "Panel_3_Estado",
    "Bateria_1_Estado", "Bateria_2_Estado",
    "Controlador_Estado", "Inversor_Estado", "Medidor_Estado",
]

# Rango aproximado de Colombia continental. Ajusta estos límites si tu
# zona de operación es distinta.
LAT_MIN, LAT_MAX = -5.0, 13.5
LON_MIN, LON_MAX = -80.0, -66.0

CAMPOS_OBS = [
    "Panel_1_Obs", "Panel_2_Obs", "Panel_3_Obs",
    "Bateria_1_Obs", "Bateria_2_Obs",
    "Controlador_Obs", "Inversor_Obs", "Medidor_Obs",
    "Observacion_General",
]

RELLENO_CORREGIDO = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
RELLENO_REVISAR = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")


def _valor_valido(valor) -> bool:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return False
    texto = str(valor).strip().lower()
    return texto not in ("", "nan", "none", "null")


def _signo_y_digitos(valor) -> tuple[bool, str, str]:
    """Devuelve (es_negativo, solo_digitos, texto_con_punto_normalizado)."""
    texto = str(valor).strip()
    # Coma como separador decimal -> punto
    if texto.count(",") == 1 and "." not in texto:
        texto = texto.replace(",", ".")
    negativo = texto.startswith("-")
    solo_digitos = re.sub(r"[^0-9]", "", texto)
    return negativo, solo_digitos, texto


def corregir_longitud(valor):
    """Colombia: la longitud siempre es negativa, magnitud aprox. entre 66 y 80.

    Devuelve (valor_corregido, se_corrigio, necesita_revision).
    """
    if not _valor_valido(valor):
        return valor, False, False

    original = str(valor).strip()
    _, digitos, texto_normalizado = _signo_y_digitos(valor)

    try:
        numero = float(texto_normalizado)
        if LON_MIN <= numero <= LON_MAX:
            corregido = texto_normalizado != original
            return (numero, corregido, False)
        if LON_MIN <= -abs(numero) <= LON_MAX:
            return (-abs(numero), True, False)
    except ValueError:
        pass

    # Probablemente falta el punto: dos dígitos enteros (66-79.999...)
    if len(digitos) > 2:
        try:
            candidato = float(f"{digitos[:2]}.{digitos[2:]}")
        except ValueError:
            candidato = None
        if candidato is not None and 66.0 <= candidato <= 80.0:
            return (-candidato, True, False)

    return valor, False, True


def corregir_latitud(valor):
    """Colombia continental: un solo dígito entero, magnitud entre 0 y ~13.5.

    Devuelve (valor_corregido, se_corrigio, necesita_revision).
    """
    if not _valor_valido(valor):
        return valor, False, False

    original = str(valor).strip()
    negativo, digitos, texto_normalizado = _signo_y_digitos(valor)

    try:
        numero = float(texto_normalizado)
        if LAT_MIN <= numero <= LAT_MAX:
            corregido = texto_normalizado != original
            return (numero, corregido, False)
    except ValueError:
        pass

    if len(digitos) > 1:
        try:
            candidato = float(f"{digitos[:1]}.{digitos[1:]}")
        except ValueError:
            candidato = None
        if candidato is not None:
            final = -candidato if negativo else candidato
            if LAT_MIN <= final <= LAT_MAX:
                return (final, True, False)

    return valor, False, True


def procesar_excel(ruta_entrada: str):
    df = pd.read_excel(ruta_entrada)

    cambios = []  # (fila_idx, nombre_columna)
    filas_revisar_coord = set()

    if "Revisar_Manual" not in df.columns:
        df["Revisar_Manual"] = "No"
    if "Motivo_Revision" not in df.columns:
        df["Motivo_Revision"] = ""
    df["Revisar_Coordenadas"] = "No"

    for idx in df.index:
        motivos_fila = []

        if "Latitud" in df.columns:
            nuevo, corregido, revisar = corregir_latitud(df.at[idx, "Latitud"])
            if corregido:
                df.at[idx, "Latitud"] = nuevo
                cambios.append((idx, "Latitud"))
            if revisar:
                filas_revisar_coord.add(idx)
                motivos_fila.append("Latitud no se pudo corregir automáticamente")

        if "Longitud" in df.columns:
            nuevo, corregido, revisar = corregir_longitud(df.at[idx, "Longitud"])
            if corregido:
                df.at[idx, "Longitud"] = nuevo
                cambios.append((idx, "Longitud"))
            if revisar:
                filas_revisar_coord.add(idx)
                motivos_fila.append("Longitud no se pudo corregir automáticamente")

        for campo in CAMPOS_ESTADO:
            if campo not in df.columns:
                continue
            original = df.at[idx, campo]
            if not _valor_valido(original):
                continue
            corregido_estado = corregir_estado(original)
            if corregido_estado != original:
                df.at[idx, campo] = corregido_estado
                cambios.append((idx, campo))

        for campo in CAMPOS_OBS:
            if campo not in df.columns:
                continue
            original = df.at[idx, campo]
            if not _valor_valido(original):
                continue
            corregido_texto = corregir_texto_libre(original)
            if corregido_texto != original:
                df.at[idx, campo] = corregido_texto
                cambios.append((idx, campo))

        # Re-evalúa filas sospechosas (posible dato inventado) con los
        # valores ya corregidos.
        motivos_equipos = detectar_filas_sospechosas(df.loc[idx].to_dict())
        if motivos_equipos:
            df.at[idx, "Revisar_Manual"] = "Sí"
            existentes = df.at[idx, "Motivo_Revision"] if _valor_valido(df.at[idx, "Motivo_Revision"]) else ""
            df.at[idx, "Motivo_Revision"] = "; ".join([p for p in [existentes, *motivos_equipos] if p])

        if motivos_fila:
            df.at[idx, "Revisar_Coordenadas"] = "Sí"
            existentes = df.at[idx, "Motivo_Revision"] if _valor_valido(df.at[idx, "Motivo_Revision"]) else ""
            df.at[idx, "Motivo_Revision"] = "; ".join([p for p in [existentes, *motivos_fila] if p])

    return df, cambios, filas_revisar_coord


def main():
    if len(sys.argv) < 2:
        print('Uso: python scripts/corregir_excel.py "ruta\\al\\consolidado.xlsx"')
        sys.exit(1)

    ruta_entrada = sys.argv[1]
    if not os.path.exists(ruta_entrada):
        print(f"No se encontró el archivo: {ruta_entrada}")
        sys.exit(1)

    df, cambios, filas_revisar_coord = procesar_excel(ruta_entrada)

    base, ext = os.path.splitext(ruta_entrada)
    ruta_salida = f"{base}_corregido{ext}"
    df.to_excel(ruta_salida, index=False, engine="openpyxl")

    # Resaltar celdas corregidas y filas para revisar
    wb = load_workbook(ruta_salida)
    ws = wb.active
    columnas = {cell.value: cell.column for cell in ws[1]}

    for fila_idx, columna in cambios:
        col_excel = columnas.get(columna)
        if col_excel:
            ws.cell(row=fila_idx + 2, column=col_excel).fill = RELLENO_CORREGIDO

    col_revisar_manual = columnas.get("Revisar_Manual")
    col_revisar_coord = columnas.get("Revisar_Coordenadas")
    filas_con_alerta = set(filas_revisar_coord)
    for idx in df.index:
        if df.at[idx, "Revisar_Manual"] == "Sí":
            filas_con_alerta.add(idx)

    for idx in filas_con_alerta:
        fila_excel = idx + 2
        if col_revisar_manual:
            ws.cell(row=fila_excel, column=col_revisar_manual).fill = RELLENO_REVISAR
        if col_revisar_coord:
            ws.cell(row=fila_excel, column=col_revisar_coord).fill = RELLENO_REVISAR

    wb.save(ruta_salida)

    print(f"Celdas corregidas (ortografía/coordenadas): {len(cambios)}")
    print(f"Filas con coordenadas que necesitan revisión manual: {len(filas_revisar_coord)}")
    print(f"Filas marcadas Revisar_Manual = Sí: {(df['Revisar_Manual'] == 'Sí').sum()}")
    print(f"\nGuardado en: {ruta_salida}")


if __name__ == "__main__":
    main()
