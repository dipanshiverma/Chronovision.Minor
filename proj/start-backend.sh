#!/usr/bin/env bash
cd "$(dirname "$0")/backend"
[ -d .venv ] || { python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt; }
. .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
