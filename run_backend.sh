#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  echo "Virtual environment missing. Run ../setup_mac.sh first."
  exit 1
fi
source .venv/bin/activate
exec python -m uvicorn app.main:app --reload --port 8000
