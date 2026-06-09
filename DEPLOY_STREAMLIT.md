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

### 3. API key en producción

**Para varios usuarios (recomendado):** no configures secrets en el servidor. Cada persona pega su key en la barra lateral al entrar.

**Solo tú usarás la app:** en Streamlit Cloud → **Settings → Secrets** puedes pegar:

```toml
GEMINI_API_KEY = "tu_clave_aqui"
```

Eso usa la clave del servidor para todos los visitantes. Úsalo solo en despliegues privados o de prueba.

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

| | Escritorio (.exe) | Web (sidebar) | Web (secrets del servidor) |
|---|---|---|---|
| **Dónde vive la key** | Credential Manager de Windows (cifrado SO) | RAM de la sesión Streamlit | Secrets de Streamlit Cloud |
| **Persistencia** | Sí, hasta que la borres | No (se pierde al cerrar sesión) | Sí, en el servidor |
| **Quién la ve** | Solo tu usuario Windows | Tú + proceso del servidor durante la sesión | Admin del deploy + todos los usuarios comparten cuota |
| **Ideal para** | Uso diario en PC | Equipo remoto, cada uno con su key | Pruebas / un solo operador |
| **Nivel de seguridad** | Alto | Medio-alto (aceptable para uso interno) | Medio (no compartir en producción con muchos usuarios) |

### Qué hace la app para protegerte (web)

- Campo tipo **password** (no se muestra en pantalla).
- La key **no se guarda en disco** ni en cookies del navegador.
- Se pasa **directamente** a Gemini en cada petición, sin escribirla en `os.environ`.
- Botón **“Borrar clave de la sesión”** en la barra lateral.

### Buenas prácticas

1. **Una API key por persona** en equipos de 3–4 usuarios.
2. **Restringe la API key en Google AI Studio** (límites por aplicación/referrer si Google lo permite en tu cuenta).
3. **Revoca** keys que hayan filtrado en [Google AI Studio](https://aistudio.google.com/apikey).
4. Para datos muy sensibles, prioriza la **app de escritorio** o un backend propio que no exponga la key al cliente.

---

## Checklist antes de publicar

- [ ] `.env` no está en Git
- [ ] `requirements.txt` incluye todas las dependencias
- [ ] Probaste `streamlit run app.py` en local
- [ ] Decidiste si cada usuario lleva su key o usas secrets centralizados
- [ ] (Opcional) App privada en Streamlit Cloud con autenticación de equipo
