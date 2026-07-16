import io
import os
import tempfile
import time
import zipfile

import pandas as pd
import streamlit as st
from PIL import Image

from src.core.document_processor import process_document
from src.core.openrouter_processor import MODELO_POR_DEFECTO, MODELOS_DISPONIBLES
from src.core.processing_modes import MODE_OPTIONS, OCR_AND_RENAME, exporta_excel, renombra_archivo
from src.utils.excel_export import limpiar_registro, ordenar_dataframe
from src.utils.file_renamer import construir_nuevo_nombre
from src.utils.niu_lookup import cargar_base_usuarios
from src.utils.web_session_security import (
    clear_user_api_key,
    has_user_api_key,
    logout_app,
    require_app_login,
    resolve_web_api_key,
    save_user_api_key,
)

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

require_app_login()


def _configurar_api_key():
    """API key cifrada en sesión + formulario que no persiste el valor en el widget."""
    st.sidebar.markdown("### Configuración")

    if has_user_api_key():
        st.sidebar.success("Clave activa (cifrada en sesión).")
        try:
            minutos = int(st.secrets.get("SESSION_TIMEOUT_MINUTES", 30))
        except Exception:
            minutos = 30
        st.sidebar.caption(f"Se borra automáticamente tras {minutos} min sin actividad.")
        if st.sidebar.button("Borrar clave de la sesión", use_container_width=True):
            clear_user_api_key()
            st.rerun()
        return resolve_web_api_key()

    with st.sidebar.form("api_key_form", clear_on_submit=True):
        clave_input = st.text_input(
            "API key de OpenRouter",
            type="password",
            placeholder="Pega tu clave de openrouter.ai",
            help="Se cifra en la sesión del servidor. No queda en el navegador.",
        )
        if st.form_submit_button("Guardar clave en sesión", use_container_width=True):
            if clave_input.strip():
                save_user_api_key(clave_input.strip())
                st.rerun()
            else:
                st.warning("Introduce una clave válida.")

    clave_servidor = resolve_web_api_key()
    if clave_servidor and not has_user_api_key():
        st.sidebar.warning("Usando API key del servidor (modo admin).")
        return clave_servidor

    st.sidebar.warning("Guarda tu API key para continuar.")
    return None


def _configurar_modelo() -> str:
    st.sidebar.markdown("### Modelo de IA")
    opciones = list(MODELOS_DISPONIBLES.keys())
    indice_defecto = opciones.index(MODELO_POR_DEFECTO) if MODELO_POR_DEFECTO in opciones else 0
    modelo = st.sidebar.selectbox(
        "Modelo a utilizar",
        options=opciones,
        format_func=lambda slug: MODELOS_DISPONIBLES.get(slug, slug),
        index=indice_defecto,
        label_visibility="collapsed",
    )
    st.sidebar.caption(
        "Flash es más preciso; Flash Lite es más económico pero puede cometer más errores "
        "(se corrigen ortografía y filas sospechosas automáticamente, ver 'Revisar_Manual')."
    )
    return modelo


def _panel_seguridad():
    with st.sidebar.expander("Seguridad de tu API key"):
        st.markdown("""
**Capas activas en la web**
- **HTTPS** en Streamlit Cloud.
- **Cifrado Fernet** de la key en la sesión (no texto plano en memoria de Streamlit).
- **Formulario** que no deja la key pegada en el campo tras guardar.
- **Expiración automática** por inactividad.
- **Contraseña de equipo** opcional (`APP_PASSWORD` en secrets).

**Escritorio (.exe)** — Máxima seguridad
Key en el **Administrador de credenciales de Windows** (`keyring`).

**Buenas prácticas en OpenRouter**
1. Crea **una key por persona**.
2. En [OpenRouter](https://openrouter.ai/keys), **limita el gasto** de la key (límite de uso / revocación rápida).
3. **Revoca** de inmediato cualquier key que hayas compartido por error.

**Límite inherente de apps web**
La key debe llegar al servidor para llamar a OpenRouter. Un atacante con control del servidor podría interceptarla; por eso conviene **APP_PASSWORD** + keys personales + uso interno.
        """)

    if st.sidebar.button("Cerrar sesión de la app", use_container_width=True):
        logout_app()
        st.rerun()


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
    <p>Digitalización inteligente de actas de mantenimiento con IA (OpenRouter)</p>
</div>
""", unsafe_allow_html=True)

api_key = _configurar_api_key()
modelo_elegido = _configurar_modelo()
_panel_seguridad()

st.sidebar.markdown("---")
st.sidebar.markdown("### Base de usuarios (opcional)")
st.sidebar.caption(
    "Excel/CSV con columnas **NIU**, **Cédula** y/o **Nombre**. "
    "Si un acta no tiene NIU visible, se busca por cédula o nombre."
)
archivo_base = st.sidebar.file_uploader(
    "Subir base de usuarios",
    type=["xlsx", "xls", "csv"],
    label_visibility="collapsed",
)
user_db = None
if archivo_base is not None:
    try:
        user_db = cargar_base_usuarios(archivo_base)
        st.sidebar.success(f"Base cargada: {user_db.total} usuarios.")
    except Exception as e:
        st.sidebar.error(f"No se pudo cargar la base: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Acerca de")
st.sidebar.info(
    "Plataforma web para extraer datos de actas técnicas, exportar Excel "
    "y/o renombrar archivos con el formato **NIU_dd-mm-aaaa_acta**."
)
st.sidebar.markdown("[Obtener API key de OpenRouter](https://openrouter.ai/keys)")

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
                data = process_document(
                    temp_path, uploaded.name, mode,
                    api_key=api_key, user_db=user_db, modelo=modelo_elegido,
                )
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
        revisar = [r for r in ok if r.get("Revisar_Manual") == "Sí"]

        m1, m2, m3, m4 = st.columns(4)
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
        with m4:
            st.markdown(
                f'<div class="metric-box"><h3 style="margin:0;color:#d97706;">{len(revisar)}</h3>'
                f'<p style="margin:0;color:#64748b;">Para revisar</p></div>',
                unsafe_allow_html=True,
            )

        if revisar:
            st.warning(
                f"{len(revisar)} documento(s) quedaron marcados para revisión manual "
                "(posible dato dudoso o inventado por el modelo). Filtra la columna "
                "**Revisar_Manual** en el Excel para verlos."
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
