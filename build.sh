#!/usr/bin/env bash
set -euo pipefail

echo "==> Python dependencies"
pip install -r requirements.txt

echo "==> Angular build"
cd frontend
if command -v npm >/dev/null 2>&1; then
  npm ci
  npm run build
else
  echo "ERROR: npm no encontrado. En Render activa Node o usa el blueprint render.yaml."
  exit 1
fi

echo "==> Build OK (SPA en public/spa/browser)"
