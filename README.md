# Sistema inteligente de digitalización de actas

Sistema de extracción de datos de actas de energía solar (PDF e imágenes) usando **Google Gemini**. Disponible como **aplicación de escritorio** y como **página web**.

## Características

- **Tres modos de operación:**
  - **Solo OCR** — extrae datos y genera Excel.
  - **Solo renombrar** — lee el acta y renombra a `NIU_dd-mm-aaaa_acta`.
  - **OCR + Renombrar** — Excel y renombrado en un solo paso.
- **Doble interfaz:** app de escritorio (PyQt6) y portal web (Streamlit).
- **IA:** modelo Gemini para texto manuscrito y tablas complejas.
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
| **Desarrollo** | Archivo `.env` con `GEMINI_API_KEY=tu_clave` (ver `.env.example`). |

Clave gratuita: [Google AI Studio](https://aistudio.google.com/apikey)

> Cada usuario debe usar **su propia API key** para no saturar la cuota gratuita de Gemini.

## Cómo ejecutar

### Aplicación de escritorio (PyQt)

```bash
python app_pyqt.py
```

1. Elige el **modo de operación** (OCR, renombrar o ambos).
2. Selecciona **carpeta** (masivo) o **un acta** (individual).
3. Pulsa **Iniciar procesamiento**.

Resultados según el modo:

- Excel en la misma carpeta (`resultado_consolidado.xlsx` o `resultado_<nombre>.xlsx`).
- Renombrado directo del archivo en disco (`NIU_dd-mm-aaaa_acta.ext`).

### Página web (Streamlit)

```bash
python -m streamlit run app.py
```

Abre `http://localhost:8501`. Cualquier persona con acceso a la URL puede:

1. Pegar su API key en la barra lateral.
2. Elegir el modo de operación.
3. Subir actas (PDF, JPG, PNG).
4. Descargar **Excel** y/o **archivos renombrados** (ZIP si son varios).

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
- `src/core/` — procesamiento, modos y Gemini.
  - `processing_modes.py` — definición de los 3 modos.
  - `document_processor.py` — lógica unificada de procesamiento.
- `src/utils/` — renombrado, Excel, API key segura.
- `LectorActas.spec` / `app_pyqt.spec` — empaquetado con PyInstaller.
