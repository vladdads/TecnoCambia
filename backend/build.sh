#!/usr/bin/env bash
set -euo pipefail

echo "==> Python dependencies"
pip install -r requirements.txt

echo "==> Backend listo (API Flask; el frontend se despliega aparte)"
