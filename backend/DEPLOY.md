# Backend — Render (u otro host Python)

Carpeta independiente del frontend. En Render configura **Root Directory** = `backend` (si el repo tiene ambas carpetas) o sube solo esta carpeta.

El build **no** compila Angular; el frontend va en Vercel (ver `../frontend/DEPLOY.md`).

## Antes de subir

1. Sube el proyecto a **GitHub** (sin `.env`, sin `.venv`, sin `db/tecnocambia.sqlite`).
2. En local:

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Comprueba `http://127.0.0.1:3000/api/meta`.

## Opción A — Blueprint

1. [render.com](https://render.com) → **New → Blueprint** → conecta el repo.
2. Si el repo tiene `frontend/` y `backend/`, en el servicio define **Root Directory** = `backend` (el `render.yaml` está aquí).
3. Variables obligatorias en producción:
   - `PUBLIC_BASE_URL` = `https://tu-backend.onrender.com`
   - `FRONTEND_ORIGIN` = `https://tu-frontend.vercel.app`
   - `CORS_ALLOWED_ORIGINS` = misma URL del frontend
   - `SESSION_COOKIE_SAMESITE` = `None`
   - SMTP para recuperar contraseña (no uses `MAIL_DEBUG=1`)

## Opción B — Servicio manual

| Campo | Valor |
|-------|--------|
| Root Directory | `backend` |
| Build Command | `chmod +x build.sh && ./build.sh` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120` |
| Health check | `/api/meta` |

Añade disco persistente en **`/var/data`** y `DATA_DIR=/var/data`.

## Variables de entorno

Copia `env.example` a `.env` en local. En Render, ver `env.example` y la tabla del README raíz.

## Comprobar

- `GET https://tu-backend.onrender.com/api/meta`
- Login desde el frontend en Vercel con `runtime-config.js` apuntando a este backend
