#!/usr/bin/env bash
cd "$(dirname "$0")/backend"
python -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
