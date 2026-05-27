## Tecnocambia

Marketplace estilo “Mercado Libre” para **venta**, **intercambio** o **donación** de equipo electrónico.

### Publicar en la nube

- **Frontend en Vercel:** despliegue estático del directorio `frontend`.
- **Backend en Render:** usa **Render** con `build.sh` y `app.py` como backend Flask.
- **Arquitectura separada (recomendada):**
  - Vercel sirve Angular.
  - Render expone `/api`, `/uploads` y páginas clásicas (`/messages`, `/auth/*`, etc.).
  - Configura `frontend/public/runtime-config.js` con la URL pública del backend:
    ```js
    window.__TC_API_BASE__ = "https://tu-backend.onrender.com";
    ```
  - En Render, define:
    - `FRONTEND_ORIGIN=https://tu-frontend.vercel.app`
    - `CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app`
    - `SESSION_COOKIE_SAMESITE=None`
    - `SESSION_COOKIE_SECURE=true`

### Requisitos
- Python 3.10+ (recomendado)
- Node 18+ (solo si compilas el frontend Angular)

### Cómo ejecutar (producción local)

1. Compilar el frontend (genera `public/spa/browser/`):

```bash
cd frontend
npm install
npm run build
cd ..
```

2. Arrancar Flask:

```bash
python app.py
```

3. Abre el catálogo Angular en `http://localhost:3000/app/products` (la raíz `/` redirige al catálogo).

> Si frontend y backend están en dominios distintos, define `window.__TC_API_BASE__` en `runtime-config.js` para que Angular llame al backend correcto.

### Recuperar contraseña (correo real)

El enlace **“Olvidé mi contraseña”** en el login Angular apunta a `/auth/forgot` (formulario clásico). El servidor envía el correo por **SMTP** usando variables de entorno.

1. Copia `env.example` a `.env` en la raíz del proyecto (junto a `app.py`) y rellena al menos:
   - `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS` o `MAIL_USE_SSL`
   - `MAIL_USERNAME` / `MAIL_PASSWORD` si tu proveedor lo exige
   - `MAIL_DEFAULT_SENDER` (o `MAIL_FROM`) — remitente visible
   - `PUBLIC_BASE_URL` — URL pública del sitio **sin** barra final (ej. `https://tudominio.com` o `http://127.0.0.1:3000`). Así el enlace del email apunta bien a `/auth/reset/...`.

2. Con **Gmail** suele hacer falta una [contraseña de aplicación](https://support.google.com/accounts/answer/185833), no la contraseña normal de la cuenta.

3. Arranca de nuevo `python app.py`. Si SMTP falla, verás el error en pantalla y detalles en `logs/app.log`.

**Solo en tu computadora (sin Gmail):** en `.env` pon `MAIL_DEBUG=1` (y no actives `MAIL_SERVER` / remitente, o comenta esas líneas). Tras enviar el formulario con un email que **sí exista** en la base, la misma página te mostrará el enlace para restablecer la contraseña. No uses `MAIL_DEBUG=1` en un servidor público.

Si no configuras ni SMTP ni `MAIL_DEBUG=1`, la recuperación por correo no funcionará hasta que configures `MAIL_*`.

### Desarrollo frontend (opcional)

Con Flask en `http://127.0.0.1:3000` en otra terminal:

```bash
cd frontend
npm start
```

Abre `http://localhost:4200/app/products`. Las peticiones a `/api` y `/uploads` se proxifican al backend (ver `frontend/proxy.conf.json`).

### Verificación de identidad (seguridad)

En el **registro** se pide **CURP válida** (18 caracteres) y **una foto del frente de la INE**. La cuenta queda **pendiente** hasta que un administrador la apruebe en `/admin`. Solo usuarios **verificados** pueden **publicar** anuncios.

### Qué incluye
- **Catálogo Angular**: `/app/products`, detalle `/app/products/:id`
- **Iniciar sesión / registro**: `/app/login`, `/app/register` (API JSON + cookies de sesión)
- **Publicar**: `/app/sell` (requiere sesión e identidad verificada)
- **Rutas clásicas** (plantillas HTML): chats, mis publicaciones, admin, etc.
- **Base de datos SQLite**: `db/tecnocambia.sqlite`

### Usuario para probar la página (demo)

En el **primer arranque** se crea un usuario de prueba ya **verificado** y **administrador**:

| Campo    | Valor                    |
|----------|--------------------------|
| **Email**    | `demo@tecnocambia.local` |
| **Contraseña** | `demo1234`             |

Sirve para entrar al catálogo, publicar sin esperar revisión y abrir **`/admin`** para aprobar identidades de otros registros.

### Reiniciar la aplicación “desde cero” (local)

1. **Detén** el servidor Flask (en la terminal donde corre, `Ctrl+C`).

2. **Entorno Python** (recomendado en la carpeta del proyecto):

```bash
python -m venv .venv
```

En Windows PowerShell: `.\.venv\Scripts\Activate.ps1`  
En macOS/Linux: `source .venv/bin/activate`

```bash
pip install -r requirements.txt
```

3. **Variables de entorno**: copia `env.example` a `.env` y edítalo (SMTP, `PUBLIC_BASE_URL`, `FLASK_SECRET_KEY` en producción). El archivo `.env` se carga solo al iniciar si instalaste las dependencias del `requirements.txt`.

4. **Frontend Angular** (genera `public/spa/browser/`):

```bash
cd frontend
npm install
npm run build
cd ..
```

5. **Base de datos limpia (opcional)**: si quieres empezar como la primera vez, cierra Flask y borra `db/tecnocambia.sqlite` (y si quieres, archivos en `uploads/`). Al volver a ejecutar `python app.py` se recrea la base y el usuario demo.

6. **Arranque**:

```bash
python app.py
```

Abre `http://127.0.0.1:3000/app/products` (o el puerto que tengas en `PORT`).
