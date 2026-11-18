# ChronoVision v2: implementation report

## 0. Read this first

- **Your test videos did not reach me.** Only the `.docx` prompt, two zips and three screenshots were uploaded, so
  **Test 1 (purse theft) and Test 2 (security checkpoint) have NOT been run.** Everything below was tested on the only
  real footage I had: a 14 s clip of people next to a bus (a camera pan over a sample photo), plus scripted scenarios.
  Please run your videos and treat the first results as unvalidated.
- **Whether the purse theft is detected depends on the model seeing the handbag.** The theft rule needs a tracked
  handbag that moves from one person to another. `yolo11n` often misses small bags. If the bag is missed, no theft event
  is produced (the search then says so honestly). Try `yolo11s` + `imgsz 960` (see INSTALL.md).
- Activity descriptions are **rule-based reasoning over tracked geometry**, not a vision-language model.

## 1. Status against the 16 parts of the brief

| Part | Status |
|---|---|
| 2 Remove Settings | Done (route, sidebar item, backend endpoints and table removed) |
| 3 Automatic upload + analysis, real progress, re-analysis without duplicates | Done. Real stages (Video uploaded, Extracting frames, Detecting objects, Tracking entities, Analysing activities, Generating event timeline, Analysis completed) with frame-accurate progress. Re-analysis replaces results atomically (tested) |
| 4 People / animal / object detection, unique counting, entity stats | Done for the 30 COCO classes the model supports. Per-entity first/last/duration/trajectory/confidence; whole-video and per-segment counts |
| 5 Detection overlay, toggles, entity inspector | Done: canvas overlay synced to playback, colour per category, ID + label + confidence, on/off + per-category toggles, entity inspector with highlight and appearance jump links |
| 6 10-second activity understanding | Done (rule-based). Every field requested per segment is stored and shown. Final partial segment and clips under 10 s handled (tested) |
| 7 Suspicious activity | Partly. Implemented: object taken from a person, hand-over (normal), pickup of unattended object, abandoned/unattended object, running, loitering, approach-then-flee, following, moving around a vehicle. Needs a supplied zone/line (API only): restricted area, boundary line (3+ crossings escalate). Not implemented: abnormal movement patterns beyond running |
| 8 Event Timeline redesign | Done: per-video header with stats, player, 10-second timeline, filters (video, suspicion level, event type), expandable details, click-to-seek |
| 9 NL search | Done: counts, yes/no, longest, time windows, event kinds, entity types, suspicious; answers only from stored data; says so when unsupported. Optional LLM query parsing is implemented but untested (no API key) |
| 10 Overview | Done: 7 live statistics, recent analyses, recent events, activity distribution chart |
| 11 Reports + PDF | Done: on-page report and server-generated PDF with all requested sections |
| 12 UI/UX | Brand kept (palette, sidebar, cards, typography). Page content is responsive; the fixed sidebar was left as designed (no mobile menu) |
| 13 Architecture | CPU-friendly: YOLO11n, ByteTrack, ~10 analysed fps, frames skipped without decoding, background worker |
| 14 Database | Schema v2 (entities, segments, events + videos); automatic migration from v1 |
| 15 Testing with your videos | **Not possible (videos missing).** See section 4 for what was tested |

## 2. What changed

**Backend (`backend/app`)** - new: `taxonomy.py`, `camera.py` (phase-correlation camera-motion compensation),
`entities.py` (noise filtering + track stitching into unique entities), `behavior.py` (temporal reasoning),
`describe.py` (10 s segments and summaries), `report.py` (PDF). Rewritten: `pipeline.py`, `db.py`, `repo.py`,
`schemas.py`, `nlq.py`, `main.py`. Updated: `detector.py` (30 classes), `evidence.py`, `config.py`. `events.py`
(zone/line engine) kept for the optional geometry rules.

