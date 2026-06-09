"""Modos de operación del sistema OCR."""

OCR_ONLY = "ocr_only"
RENAME_ONLY = "rename_only"
OCR_AND_RENAME = "ocr_and_rename"

MODE_OPTIONS = {
    OCR_ONLY: {
        "label": "Solo OCR",
        "description": "Extrae los datos del acta y genera Excel. No modifica el nombre del archivo.",
        "icon": "📊",
    },
    RENAME_ONLY: {
        "label": "Solo renombrar",
        "description": "Lee el acta con IA y renombra el archivo a NIU_dd-mm-aaaa_acta. No genera Excel.",
        "icon": "📝",
    },
    OCR_AND_RENAME: {
        "label": "OCR + Renombrar",
        "description": "Extrae datos, genera Excel y renombra el archivo original.",
        "icon": "⚡",
    },
}


def exporta_excel(mode: str) -> bool:
    return mode in (OCR_ONLY, OCR_AND_RENAME)


def renombra_archivo(mode: str) -> bool:
    return mode in (RENAME_ONLY, OCR_AND_RENAME)
