# Sistema de Reanudación y Checkpoints

## Descripción

Cuando procesas una carpeta completa con la aplicación de escritorio (PyQt), si la conexión se pierde, la aplicación se cierra inesperadamente, o ejecutas un "Alt+F4", el sistema ahora **guarda automáticamente el progreso** en un archivo `.progress.json`.

Al seleccionar la misma carpeta nuevamente, la aplicación **detecta que hay un procesamiento anterior incompleto** y te pregunta si deseas:
- **Continuar** desde donde se quedó (procesa solo los archivos pendientes)
- **Empezar de nuevo** (limpia el checkpoint y procesa toda la carpeta)

## Cómo funciona

### Durante el procesamiento

1. Después de procesar cada archivo exitosamente, se guarda:
   - El nombre del archivo en `.progress.json`
   - Se actualiza incrementalmente el archivo `resultado_consolidado.xlsx` con los datos procesados hasta el momento
   - Se guarda un timestamp del último progreso

### Si se interrumpe

- El archivo `.progress.json` permanece en la carpeta
- Los archivos ya procesados están guardados en `resultado_consolidado.xlsx`

### Al reanudar

1. Selecciona la misma carpeta con las actas
2. Se detecta automáticamente `.progress.json`
3. Un diálogo te pregunta: **¿Continuar o empezar de nuevo?**
   - Si eliges **Continuar**: se procesan solo los archivos que faltan
   - Si eliges **Empezar de nuevo**: `.progress.json` se elimina y comienza el procesamiento desde cero

### Finalización exitosa

Cuando se completa todo el procesamiento sin errores, `.progress.json` se elimina automáticamente.

## Archivos involucrados

- **`.progress.json`** - Checkpoint guardado en la carpeta de actas (se elimina al terminar)
- **`resultado_consolidado.xlsx`** - Se actualiza incrementalmente con cada archivo procesado
- **`src/utils/progress_tracker.py`** - Módulo que gestiona los checkpoints

## Ejemplo

```
Mi carpeta/
  ├── acta_001.pdf
  ├── acta_002.pdf
  ├── acta_003.pdf
  ├── .progress.json          ← Se crea automáticamente
  └── resultado_consolidado.xlsx ← Se actualiza tras cada archivo
```

Si falla el proceso después de acta_002.pdf:
- Al reanudar, solo se procesa acta_003.pdf
- El Excel ya tiene datos de acta_001 y acta_002

## Notas técnicas

- Los checkpoints son locales: cada carpeta tiene su propio `.progress.json`
- Solo se registran archivos **procesados exitosamente** (sin errores)
- Los archivos con error se vuelven a intentar en el siguiente procesamiento
- El sistema es compatible con modo OCR, Renombrar o ambos
