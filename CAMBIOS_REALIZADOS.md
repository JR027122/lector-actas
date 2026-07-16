# Cambios Realizados: Sistema de Reanudación

## Resumen
Se implementó un sistema completo de checkpoints y reanudación que permite:
1. Guardar automáticamente el progreso en `.progress.json`
2. Alimentar el Excel incrementalmente tras procesar cada archivo
3. Detectar procesamiento anterior incompleto
4. Preguntar al usuario si continuar o empezar de nuevo
5. Limpiar checkpoints automáticamente al terminar

---

## Archivos Modificados

### 1. **src/utils/progress_tracker.py** (NUEVO)
**Responsabilidad:** Gestionar la persistencia de checkpoints

**Clases:**
- `ProgressTracker` - Maneja guardar/cargar/actualizar progreso
  - `save(data)` - Guarda el estado en `.progress.json`
  - `load()` - Carga el estado anterior
  - `delete()` - Elimina el archivo de checkpoint
  - `register_processed_file(filename)` - Registra un archivo como procesado
  - `get_processed_files()` - Lista de archivos ya procesados
  - `has_previous_progress()` - Detecta si hay procesamiento anterior incompleto

**Formato de .progress.json:**
```json
{
  "folder": "/ruta/a/carpeta",
  "procesados": ["acta_001.pdf", "acta_002.pdf"],
  "timestamp": "2026-07-15T14:30:45.123456"
}
```

---

### 2. **src/core/document_processor.py** (MODIFICADO)
**Cambios:**

#### Imports agregados:
```python
import pandas as pd
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.progress_tracker import ProgressTracker
```

#### Modificación a `process_folder()`:
- **Nuevos parámetros:**
  - `progress_tracker: ProgressTracker | None = None`
  - `excel_callback=None`

- **Nueva lógica:**
  - Filtra archivos ya procesados si hay checkpoint anterior (línea 99-103)
  - Detecta si no hay archivos nuevos y limpia checkpoint (línea 107-111)
  - Registra cada archivo procesado exitosamente (línea 178-179)
  - Llama a `excel_callback` para actualizar Excel incrementalmente (línea 181-183)
  - Limpia checkpoint al terminar sin errores (línea 191-193)

---

### 3. **app_pyqt.py** (MODIFICADO)
**Cambios:**

#### Imports agregados:
```python
from src.utils.progress_tracker import ProgressTracker
```

#### Nuevas funciones:
- `preguntar_reanudacion(parent=None, carpeta="")` - Diálogo de confirmación de reanudación (línea 115-127)

#### Modificaciones a clase `WorkerThread`:
- Parámetros agregados al `__init__`:
  - `progress_tracker: ProgressTracker | None = None`
  - `excel_callback=None`
- En `run()`: pasa estos parámetros a `process_folder()`

#### Modificaciones a clase `AppOCR`:
- Atributos nuevos en `__init__`:
  - `self.progress_tracker = None`
  - `self.excel_path = ""`

- Método nuevo `_actualizar_excel_incremental()`:
  - Carga Excel anterior si existe
  - Evita duplicados por nombre de archivo
  - Combina datos anteriores + nuevos
  - Escribe el resultado combinado

- Método modificado `seleccionar_carpeta()`:
  - Crea un `ProgressTracker` para la carpeta
  - Detecta si hay `.progress.json` anterior
  - Si existe, pregunta al usuario si continuar o empezar de nuevo
  - Muestra visualmente si está "reanudando"

- Método modificado `iniciar_procesamiento()`:
  - Pasa `progress_tracker` y `excel_callback` al `WorkerThread`

- Método modificado `procesamiento_completado()`:
  - Carga Excel anterior si existe
  - Evita duplicados por nombre de archivo
  - Combina datos para generar Excel final completo

---

## Flujo de Ejecución

