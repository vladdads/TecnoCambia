# Tecnocambia — Backend (Flask)

API REST (`/api/*`), subida de archivos (`/uploads`), plantillas HTML clásicas (`/messages`, `/auth/*`, etc.) y SQLite.

- **Producción:** ver [DEPLOY.md](DEPLOY.md) (Render).
- **Variables:** copia `env.example` a `.env` en esta carpeta.

## Arranque local

```bash
python -m venv .venv
pip install -r requirements.txt
copy env.example .env
python app.py
```

Comprueba `http://127.0.0.1:3000/api/meta`.

Con frontend separado, define en `.env`:

```env
FRONTEND_ORIGIN=http://localhost:4200
CORS_ALLOWED_ORIGINS=http://localhost:4200
```
