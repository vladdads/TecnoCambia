# Publicar Tecnocambia en la nube (Render)

Guía recomendada: **Render** (plan gratis para probar, HTTPS incluido). La app es **Flask + Angular** con **SQLite** y archivos en `uploads/`.

## Antes de subir

1. Sube el proyecto a **GitHub** (sin `.env`, sin `node_modules`, sin `.venv`).
2. En local, verifica que compila:
   ```bash
   cd frontend && npm install && npm run build && cd ..
   pip install -r requirements.txt
   ```

## Opción A — Blueprint (más fácil)

1. Entra en [render.com](https://render.com) y crea cuenta.
2. **New → Blueprint** y conecta el repositorio de Tecnocambia.
3. Render leerá `render.yaml` y creará el servicio web con disco persistente.
4. En el panel del servicio, configura variables que quedaron vacías:
   - **`PUBLIC_BASE_URL`**: URL final, por ejemplo `https://tecnocambia.onrender.com` (sin `/` al final).
   - **Correo (recuperar contraseña)** — rellena `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`. No uses `MAIL_DEBUG=1` en producción.
5. Tras el deploy, abre: `https://TU-URL.onrender.com/app/products`

## Opción B — Servicio web manual

1. **New → Web Service** → conecta el repo.
2. Configuración:
   - **Runtime**: Python 3
   - **Build Command**: `chmod +x build.sh && ./build.sh`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
3. **Environment** (mínimo):

   | Variable | Valor |
   |----------|--------|
   | `FLASK_DEBUG` | `0` |
   | `FLASK_SECRET_KEY` | cadena larga aleatoria |
   | `SESSION_COOKIE_SECURE` | `true` |
   | `TRUST_PROXY` | `true` |
   | `DATA_DIR` | `/var/data` |
   | `PUBLIC_BASE_URL` | `https://tu-dominio.onrender.com` |
   | `FRONTEND_ORIGIN` | `https://tu-frontend.vercel.app` |
   | `CORS_ALLOWED_ORIGINS` | `https://tu-frontend.vercel.app` |
   | `SESSION_COOKIE_SAMESITE` | `None` |

4. **Disk** (importante): añade un disco persistente montado en **`/var/data`** (1 GB basta). Sin esto, la base SQLite y las fotos se pierden al reiniciar.

5. Deploy.

## Frontend en Vercel (separado)

1. Importa el mismo repositorio en Vercel y configura **Root Directory** = `frontend`.
2. Build command: `npm ci && npm run build`.
3. Output directory: `../public/spa/browser`.
4. Configura `frontend/public/runtime-config.js` para apuntar al backend:

```js
window.__TC_API_BASE__ = "https://tu-backend.onrender.com";
```

5. Después de desplegar, abre `https://tu-frontend.vercel.app/app/products`.

## Variables de entorno en producción

Copia desde `env.example` y ajusta:

```env
FLASK_SECRET_KEY=genera-una-clave-larga-aleatoria
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
DATA_DIR=/var/data
PUBLIC_BASE_URL=https://tu-url.onrender.com

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=tu_correo@gmail.com
MAIL_PASSWORD=contraseña_de_aplicacion
MAIL_DEFAULT_SENDER=Tecnocambia <tu_correo@gmail.com>
```

No definas `MAIL_DEBUG` en la nube.

## Usuario demo

En la **primera** base vacía se crea `demo@tecnocambia.local` / `demo1234` (admin). En producción conviene cambiar esa contraseña o eliminar el usuario demo después de las pruebas.

## Otras plataformas

| Plataforma | Notas |
|------------|--------|
| **Fly.io** | Usa volumen persistente para `/var/data`. |
| **VPS** (DigitalOcean, etc.) | Nginx + gunicorn + systemd; tú gestionas HTTPS con Certbot. |

## Límites del plan gratis (Render)

- El servicio **se duerme** tras inactividad; el primer acceso puede tardar ~30–60 s.
- **Un solo disco** por servicio: base + fotos viven en `DATA_DIR`.
- Para mucho tráfico, valora plan de pago o migrar la base a PostgreSQL más adelante.

## Comprobar que funciona

1. Catálogo: `/app/products`
2. Registro + admin en `/app/admin` (usuario demo o tu admin)
3. Publicar con al menos 1 foto
4. Recuperar contraseña (con SMTP configurado)

## Si el build falla por Node

En Render, en **Environment**, añade si hace falta:

- `NODE_VERSION` = `20` (o la LTS actual)

O en el build command instala Node según la documentación de Render para builds Python + frontend.
