# Frontend — Vercel (u otro hosting estático)

Carpeta independiente del backend. Sube **solo** `frontend/` o configura el repositorio con **Root Directory** = `frontend`.

## Pasos en Vercel

1. Importa el repositorio.
2. **Root Directory**: `frontend`
3. **Build Command**: `npm ci && npm run build` (o deja el de `vercel.json`)
4. **Output Directory**: `dist/browser`
5. Edita `public/runtime-config.js` con la URL de tu backend en Render:

```js
window.__TC_API_BASE__ = "https://tu-backend.onrender.com";
```

6. Tras el deploy, abre `https://tu-dominio.vercel.app/app/products`

## Desarrollo local

Con el backend en `http://127.0.0.1:3000`:

```bash
npm install
npm start
```

Abre `http://localhost:4200/app/products`. Las peticiones `/api` y `/uploads` se proxifican vía `proxy.conf.json`.

## Build local

```bash
npm install
npm run build
```

Los archivos quedan en `dist/browser/`.
