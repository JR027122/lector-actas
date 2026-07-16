# Sistema inteligente de digitalización de actas

Sistema de extracción de datos de actas de energía solar (PDF e imágenes) usando **Gemini vía OpenRouter**. Disponible como **aplicación de escritorio** y como **página web**.

## Características

- **Tres modos de operación:**
  - **Solo OCR** — extrae datos y genera Excel.
  - **Solo renombrar** — lee el acta y renombra a `NIU_dd-mm-aaaa_acta`.
  - **OCR + Renombrar** — Excel y renombrado en un solo paso.
- **Doble interfaz:** app de escritorio (PyQt6) y portal web (Streamlit).
- **IA vía OpenRouter:** elige entre **Gemini 2.5 Flash** (más preciso) o **Gemini 2.5 Flash Lite** (más económico) para texto manuscrito y tablas complejas.
- **Corrección automática y detección de datos dudosos:** ortografía de campos cerrados (Estado) y observaciones corregida por vocabulario técnico; filas de equipos con datos sospechosamente idénticos entre familias distintas se marcan en `Revisar_Manual`/`Motivo_Revision` en vez de darse por buenas.
- **Base de usuarios (opcional):** si un acta no tiene NIU visible (p. ej. registros fotográficos), se busca por **cédula, nombre o el nombre del archivo original** en un Excel/CSV que cargues, y se completa el NIU para renombrar (siempre validado contra la base cuando hay una cargada).
- **API key segura (escritorio):** almacén de credenciales de Windows vía `keyring`.
- **Interfaz profesional** con diseño moderno en web y escritorio.

## Requisitos previos

1. **Python 3.10 o superior** (recomendado 3.11 o 3.12).
2. **Poppler** (opcional, solo si usas conversión PDF con `pdf2image` en desarrollo).

## Instalación

```bash
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuración de la API key

| Plataforma | Cómo configurarla |
|---|---|
| **Escritorio** | Diálogo al primer arranco o botón **API key**. Se guarda en el Administrador de credenciales de Windows. |
| **Web** | Cada usuario la introduce en la barra lateral al entrar a la página. |
| **Desarrollo** | Archivo `.env` con `OPENROUTER_API_KEY=tu_clave` (ver `.env.example`). |

Consigue tu clave (de pago) en [OpenRouter](https://openrouter.ai/keys)

> Cada usuario debe usar **su propia API key** para controlar su propio consumo/crédito en OpenRouter.

## Cómo ejecutar

### Aplicación de escritorio (PyQt)

```bash
python app_pyqt.py
```

1. Elige el **modo de operación** (OCR, renombrar o ambos) y el **modelo de IA** (Flash o Flash Lite).
2. Selecciona **carpeta** (masivo) o **un acta** (individual).
3. (Opcional) Carga una **base de usuarios** (Excel/CSV con columnas `NIU`, `Cédula` y/o `Nombre`) para resolver el NIU de documentos que solo traen cédula, nombre o lo traen en el nombre del archivo.
4. Pulsa **Iniciar procesamiento**.

Resultados según el modo:

- Excel en la misma carpeta (`resultado_consolidado.xlsx` o `resultado_<nombre>.xlsx`).
- Renombrado directo del archivo en disco (`NIU_dd-mm-aaaa_acta.ext`).

### Página web (Streamlit)

```bash
python -m streamlit run app.py
```

Abre `http://localhost:8501`. Cualquier persona con acceso a la URL puede:

1. Pegar su API key en la barra lateral.
2. Elegir el modo de operación y el modelo de IA (Flash o Flash Lite).
3. (Opcional) Subir la **base de usuarios** (Excel/CSV) en la barra lateral.
4. Subir actas (PDF, JPG, PNG).
5. Descargar **Excel** y/o **archivos renombrados** (ZIP si son varios).

#### Base de usuarios para resolver el NIU

Para actas o registros fotográficos **sin NIU visible**:

| NIU | Cedula | Nombre |
|-----|--------|--------|
| 1001 | 12345678 | Juan Pérez Gómez |
| 1002 | 98765432 | María López García |

- Acepta nombres de columna flexibles (`NIU`/`Código`, `Cédula`/`CC`/`Documento`, `Nombre`/`Cliente`...).
- La búsqueda por cédula ignora puntos y espacios; la de nombre tolera errores leves de OCR.
- Si el documento ya trae NIU, la base no lo modifica.

#### Publicar en internet

Guía paso a paso en **[DEPLOY_STREAMLIT.md](DEPLOY_STREAMLIT.md)** (Streamlit Cloud gratis o servidor propio).

Resumen rápido:

1. Sube el proyecto a **GitHub** (Streamlit Cloud no lee Azure DevOps directamente).
2. Entra en [share.streamlit.io](https://share.streamlit.io) → **New app** → archivo `app.py`.
3. Cada usuario pega **su propia API key** en la barra lateral (recomendado).

#### Seguridad de la API key

| Plataforma | Nivel | Detalle |
|---|---|---|
| **Escritorio** | Alto | Key cifrada en Credential Manager de Windows (`keyring`). |
| **Web (sidebar)** | Medio-alto | Key solo en memoria de sesión, HTTPS, botón para borrarla. Adecuado para equipo interno. |
| **Web (secrets del servidor)** | Medio | Una key para todos; solo para pruebas o un solo operador. |

En la web, expande **“Seguridad de tu API key”** en la barra lateral para ver el detalle completo.

## Cómo generar el `.exe` (Windows)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m PyInstaller --clean -y LectorActas.spec
```

El ejecutable queda en `dist\LectorActas.exe`. **No incluye API key**; cada usuario la configura al primer uso.

Alternativa: `python -m PyInstaller --clean -y app_pyqt.spec` → `dist\app_pyqt.exe`.

## Estructura del proyecto

- `app.py` — portal web Streamlit.
- `app_pyqt.py` — aplicación de escritorio PyQt6.
- `.streamlit/config.toml` — tema visual de la web.
- `src/core/` — procesamiento, modos y llamadas a OpenRouter.
  - `processing_modes.py` — definición de los 3 modos.
  - `document_processor.py` — lógica unificada de procesamiento.
  - `openrouter_processor.py` — llamadas a la IA vía OpenRouter (Flash / Flash Lite).
- `src/utils/` — renombrado, Excel, API key segura, corrección/detección posterior (`post_procesado.py`), NIU (`niu_lookup.py`).
- `scripts/comparar_modelos.py` — compara Flash vs Flash Lite sobre un acta real (costos y campos extraídos).
- `scripts/corregir_excel.py` — corrige coordenadas y ortografía en un Excel consolidado ya exportado.
- `LectorActas.spec` / `app_pyqt.spec` — empaquetado con PyInstaller.