### Primera ejecución (sin checkpoint):
```
1. Usuario selecciona carpeta
2. No hay .progress.json
3. Inicia procesamiento normalmente
4. Tras procesar archivo 1: 
   - Registra en .progress.json: ["acta_1.pdf"]
   - Actualiza resultado_consolidado.xlsx (1 fila)
5. Tras procesar archivo 2:
   - Registra en .progress.json: ["acta_1.pdf", "acta_2.pdf"]
   - Actualiza resultado_consolidado.xlsx (2 filas)
6. Al terminar: elimina .progress.json
```

### Segunda ejecución (con checkpoint):
```
1. Usuario selecciona MISMA carpeta
2. Se detecta .progress.json con ["acta_1.pdf", "acta_2.pdf"]
3. Diálogo: "¿Continuar desde donde se quedó?"
   - Si "Continuar": filtra solo acta_3.pdf (y posteriores)
   - Si "Empezar de nuevo": elimina .progress.json y procesa todos
4. Solo procesa archivos pendientes
5. Excel se actualiza incrementalmente
6. Al terminar: elimina .progress.json
```

---

## Características

### ✅ Almacenamiento de progreso
- Persiste en `.progress.json` (archivo JSON simple, legible)
- Se guarda en la carpeta de actas (mismo nivel que los PDFs)
- Contiene: lista de procesados, timestamp, ruta de carpeta

### ✅ Excel incremental
- Se actualiza tras procesar cada archivo
- No necesita esperar a terminar todo
- Combina datos anteriores con nuevos automáticamente
- Evita duplicados inteligentemente

### ✅ Detección de reanudación
- Automática: al seleccionar carpeta, detecta `.progress.json`
- Con confirmación: pregunta al usuario antes de continuar
- Mensaje visual: indica que está "reanudando"

### ✅ Recuperación ante desconexiones
- API key sin créditos: pausa y permite cambiar clave (ya existía)
- Conexión perdida: checkpoint persiste, permite reanudar
- Cierre inesperado: datos en Excel se preservan

### ✅ Limpieza automática
- Checkpoint se elimina al completar exitosamente
- Aún persiste si hay errores (para permitir reanudar)

---

## Compatibilidad

- ✅ **Retrocompatible**: Todos los parámetros nuevos son opcionales
- ✅ **app.py (Streamlit)**: Sin cambios, sigue funcionando
- ✅ **app_pyqt.py**: Nuevo sistema activado automáticamente
- ✅ **Modos**: Compatible con OCR, Renombrar, y ambos

---

## Casos de uso

### Caso 1: Procesamiento de 100 actas, conexión cae en acta #45
```
Procesadas: 44 ✓ (en resultado_consolidado.xlsx)
Checkpoint: .progress.json con 44 archivos
Acción: Reanudar → procesa acta 45-100 → todo completo
```

### Caso 2: Cambio de API key a mitad de lote
```
Cuota agotada en archivo #30
Usuario ingresa nueva key
Sistema continúa desde archivo #30
```

### Caso 3: Error OCR en un archivo
```
Archivo problemático: no se registra en checkpoint
Excel: no aparece
Al reanudar: se reintenta este archivo
```

---

## Variables de Configuración

No hay variables que configurar. El sistema funciona automáticamente:
- Detecta `.progress.json` en la carpeta seleccionada
- Maneja todo sin intervención del usuario (excepto diálogo de confirmación)
- Parámetros son opcionales (backwards compatible)

---

## Testing recomendado

```
1. Procesa 10 archivos de una carpeta
2. Detén el proceso en mitad (Ctrl+C o cierra la app)
3. Verifica que .progress.json existe
4. Verifica que Excel tiene datos parciales
5. Reabre la app y selecciona la misma carpeta
6. Confirma que pregunta "Continuar"
7. Confirma que solo procesa archivos pendientes
8. Verifica que Excel final combina todo correctamente
```

---

## Notas técnicas

- **Thread-safe**: ProgressTracker opera en el thread worker, Excel se escribe desde ahí
- **Manejo de errores**: Si falla actualización de Excel, continúa (no bloquea procesamiento)
- **Deduplicación**: Por nombre de archivo, permite actualizar datos si se reprocesa
- **Performance**: Actualización incremental es más rápida que regenerar todo cada vez
