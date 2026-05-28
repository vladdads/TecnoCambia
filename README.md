# Tecnocambia

Marketplace para venta, intercambio o donación de equipo electrónico.

El proyecto está dividido en **dos carpetas** para subir cada parte a la nube por separado:

| Carpeta | Qué es | Dónde desplegar |
|---------|--------|-----------------|
| [`frontend/`](frontend/) | App Angular (catálogo, login, publicar) | **Vercel**, Netlify, etc. |
| [`backend/`](backend/) | API y rutas Flask (SQLite, uploads, correo) | **Render**, Fly.io, VPS |

## Despliegue en la nube (recomendado)

1. **Backend (Render)** — guía en [`backend/DEPLOY.md`](backend/DEPLOY.md)
   - Root del servicio: carpeta `backend` (o sube solo esa carpeta a un repo).
   - Variables: `FRONTEND_ORIGIN`, `CORS_ALLOWED_ORIGINS`, `PUBLIC_BASE_URL`, `DATA_DIR`, SMTP, etc.

2. **Frontend (Vercel)** — guía en [`frontend/DEPLOY.md`](frontend/DEPLOY.md)
   - Root Directory: `frontend`
   - En `frontend/public/runtime-config.js` pon la URL del backend:
     ```js
     window.__TC_API_BASE__ = "https://tu-backend.onrender.com";
     ```

## Desarrollo local

**Terminal 1 — backend:**

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy env.example .env
python app.py
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install
npm start
```

Abre `http://localhost:4200/app/products`.

## Usuario demo

Tras el primer arranque del backend: `demo@tecnocambia.local` / `demo1234` (admin y verificado).
