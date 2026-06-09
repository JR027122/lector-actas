# Despliegue web — Lector de Actas

Guía para publicar la app en internet con **Streamlit Cloud** (gratis) o en un **servidor propio**.

---

## Opción A: Streamlit Cloud (recomendada, gratis)

Streamlit Cloud despliega directamente desde **GitHub** o **GitLab**. No soporta Azure DevOps de forma nativa; si tu código está en Azure, primero súbelo a GitHub (repo nuevo o espejo).

### 1. Subir el proyecto a GitHub

En la carpeta del proyecto (solo esta carpeta, no todo el usuario):

```powershell
cd "C:\Users\Usuario\Documents\Desarrollos Juan\Proyecto OCR-1 v2"
git init
git add .
git commit -m "Lector de Actas: web + escritorio"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/lector-actas.git
git push -u origin main
```

**Importante:** confirma que `.env` y `.streamlit/secrets.toml` **no** estén en el commit (están en `.gitignore`).

### 2. Crear la app en Streamlit Cloud

1. Entra en [share.streamlit.io](https://share.streamlit.io) con tu cuenta de GitHub.
2. **New app** → elige el repositorio y la rama `main`.
3. **Main file path:** `app.py`
4. **Advanced settings → Python version:** 3.11 o 3.12.
5. Deploy.

En unos minutos tendrás una URL pública tipo:

`https://lector-actas-xxxxx.streamlit.app`

### 3. Secrets de seguridad (recomendado en producción)

En Streamlit Cloud → **Settings → Secrets**, pega (adaptado desde `.streamlit/secrets.toml.example`):

```toml
# Genera con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_ENCRYPTION_KEY = "tu_clave_fernet_generada"

SESSION_TIMEOUT_MINUTES = 30

# Solo quien conozca esta contraseña puede abrir la app
APP_PASSWORD = "contraseña_interna_del_equipo"

# NO actives la key compartida del servidor para equipos
ALLOW_SERVER_GEMINI_KEY = false
```

**Cada usuario** sigue pegando **su propia API key de Gemini** en la barra lateral. La contraseña `APP_PASSWORD` solo evita que cualquier persona de internet entre a la app.

**Modo admin (solo tú):** si eres el único usuario, puedes poner `ALLOW_SERVER_GEMINI_KEY = true` y `GEMINI_API_KEY = "..."` para no pedir key en la sidebar.

### 4. Actualizar la app

Cada `git push` a `main` vuelve a desplegar automáticamente.

---

## Opción B: Servidor propio (VPS, Azure VM, etc.)

Útil si quieres control total o ya tienes infraestructura.

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Detrás de **nginx** o **Azure Application Gateway** con HTTPS. No expongas el puerto 8501 sin proxy SSL.

Variables de entorno opcionales:

```bash
export GEMINI_API_KEY="..."   # solo si quieres key centralizada
```

---

## Seguridad de la API key — comparativa

| | Escritorio (.exe) | Web (mejorada) | Web (key en secrets) |
|---|---|---|---|
| **Dónde vive la key** | Credential Manager (Windows) | Sesión cifrada con Fernet | Secrets de Streamlit |
| **Persistencia** | Sí, hasta borrarla | Expira por inactividad (~30 min) | Permanente en servidor |
| **Acceso a la app** | Solo tu PC | HTTPS + `APP_PASSWORD` opcional | Igual |
| **Nivel** | **Alto** | **Medio-alto** (uso interno) | Medio (no para equipos) |

### Capas de seguridad en la web (implementadas)

1. **HTTPS** — Streamlit Cloud cifra el tráfico.
2. **APP_PASSWORD** — muro de acceso; la URL pública no basta para usar la app.
3. **Cifrado Fernet** — la key del usuario no se guarda en texto plano en `session_state`.
4. **Formulario con clear_on_submit** — la key no queda visible en el campo tras guardar.
5. **Expiración por inactividad** — la key se borra sola tras X minutos.
6. **Key personal por usuario** — cada uno usa su cuota de Gemini.
7. **ALLOW_SERVER_GEMINI_KEY = false** por defecto — evita key compartida accidental.

### Buenas prácticas adicionales

1. **Una API key por persona** en equipos de 3–4 usuarios.
2. **Restringe y rota keys** en [Google AI Studio](https://aistudio.google.com/apikey).
3. **No compartas** `APP_PASSWORD` ni `SESSION_ENCRYPTION_KEY` por chat/correo.
4. **Máxima seguridad:** app de escritorio, o un **backend propio** donde la key nunca llega al navegador (requiere desarrollo extra).

---

## Checklist antes de publicar

- [ ] `.env` no está en Git
- [ ] `requirements.txt` incluye todas las dependencias
- [ ] Probaste `streamlit run app.py` en local
- [ ] Configuraste `SESSION_ENCRYPTION_KEY` y `APP_PASSWORD` en Streamlit Secrets
- [ ] `ALLOW_SERVER_GEMINI_KEY` está en `false` si hay varios usuarios