**Frontend (20 files)** - new: `detection-player`, `entity-inspector`, `segment-timeline`, `activity-chart`.
Rewritten: Overview, Analyse, Timeline, Search, Reports pages, `video-store.ts`, badges, analyses table, events rows.
Removed: Settings, zone editor, segment-player. Hydration-safe store.

**Database** - tables `entities` (with tracked boxes), `segments`, `events` (kind, severity, confidence, evidence, entity
links); `videos` gains `stage`. v1 data migrates automatically; old videos are re-analysed.

**Dependencies added** - `reportlab` (PDF). Everything else was already in use (ultralytics/torch, opencv, fastapi).

**Models and methods** - Ultralytics **YOLO11n** (COCO, pretrained), **ByteTrack**, OpenCV phase correlation for
camera motion, geometric rules for behaviour. Optional: Claude (query parsing only, off unless `ANTHROPIC_API_KEY` is set).

## 3. Run

```
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev          # http://localhost:8080
cd backend && python -m pytest -q   # 26 tests
```

## 4. Actual test results

**Automated (26 passing):**
- Behaviour rules on **scripted** trajectories (synthetic): theft scenario -> High-Priority transfer with hedged wording;
  hand-over between people already together -> Normal; bag left behind -> Potentially Suspicious after ~15 s alone;
  running detected, walking not; **a fast-panning camera with stationary people produces no motion events**; empty scene -> no events.
- Full pipeline with a scripted detector: upload -> automatic analysis -> entities, 10 s + 4 s segments, incident with
  evidence frame, overview totals, 7 search questions answered from stored data, PDF generated, **re-analysis three times
  gives identical stats and no duplicates**, deletion cleans up; empty scene reports zeros; failures surface as "Failed".

**Real model (YOLO11n + ByteTrack) on the 14 s demo clip (people beside a bus, panning camera):**
- Stages progressed live; completed with 4-5 unique people and 1-2 buses (varies slightly with video encoding), 0 animals.
- Segment 1 (00:00-00:10): "4 people are visible (3 standing, 1 walking). Objects in view: bus x2." Segment 2:
  "Person 4 stands near a bus before leaving the scene. Objects in view: bus."
- **No false running/following events despite the pan** (camera compensation working). 0 events, 0 incidents, which is
  correct for this clip. "When did someone steal the handbag?" -> honest "no stored analysis shows an object being taken".
- Speed on this sandbox CPU: ~1.5 s of processing per 1 s of video (includes model load and transcode).

**Browser end-to-end (headless Chromium, real backend + model):** upload; live stage list; Overview figures; timeline
with overlay painting boxes (16k pixels) and 0 after toggling off; entity selection highlight; segment seek; search answer;
**PDF download** (`%PDF`); `/settings` no longer exists; no JavaScript errors.

**Not tested:** your purse-theft and checkpoint videos; animals (none in my footage; detection uses the same pipeline);
real vehicles/handbags; the optional LLM parser; tracking benchmarks (MOT17); mobile layout.

## 4b. Expectations for your purse-theft video

If `yolo11n` sees both the woman and the handbag and tracks the bag, expect: carry event for the woman, then a `transfer`
event when the bag ends up with the other person, graded Potentially Suspicious or High-Priority depending on whether the
taker approached and moved away quickly. If the bag is missed or the person grabbing it is occluded, expect people and
movement summaries but no theft event. Check the overlay toggle to see what the model actually saw.

## 5. Known limitations and next steps

- No vision-language model: descriptions cannot name actions the rules do not cover. A next step is to send 2-3 sampled
  frames per segment to a VLM and merge its description with the rule facts (not done, to avoid unverified code).
- Handbag/phone detection is weak on the nano model; fine-tuning on surveillance footage would help most.
- Unique counts depend on stitching; no appearance re-identification; crowded scenes will over/under count.
- Restricted-area and boundary rules need a user-drawn zone (API only now); a small optional "advanced" UI could return.
- Confidence values are heuristic scores, not calibrated probabilities.
- Sidebar is fixed-width (no mobile menu).
