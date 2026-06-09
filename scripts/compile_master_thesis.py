import os

# Configuración de directorios en orden lógico
dirs = [
    "docs/tesis_maestria/Preliminares",
    "docs/tesis_maestria/Seccion_2_Introduccion",
    "docs/tesis_maestria/Seccion_3_Marco_Referencial",
    "docs/tesis_maestria/Seccion_4_Metodologia",
    "docs/tesis_maestria/Seccion_5_Resultados",
    "docs/tesis_maestria/Seccion_6_Cierre",
    "docs/tesis_maestria/Seccion_7_Anexos"
]

output_file = "docs/tesis_maestria/Tesis_Maestria_Completa.md"
content = ""

print("Iniciando compilación de la tesis...")

for d in dirs:
    if not os.path.exists(d):
        print(f"Advertencia: El directorio {d} no existe.")
        continue
    
    print(f"Procesando: {d}")
    # Listar archivos y ordenarlos alfabéticamente (por su prefijo numérico)
    files = sorted([f for f in os.listdir(d) if f.endswith(".md")])
    
    for f in files:
        file_path = os.path.join(d, f)
        with open(file_path, "r", encoding="utf-8") as file:
            # Añadir saltos de página o separadores si es necesario
            content += file.read() + "\n\n"
            # Opcional: añadir un separador visual o salto de página para Word
            content += "---\n\n" 

with open(output_file, "w", encoding="utf-8") as file:
    file.write(content)

print(f"Compilación exitosa! Archivo generado: {output_file}")
