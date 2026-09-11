#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }
command -v npm >/dev/null || { echo "Node.js/npm is required."; exit 1; }

PYTHON_BIN="python3"
if command -v python3.11 >/dev/null; then PYTHON_BIN="python3.11"; fi

echo "=== DGDF-RAG Final Ready Prototype Setup ==="
echo "Using: $($PYTHON_BIN --version)"

cd backend
$PYTHON_BIN -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd ..

cd frontend
npm install
cd ..

source backend/.venv/bin/activate
python prepare_demo.py

chmod +x run_backend.sh run_frontend.sh check_project.sh setup_mac.sh

echo ""
echo "SETUP COMPLETE"
echo "Backend:  ./run_backend.sh"
echo "Frontend: ./run_frontend.sh"
echo "Swagger:  http://127.0.0.1:8000/docs"
