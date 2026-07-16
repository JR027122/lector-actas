# Seguridad — API keys

## Si OpenRouter avisó que tu key está expuesta

1. **Revoca la key de inmediato** en [OpenRouter → Keys](https://openrouter.ai/keys).
2. **Crea una key nueva** y actualízala en:
   - Tu archivo local `.env` (nunca lo subas a Git).
   - Streamlit Cloud → Settings → Secrets (si usabas la misma key ahí).
   - La app de escritorio (botón **API key** o Credential Manager).
3. La key antigua puede seguir visible en **commits huérfanos** de GitHub (URLs con hash antiguo) aunque borres el archivo de `main`. Por eso hay que **revocar la key** y, si el aviso persiste, **eliminar y recrear el repositorio** en GitHub (ver abajo).

## Reglas del proyecto

- **Nunca** pegues API keys en archivos `.py`, `.md`, `.spec` ni commits.
- Usa `.env` en local (está en `.gitignore`).
- En la web, cada usuario ingresa su propia key en la sesión cifrada.
- No subas la carpeta `scripts/` con utilidades personales al repo del OCR.

## Patrones prohibidos en Git

```
sk-or-v1-...           # OpenRouter API keys
OPENROUTER_API_KEY=... # en archivos que no sean .env.example con placeholder
```

Si necesitas verificar la key de OpenRouter en local:

```powershell
# Con .env configurado
python -c "import os; from dotenv import load_dotenv; from openai import OpenAI; load_dotenv(); c=OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY')); print('OK')"
```

## Commits huérfanos en GitHub (por qué sigue alertando)

Si hiciste `git push --force`, la rama `main` queda limpia, pero GitHub **conserva commits viejos** accesibles por su hash (ej. `.../commit/29d4bba...`). OpenRouter y bots pueden seguir leyendo la key ahí.

**Solución definitiva:**

1. Revoca la key en OpenRouter (obligatorio).
2. En GitHub → repo **lector-actas** → **Settings** → **Danger zone** → **Delete this repository**.
3. Crea un repo nuevo con el mismo nombre (`lector-actas`).
4. En tu PC:
   ```powershell
   cd "C:\Users\Usuario\Documents\Desarrollos Juan\Proyecto OCR-1 v2"
   git remote set-url origin https://github.com/JR027122/lector-actas.git
   git push -u origin main
   ```
5. Reconecta la app en [Streamlit Cloud](https://share.streamlit.io) al repo nuevo y vuelve a pegar los Secrets.
