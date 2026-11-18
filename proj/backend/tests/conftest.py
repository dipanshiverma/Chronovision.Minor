import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API client with an isolated data dir and no real worker thread (tests call the pipeline directly)."""
    from app import config
    for name, sub in (("DATA_DIR", ""), ("UPLOAD_DIR", "uploads"), ("EVIDENCE_DIR", "evidence"), ("THUMB_DIR", "thumbs")):
        monkeypatch.setattr(config, name, tmp_path / sub if sub else tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    from app import worker
    monkeypatch.setattr(worker, "start", lambda: None)
    monkeypatch.setattr(worker, "enqueue", lambda vid: None)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
