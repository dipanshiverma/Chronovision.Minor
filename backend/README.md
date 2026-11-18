# ChronoVision Backend (v2)

FastAPI service that turns a surveillance video into **unique tracked entities, 10-second activity summaries, graded
incidents, evidence frames, searchable answers and a PDF report** - all computed from the footage.

```
upload -> OpenCV frames -> YOLO11 detect + ByteTrack -> unique entities (stitching, camera-motion compensation)
       -> behaviour reasoning (carry / hand-off / approach / flee / unattended / running / loitering ...)
       -> 10 s segments + severity -> evidence frames -> SQLite -> search / overview / PDF report
```

## Run

Python 3.10-3.12; ffmpeg on PATH is recommended (browser-safe transcoding).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
API docs: http://localhost:8000/docs. Data lives in `./data` (`CHRONOVISION_DATA` to change).
**Upgrading from v1:** the database migrates automatically; old videos are kept and re-analysed on startup.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/videos` | upload (multipart `file`); analysis starts automatically |
| GET | `/api/videos`, `/api/videos/{id}` | list / status (`stage`, `progress`, `stats`) |
| GET | `/api/videos/{id}/analysis` | stats + 10 s segments + events + entities |
| GET | `/api/videos/{id}/tracks` | per-entity boxes `[t,x1,y1,x2,y2,conf]` for the synchronised overlay |
| GET | `/api/videos/{id}/report.pdf` | PDF report |
| POST | `/api/videos/{id}/analyse` | re-analyse (replaces results, no duplicates) |
| DELETE | `/api/videos/{id}` | remove video + results |
| GET | `/api/videos/{id}/file`, `/thumbnail` | video (Range supported), thumbnail |
| GET | `/api/events?videoId=&kind=&severity=&minSeverity=&order=&limit=` | events |
| GET | `/api/events/{id}/frame`, `/api/segments/{id}/frame`, `/api/entities/{id}/thumb` | evidence images |
| GET | `/api/overview` | dashboard totals + activity distribution |
| GET | `/api/search?q=` | natural-language search -> `answer` + `results` |

## What it detects

COCO classes of YOLO11: **people**, **animals** (bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe),
**objects** (bicycle, car, motorcycle, bus, truck, bench, backpack, umbrella, handbag, suitcase, bottle, cup, chair,
couch, dining table, tv, laptop, cell phone, book). COCO has no "purse": handbags and purses are both `handbag`.

Event kinds and their severity (Normal / Unusual / Potentially Suspicious / High-Priority):
`carry`, `approach`, `handover`, `pickup` (unattended object picked up), `transfer` (object appears to be taken from
one person by another: suspicious, high when the taker also approached and fled), `approach_flee`, `following`,
`running`, `loitering`, `unattended`/`abandoned`, `vehicle_proximity`. Optional geometry rules (only if a zone/line is
sent in `config`): `restricted_entry`, `line_crossing` (3+ crossings escalate), `prolonged_presence`.

Confidence = mean detection confidence of the entities involved, scaled by how many independent cues agree. It is a
heuristic score, not a calibrated probability.

## Tests and evaluation

`pytest` (26 tests: behaviour rules on scripted trajectories, search parsing, full upload -> analysis -> search -> PDF ->
re-analysis flow). `evaluation/` has scripts for event P/R/F1 + delay, search Recall@k, tracking IDF1/MOTA (MOT17) and runtime.

## Limits (read before trusting a result)

- **Activity descriptions are rule-based**, composed from tracked geometry. There is no vision-language model, so it cannot
  recognise an action it has no rule for, and it reads "appears to take" from box overlap, not from seeing hands.
- **Small objects are the weak spot.** `yolo11n` often misses handbags and phones; a missed bag means no theft event.
  Try `CHRONOVISION_MODEL=yolo11s.pt` and `CHRONOVISION_IMGSZ=960`.
- Unique counts rely on track stitching (position + motion), not appearance re-identification: someone who leaves and
  returns is counted again, and long occlusions in crowds can split or merge people.
- Restricted areas and boundary lines cannot be inferred automatically; they run only when a zone/line is supplied via the
  API. Without one, "restricted area" questions are answered honestly ("none recorded").
- Camera motion (pan/handheld) is compensated by phase correlation; fast zooms or rolling-shutter footage can still confuse it.
- Offline analysis, one video at a time, ~1.5 s of CPU time per second of video on a plain CPU (yolo11n). No authentication.
