# Test results (measured in the build sandbox, CPU only, YOLO11n + ByteTrack)

**Important:** your purse-theft and checkpoint videos were not included in the upload, so Tests 1 and 2 of the brief were
NOT run on them. Run them yourself and inspect the overlay toggle to see what the model detected.

| Check | Result |
|---|---|
| Backend unit/API tests | 26 passed (theft/hand-over/abandonment/running rules on scripted tracks, full pipeline, re-analysis x3 = identical stats, delete cleanup, PDF) |
| Frontend | type-check clean, vitest passed, production build OK |
| Formats uploaded through the real API | MP4, MOV, WEBM, AVI, MKV all analysed (non-MP4 transcoded to H.264 for playback) |
| 14 s street clip (real people + bus, panning camera) | 3–5 unique people, 0–1 bus depending on codec; 2 segments (10 s + 4 s); 0 events (no false running/following from the pan) |
| 42 s clip | 5 segments (4 x 10 s + final 2 s) |
| 8 s two-person clip | 2 people, 1 segment |
| Re-analysis (x2) | videos/people/objects unchanged, no duplicates |
| Overview / Search / PDF | totals computed from stored data; 8 questions answered or honestly declined; PDF 189 KB, valid |
| Browser (Chromium) | upload via UI showed live stages; all 5 pages render; /settings is 404; overlay canvases draw; no horizontal overflow at 390 px or 820 px; mobile drawer works |

Not verified: handbag/phone detection, animals (none in the footage), real theft footage, LLM search parsing, Windows/macOS runs.
