"""
Almacenamiento de la API key de Gemini fuera del texto plano.

En Windows se usa el Administrador de credenciales (Credential Manager),
donde el sistema operativo cifra el secreto. No es invulnerable a un atacante
con control total de la máquina del usuario, pero evita dejar la clave en un
archivo .env legible junto al ejecutable.
"""

import os

SERVICE_NAME = "LectorActas_Gemini"
ACCOUNT_NAME = "GEMINI_API_KEY"


def load_stored_api_key():
    """Devuelve la clave guardada o None si no existe."""
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
    except Exception:
        return None


def save_api_key(api_key: str):
    """Guarda la clave en el almacén seguro del sistema."""
    import keyring

    keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, api_key.strip())


def delete_stored_api_key():
    """Elimina la clave del almacén (p. ej. al cambiar de cuenta)."""
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
    except Exception:
        pass


def resolve_api_key():
    """
    Orden: variable de entorno (desarrollo / .env) → almacén del sistema.
    Devuelve la clave sin espacios o None.
    """
    env_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if env_key:
        return env_key
    stored = (load_stored_api_key() or "").strip()
    return stored or None
