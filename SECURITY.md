# Seguridad — API keys

## Si Google avisó que tu key está expuesta

1. **Revoca la key de inmediato** en [Google AI Studio → API keys](https://aistudio.google.com/apikey).
2. **Crea una key nueva** y actualízala en:
   - Tu archivo local `.env` (nunca lo subas a Git).
   - Streamlit Cloud → Settings → Secrets (si usabas la misma key ahí).
   - La app de escritorio (botón **API key** o Credential Manager).
3. La key antigua quedó en el historial público de GitHub; revocarla es **obligatorio** aunque limpiemos el repo.

## Reglas del proyecto

- **Nunca** pegues API keys en archivos `.py`, `.md`, `.spec` ni commits.
- Usa `.env` en local (está en `.gitignore`).
- En la web, cada usuario ingresa su propia key en la sesión cifrada.
- No subas la carpeta `scripts/` con utilidades personales al repo del OCR.

## Patrones prohibidos en Git

```
AIzaSy...          # Google API keys
GEMINI_API_KEY=... # en archivos que no sean .env.example con placeholder
```

Si necesitas listar modelos de Gemini en local:

```powershell
# Con .env configurado
python -c "import os; from dotenv import load_dotenv; from google import genai; load_dotenv(); c=genai.Client(api_key=os.getenv('GEMINI_API_KEY')); print('OK')"
```
