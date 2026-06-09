import io
import os
import tempfile
import time
import zipfile

import pandas as pd
import streamlit as st
from PIL import Image

from src.core.document_processor import process_document
from src.core.processing_modes import MODE_OPTIONS, OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.file_renamer import construir_nuevo_nombre

st.set_page_config(
    page_title="Lector de Actas | OCR Inteligente",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #0ea5e9 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 40px rgba(37, 99, 235, 0.25);
    }
    .main-header h1 { color: white !important; margin: 0; font-size: 2rem; font-weight: 700; }
    .main-header p { color: rgba(255,255,255,0.9) !important; margin: 0.5rem 0 0 0; font-size: 1.05rem; }
    .mode-card {
        background: #ffffff;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.5rem;
        transition: border-color 0.2s;
    }
    .mode-card:hover { border-color: #2563eb; }
    .metric-box {
        background: #f8fafc;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        border: 1px solid #e2e8f0;
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    div[data-testid="stSidebar"] * { color: #f1f5f9 !important; }
    div[data-testid="stSidebar"] input { color: #0f172a !important; background: #fff !important; }
    .stDownloadButton button {
        background: linear-gradient(135deg, #2563eb, #0ea5e9) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)


def _configurar_api_key():
    """Gestiona la API key solo en memoria de sesión (web). No escribe en disco."""
    if "gemini_api_key" not in st.session_state:
        st.session_state.gemini_api_key = ""

    st.sidebar.markdown("### Configuración")

    clave_input = st.sidebar.text_input(
        "API key de Gemini",
        type="password",
        placeholder="Pega tu clave de Google AI Studio",
        help="Se usa solo durante tu sesión. No se guarda en el navegador ni en el servidor.",
        key="api_key_input",
    )
    if clave_input.strip():
        st.session_state.gemini_api_key = clave_input.strip()

    if st.session_state.gemini_api_key:
        st.sidebar.success("Clave activa en esta sesión.")
        if st.sidebar.button("Borrar clave de la sesión", use_container_width=True):
            st.session_state.gemini_api_key = ""
            if "api_key_input" in st.session_state:
                del st.session_state["api_key_input"]
            st.rerun()
        return st.session_state.gemini_api_key

    # Fallback opcional: clave del servidor (despliegue privado con secrets.toml)
    try:
        clave_servidor = st.secrets.get("GEMINI_API_KEY", "").strip()
        if clave_servidor:
            st.sidebar.warning(
                "Usando la API key configurada en el servidor. "
                "Todos los visitantes comparten la misma cuota."
            )
            return clave_servidor
    except Exception:
        pass

    st.sidebar.warning("Introduce tu API key para continuar.")
    return None


def _panel_seguridad():
    with st.sidebar.expander("Seguridad de tu API key"):
        st.markdown("""
**Escritorio (.exe)** — Más seguro para un solo usuario  
La clave se guarda cifrada en el **Administrador de credenciales de Windows** (`keyring`). Solo tu usuario de Windows puede leerla.

**Web (esta página)** — Seguro para uso en equipo con matices  
- La clave viaja por **HTTPS** hasta el servidor de la app.  
- Vive **solo en memoria** durante tu sesión; no se escribe en disco ni en cookies.  
- Cada persona debe usar **su propia key** (cuota propia de Gemini).  
- Al cerrar la pestaña o borrar la sesión, la clave desaparece.

**Riesgos a tener en cuenta**  
- Quien administre el servidor donde corre la app *podría* interceptar tráfico o memoria (igual que cualquier SaaS).  
- No pegues la key en chats, capturas ni correos.  
- Si revocas la key en Google AI Studio, deja de funcionar al instante.

**Recomendación**  
Uso diario en oficina → **app de escritorio**.  
Acceso remoto ocasional → **web con key personal** por usuario.
        """)


def _guardar_temporal(uploaded_file) -> str:
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


def _nombre_descarga(data: dict, nombre_original: str) -> str:
    sugerido = data.get("__nombre_sugerido__") or construir_nuevo_nombre(
        data.get("NIU"), data.get("Fecha"), os.path.splitext(nombre_original)[1]
    )
    return sugerido or nombre_original


st.markdown("""
<div class="main-header">
    <h1>Lector de Actas</h1>
    <p>Digitalización inteligente de actas de mantenimiento con Google Gemini</p>
</div>
""", unsafe_allow_html=True)

api_key = _configurar_api_key()
_panel_seguridad()

st.sidebar.markdown("---")
st.sidebar.markdown("### Acerca de")
st.sidebar.info(
    "Plataforma web para extraer datos de actas técnicas, exportar Excel "
    "y/o renombrar archivos con el formato **NIU_dd-mm-aaaa_acta**."
)
st.sidebar.markdown("[Obtener API key gratuita](https://aistudio.google.com/apikey)")

col_mode, col_upload = st.columns([1, 1.2], gap="large")

with col_mode:
    st.markdown("#### Modo de operación")
    mode_labels = {k: f"{v['icon']} {v['label']}" for k, v in MODE_OPTIONS.items()}
    mode = st.radio(
        "Selecciona qué deseas hacer",
        options=list(MODE_OPTIONS.keys()),
        format_func=lambda k: mode_labels[k],
        index=2,
        label_visibility="collapsed",
    )
    st.markdown(
        f'<div class="mode-card"><strong>{MODE_OPTIONS[mode]["label"]}</strong><br>'
        f'<span style="color:#64748b;">{MODE_OPTIONS[mode]["description"]}</span></div>',
        unsafe_allow_html=True,
    )

with col_upload:
    st.markdown("#### Documentos")
    uploaded_files = st.file_uploader(
        "Arrastra actas aquí (PDF, JPG, PNG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

if uploaded_files:
    st.markdown("---")
    if st.button("Iniciar procesamiento", type="primary", use_container_width=True, disabled=not api_key):
        resultados = []
        archivos_renombrados = []
        inicio = time.time()

        progress = st.progress(0, text="Preparando...")
        status = st.empty()

        for i, uploaded in enumerate(uploaded_files):
            status.info(f"Procesando **{uploaded.name}** ({i + 1} de {len(uploaded_files)})")
            temp_path = _guardar_temporal(uploaded)

            try:
                data = process_document(temp_path, uploaded.name, mode, api_key=api_key)
                data["__archivo_original__"] = uploaded.name

                if renombra_archivo(mode) and "Error" not in data:
                    nombre_final = _nombre_descarga(data, uploaded.name)
                    with open(temp_path, "rb") as f:
                        archivos_renombrados.append((nombre_final, f.read()))

                resultados.append(data)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            progress.progress((i + 1) / len(uploaded_files), text=f"{i + 1} / {len(uploaded_files)} actas")

        duracion = time.time() - inicio
        progress.progress(1.0, text="Completado")
        status.success(f"Procesamiento finalizado en {duracion:.1f} s")

        ok = [r for r in resultados if "Error" not in r]
        err = [r for r in resultados if "Error" in r]

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(
                f'<div class="metric-box"><h3 style="margin:0;color:#2563eb;">{len(ok)}</h3>'
                f'<p style="margin:0;color:#64748b;">Procesados</p></div>',
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f'<div class="metric-box"><h3 style="margin:0;color:#dc2626;">{len(err)}</h3>'
                f'<p style="margin:0;color:#64748b;">Con error</p></div>',
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                f'<div class="metric-box"><h3 style="margin:0;color:#059669;">{len(archivos_renombrados)}</h3>'
                f'<p style="margin:0;color:#64748b;">Listos para renombrar</p></div>',
                unsafe_allow_html=True,
            )

        if exporta_excel(mode) and ok:
            st.markdown("#### Datos extraídos")
            df = ordenar_dataframe(pd.DataFrame([limpiar_registro(r) for r in ok]))
            st.dataframe(df, use_container_width=True, hide_index=True)

            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine="openpyxl")
            buffer.seek(0)
            st.download_button(
                "Descargar Excel consolidado",
                data=buffer,
                file_name="resultado_actas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        if renombra_archivo(mode) and archivos_renombrados:
            st.markdown("#### Archivos renombrados")
            if len(archivos_renombrados) == 1:
                nombre, contenido = archivos_renombrados[0]
                st.download_button(
                    f"Descargar {nombre}",
                    data=contenido,
                    file_name=nombre,
                    use_container_width=True,
                )
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for nombre, contenido in archivos_renombrados:
                        zf.writestr(nombre, contenido)
                zip_buffer.seek(0)
                st.download_button(
                    "Descargar ZIP con archivos renombrados",
                    data=zip_buffer,
                    file_name="actas_renombradas.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        if err:
            st.markdown("#### Errores")
            for r in err:
                st.error(f"**{r.get('Archivo', 'Archivo')}**: {r.get('Error', 'Error desconocido')}")

        with st.expander("Vista previa del primer documento"):
            first = uploaded_files[0]
            if first.type == "application/pdf":
                st.info("Vista previa PDF no disponible en navegador. Descarga el archivo procesado.")
            else:
                st.image(Image.open(first), use_container_width=True)

elif not api_key:
    st.info("Configura tu API key en la barra lateral para comenzar.")
else:
    st.info("Sube uno o más actas para iniciar el procesamiento.")
