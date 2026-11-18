# ChronoVision – AI-Based Video Surveillance Intelligence

## 1. Project Overview

ChronoVision is an AI-based video surveillance analysis system designed to automate the processing and interpretation of CCTV footage. It detects and tracks people, animals, and objects, identifies activities and potentially suspicious events, and generates structured reports from recorded video.

The system aims to reduce the manual effort involved in reviewing lengthy surveillance recordings by providing timestamp-based activity summaries, searchable video insights, visual evidence, and downloadable PDF reports.

## 2. Key Features

- **Video Upload and Analysis:** Upload surveillance videos in MP4, MOV, WEBM, AVI, MKV, and M4V formats. Analysis begins automatically after upload.
- **Object Detection:** Detect people, animals, vehicles, and other supported objects using YOLO11.
- **Multi-Object Tracking:** Track detected entities across video frames using ByteTrack.
- **Entity Identification and Counting:** Maintain tracked identities and calculate entity-level statistics.
- **Activity Analysis:** Generate activity descriptions for every 10-second video segment using rule-based behavioural analysis.
- **Suspicious Event Detection:** Identify potentially suspicious activities such as object transfers, unattended objects, running, loitering, following, and approach-and-flee behaviour.
- **Evidence Extraction:** Store relevant frames associated with detected events and activities.
- **Detection Visualization:** Display bounding boxes, tracking identifiers, and confidence values synchronized with video playback.
- **Event Timeline:** Browse timestamped activities and filter events by type and severity.
- **Natural Language Search:** Query analysed footage using plain-language questions and retrieve relevant results with timestamps and evidence.
- **PDF Report Generation:** Generate downloadable reports containing video information, entity statistics, detected events, activity summaries, and evidence frames.

## 3. System Architecture

ChronoVision follows a frontend-backend architecture.

### Frontend
Provides the user interface for uploading videos, monitoring analysis progress, visualizing detections, exploring event timelines, searching analysed footage, and accessing reports.

### Backend
Handles video processing, object detection, tracking, behavioural analysis, evidence extraction, database operations, and report generation.

### Processing Pipeline

```text
Video Upload
     |
     v
Video Validation and Preprocessing
     |
     v
Frame Extraction
     |
     v
YOLO11 Object Detection
     |
     v
ByteTrack Multi-Object Tracking
     |
     v
Entity Identification and Tracking
     |
     v
Behavioural Analysis
     |
     v
10-Second Activity Segmentation
     |
     v
Event Detection and Evidence Extraction
     |
     v
SQLite Database
     |
     v
Timeline | Search | Dashboard | PDF Reports
```

## 4. Technologies Used

| Component | Technologies |
|---|---|
| Frontend | React, TypeScript, Tailwind CSS |
| Frontend Framework | TanStack Start, Vite |
| Backend Framework | Python, FastAPI |
| Object Detection | YOLO11 (Ultralytics) |
| Object Tracking | ByteTrack |
| Video Processing | OpenCV, FFmpeg |
| Database | SQLite |
| Data Validation | Pydantic |
| PDF Generation | ReportLab |
| Testing | Pytest, Vitest |

## 5. Project Structure

```text
Chronovision.Minor/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── pipeline.py
│   │   ├── detector.py
│   │   ├── entities.py
│   │   ├── behavior.py
│   │   ├── events.py
│   │   ├── describe.py
│   │   ├── evidence.py
│   │   ├── nlq.py
│   │   ├── report.py
│   │   ├── db.py
│   │   ├── repo.py
│   │   └── ...
│   │
│   ├── evaluation/
│   ├── scripts/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── routes/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── ...
│   ├── public/
│   └── package.json
│
├── .gitignore
└── README.md
```

## 6. Installation and Execution

### Prerequisites

- Python 3.10–3.12
- Node.js 20 or later
- npm
- FFmpeg (required for video formats that need transcoding)

### Backend Setup

Open a terminal and execute:

```bash
cd backend

python -m venv .venv
```

Activate the virtual environment:

**Windows:**
```bash
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Start the backend server:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The backend API documentation is available at:

`http://localhost:8000/docs`

### Frontend Setup

Open a separate terminal:

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Open the application using the local URL displayed by the development server.

## 7. Evaluation and Testing

The project includes automated tests and evaluation scripts to assess different components of the system.

- **Behavioural Analysis:** Tests event-classification rules using predefined tracking scenarios.
- **API and Pipeline Testing:** Tests video upload, processing, analysis retrieval, report generation, and re-analysis.
- **Event Detection Evaluation:** Supports Precision, Recall, F1-score, and detection-delay calculation against manually annotated ground truth.
- **Tracking Evaluation:** Supports IDF1, MOTA, ID precision, ID recall, and identity-switch evaluation using MOTChallenge-format datasets.
- **Search Evaluation:** Supports Recall@K and timestamp accuracy.
- **Runtime Evaluation:** Measures processing speed, frame latency, and memory usage.

Run backend tests:

```bash
cd backend
python -m pytest -q
```

Run frontend tests:

```bash
cd frontend
npm test
```

Build the frontend:

```bash
npm run build
```

## 8. Technical Considerations and Limitations

- Behavioural interpretation is based on rule-based analysis of tracked object positions and movements; it is not direct semantic understanding of video through a vision-language model.
- Detection accuracy depends on video quality, object visibility, lighting, occlusion, and model performance.
- Small objects such as handbags and mobile phones may not always be detected reliably.
- Unique entity counting depends on track stitching and does not include appearance-based re-identification.
- Restricted-area and boundary-crossing detection require zone or line coordinates supplied through the API.
- Confidence values are heuristic scores and should not be interpreted as calibrated probabilities.
- Detected suspicious activities are automated observations and should not be treated as definitive evidence of criminal activity.

## 9. Conclusion

ChronoVision demonstrates an integrated approach to automated video surveillance analysis by combining object detection, multi-object tracking, behavioural analysis, event identification, evidence extraction, and natural-language retrieval.

The system transforms raw surveillance footage into structured, timestamped information that can be reviewed through an interactive interface and exported as detailed reports. It provides a foundation for reducing manual video-review effort and improving the accessibility of surveillance information.
