"""
Seguridad de la API key en la app web (Streamlit).

- Cifrado Fernet en session_state (no texto plano).
- Expiración por inactividad.
- Acceso opcional con contraseña de equipo (secrets).
"""

from __future__ import annotations

import base64
import hashlib
import time

import streamlit as st
from cryptography.fernet import Fernet, InvalidToken

# Minutos sin actividad antes de borrar la key de la sesión
SESSION_TIMEOUT_MINUTES = 30

_ENCRYPTED_KEY = "_encrypted_api_key"
_LAST_ACTIVITY = "_key_last_activity"
_APP_AUTH = "app_authenticated"


def _session_timeout_seconds() -> int:
    try:
        minutos = int(st.secrets.get("SESSION_TIMEOUT_MINUTES", SESSION_TIMEOUT_MINUTES))
        return max(5, minutos) * 60
    except Exception:
        return SESSION_TIMEOUT_MINUTES * 60


def _fernet() -> Fernet:
    """Clave de cifrado del servidor (secrets) o efímera en desarrollo local."""
    if "SESSION_ENCRYPTION_KEY" in st.secrets:
        raw = st.secrets["SESSION_ENCRYPTION_KEY"].encode("utf-8")
    else:
        if "_dev_fernet_seed" not in st.session_state:
            st.session_state._dev_fernet_seed = Fernet.generate_key().decode()
        raw = st.session_state._dev_fernet_seed.encode("utf-8")

    derived = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(derived)


def _touch_activity():
    st.session_state[_LAST_ACTIVITY] = time.time()


def _session_expired() -> bool:
    last = st.session_state.get(_LAST_ACTIVITY)
    if last is None:
        return False
    return (time.time() - last) > _session_timeout_seconds()


def save_user_api_key(api_key: str):
    """Guarda la API key cifrada en la sesión."""
    token = _fernet().encrypt(api_key.strip().encode("utf-8"))
    st.session_state[_ENCRYPTED_KEY] = token.decode("ascii")
    _touch_activity()


def clear_user_api_key():
    st.session_state.pop(_ENCRYPTED_KEY, None)
    st.session_state.pop(_LAST_ACTIVITY, None)
    st.session_state.pop("api_key_input", None)


def has_user_api_key() -> bool:
    if _session_expired():
        clear_user_api_key()
        return False
    return bool(st.session_state.get(_ENCRYPTED_KEY))


def get_user_api_key() -> str | None:
    """Devuelve la key descifrada o None si expiró / no existe."""
    if _session_expired():
        clear_user_api_key()
        return None

    token = st.session_state.get(_ENCRYPTED_KEY)
    if not token:
        return None

    try:
        plain = _fernet().decrypt(token.encode("ascii")).decode("utf-8")
        _touch_activity()
        return plain.strip() or None
    except InvalidToken:
        clear_user_api_key()
        return None


def get_server_api_key() -> str | None:
    """
    Key centralizada del servidor (secrets). Desactivada por defecto en producción
    salvo que ALLOW_SERVER_OPENROUTER_KEY = true en secrets.
    """
    try:
        if not st.secrets.get("ALLOW_SERVER_OPENROUTER_KEY", False):
            return None
        key = st.secrets.get("OPENROUTER_API_KEY", "").strip()
        return key or None
    except Exception:
        return None


def resolve_web_api_key() -> str | None:
    return get_user_api_key() or get_server_api_key()


def require_app_login():
    """
    Muro de acceso opcional. Configura APP_PASSWORD en secrets de Streamlit Cloud.
    Si no está definido, la app es pública (como antes).
    """
    try:
        app_password = st.secrets.get("APP_PASSWORD", "").strip()
    except Exception:
        app_password = ""

    if not app_password:
        return

    if st.session_state.get(_APP_AUTH):
        return

    st.markdown("## Acceso restringido")
    st.caption("Esta aplicación es de uso interno. Introduce la contraseña del equipo.")

    with st.form("login_form", clear_on_submit=False):
        pwd = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)

    if submitted:
        if pwd == app_password:
            st.session_state[_APP_AUTH] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    st.stop()


def logout_app():
    st.session_state.pop(_APP_AUTH, None)
    clear_user_api_key()
