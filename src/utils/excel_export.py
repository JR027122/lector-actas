import pandas as pd

COLUMNAS_ORDENADAS = [
    "NIU", "Nombre_Usuario", "Cedula_Usuario", "Municipio", "Vereda",
    "Fecha", "Hora", "Condicion_Climatica", "Sistema_Activo",
    "Panel_1_Serie", "Panel_1_Estado", "Panel_1_Obs",
    "Panel_2_Serie", "Panel_2_Estado", "Panel_2_Obs",
    "Panel_3_Serie", "Panel_3_Estado", "Panel_3_Obs",
    "Bateria_1_Serie", "Bateria_1_Estado", "Bateria_1_Obs",
    "Bateria_2_Serie", "Bateria_2_Estado", "Bateria_2_Obs",
    "Controlador_Serie", "Controlador_Estado", "Controlador_Obs",
    "Inversor_Serie", "Inversor_Estado", "Inversor_Obs",
    "Medidor_Serie", "Medidor_Estado", "Medidor_Obs",
    "Corriente_Entrada_Bateria", "Corriente_Salida_Bateria",
    "Voltaje_Toma_1", "Voltaje_Toma_2", "Voltaje_Toma_3", "Voltaje_Toma_4",
    "Voltaje_Tierra_Neutro", "Latitud", "Longitud", "Observacion_General",
    "Revisar_Manual", "Motivo_Revision", "Archivo",
]


def limpiar_registro(data: dict) -> dict:
    """Quita claves internas antes de exportar a Excel."""
    return {k: v for k, v in data.items() if not k.startswith("__")}


def ordenar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    columnas_finales = [col for col in COLUMNAS_ORDENADAS if col in df.columns]
    extras = [col for col in df.columns if col not in columnas_finales]
    return df[columnas_finales + extras]
