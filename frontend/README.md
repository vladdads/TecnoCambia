# Tecnocambia — Frontend (Angular)

App del catálogo, login, registro y publicación. Se despliega **aparte** del backend.

- **Producción:** ver [DEPLOY.md](DEPLOY.md) (Vercel).
- **API:** configura `public/runtime-config.js` con la URL del backend en Render.

## Desarrollo

```bash
npm install
npm start
```

Con el backend en `http://127.0.0.1:3000`, abre `http://localhost:4200/app/products`.

## Build

```bash
npm run build
```

Salida en `dist/browser/`.
