import os

files = [
    "00_portada.md",
    "00_indice.md",
    "01_introduccion.md",
    "02_marco_teorico.md",
    "03_metodologia_arquitectura.md",
    "04_implementacion_pruebas.md",
    "05_conclusiones.md",
    "06_manual_usuario.md",
    "07_estructura_db.md",
    "08_justificacion_librerias.md"
]

content = ""
for f in files:
    with open(os.path.join("docs", "tesis", f), "r", encoding="utf-8") as file:
        content += file.read() + "\n\n"

with open(os.path.join("docs", "tesis", "tesis_completa.md"), "w", encoding="utf-8") as file:
    file.write(content)

print("Concatenación completa: tesis_completa.md")
