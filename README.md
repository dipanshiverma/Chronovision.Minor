# ChronoVision — AI Video Surveillance Intelligence

Upload a surveillance video and ChronoVision automatically **detects and tracks people, animals and objects**, counts unique
entities, writes a **10-second activity description** for every interval, flags **potentially suspicious behaviour** with
evidence frames, and lets you **search the footage in plain language** and **download a PDF report**.

```
UPLOAD → validate/transcode → frames (≈10 fps) → YOLO11 detection + ByteTrack → unique entities
       → behaviour reasoning → 10 s segments → evidence frames → SQLite → Overview · Timeline · Search · Reports
```

Pages: **Overview · Analyse Video · Event Timeline · Video Search · Reports** (no Settings, nothing to configure).

## Requirements
Node 20+, Python 3.10–3.13, ffmpeg on PATH (needed for MOV/AVI/MKV). No GPU needed.

## Run (two terminals)
```bash
# Terminal 1 — backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # PyTorch + Ultralytics: large download, once
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (project root)
npm install --legacy-peer-deps
npm run dev                                             # open http://localhost:8080
```
Shortcuts: `./start-backend.sh` / `./start-frontend.sh` (macOS/Linux) or `start-backend.bat` / `start-frontend.bat` (Windows).
The YOLO weights (~5 MB) download on first analysis.

## Tests
`cd backend && python -m pytest -q` (26 tests) · `npm test` · `npm run build`

## How it works / honest limits
* Detection: Ultralytics YOLO11n (COCO: people, 10 animal classes, vehicles, bags, phones, laptops, bottles, furniture…).
  Tracking: ByteTrack plus track-stitching into unique entities; camera-motion compensation avoids false motion on pans.
* Activity descriptions and suspicious-behaviour findings are **rule-based reasoning over tracked geometry** (carry,
  hand-over, object taken, pick-up, left-behind, loitering, running, following, approach-then-flee, vehicle proximity) —
  not a vision-language model. Wording is hedged ("appears to…"); nothing claims a crime occurred.
* Small items (handbags, phones) are often missed by the nano model. For better recall set `CHRONOVISION_MODEL=yolo11s.pt`
  and `CHRONOVISION_IMGSZ=960` (slower). See `backend/.env.example`.
* Unique counts have no appearance re-identification: a person who leaves and returns can be counted twice, crowds can
  be mis-counted.
* Restricted-area / boundary-line rules need a zone supplied through the API (`/api/videos/{id}/analyse`); they are never guessed.
* Everything shown comes from stored analysis; empty results say so. Re-analysis replaces results atomically (no duplicates).
* Optional: set `ANTHROPIC_API_KEY` to let an LLM parse search questions into filters (answers still come from stored data).

See `IMPLEMENTATION_REPORT_v2.md` for the detailed design notes and `TEST_RESULTS.md` for measured results.
