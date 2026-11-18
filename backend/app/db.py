"""SQLite storage. One short-lived connection per call keeps it thread-safe.

Schema v2: videos -> entities (unique people/animals/objects with their tracked boxes), segments (10-second
activity summaries) and events (interactions / incidents). Re-analysis replaces a video's derived rows inside one
transaction, so statistics can never double count."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  thumb_path TEXT,
  uploaded_at TEXT NOT NULL,
  duration_sec REAL, fps REAL, width INTEGER, height INTEGER,
  status TEXT NOT NULL DEFAULT 'Queued',
  stage TEXT NOT NULL DEFAULT 'Video uploaded',
  progress REAL NOT NULL DEFAULT 0,
  error TEXT,
  config_json TEXT NOT NULL DEFAULT '{}',
  created_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  grp TEXT NOT NULL,            -- person | animal | object
  label TEXT NOT NULL,          -- COCO class, e.g. person, dog, handbag
  seq INTEGER NOT NULL,         -- 1-based number within its group: Person 1, Animal 1, Object 3
  track_ids_json TEXT NOT NULL, -- raw ByteTrack ids merged into this entity
  first_sec REAL NOT NULL, last_sec REAL NOT NULL, duration_sec REAL NOT NULL,
  confidence REAL, obs_count INTEGER NOT NULL,
  thumb_path TEXT,
  trajectory_json TEXT NOT NULL DEFAULT '[]',
  distance REAL,
  obs_json TEXT NOT NULL DEFAULT '[]'  -- [[t,x1,y1,x2,y2,conf],...] normalised boxes (overlay + trajectories)
);
CREATE INDEX IF NOT EXISTS idx_entities_video ON entities(video_id, grp);
CREATE TABLE IF NOT EXISTS segments (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  start_sec REAL NOT NULL, end_sec REAL NOT NULL,
  summary TEXT NOT NULL,
  people INTEGER NOT NULL, animals INTEGER NOT NULL, objects INTEGER NOT NULL,
  objects_json TEXT NOT NULL DEFAULT '{}',
  entity_ids_json TEXT NOT NULL DEFAULT '[]',
  event_ids_json TEXT NOT NULL DEFAULT '[]',
  interactions_json TEXT NOT NULL DEFAULT '[]',
  classification TEXT NOT NULL DEFAULT 'normal',
  confidence REAL,
  frame_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id, idx);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,       -- normal | unusual | suspicious | high
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  start_sec REAL NOT NULL, end_sec REAL,
  confidence REAL,
  frame_path TEXT,
  entity_ids_json TEXT NOT NULL DEFAULT '[]',
  segment_idx INTEGER,
  details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_video ON events(video_id, start_sec);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, severity);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_dirs()
    with connect() as c:
        c.execute("PRAGMA journal_mode = WAL")
        ver = c.execute("PRAGMA user_version").fetchone()[0]
        if ver < SCHEMA_VERSION:
            # v1 -> v2: old rule-event rows and the settings table are obsolete; keep the videos and re-analyse them.
            c.execute("DROP TABLE IF EXISTS events")
            c.execute("DROP TABLE IF EXISTS settings")
            c.executescript(SCHEMA)
            cols = {r["name"] for r in c.execute("PRAGMA table_info(videos)")}
            if "stage" not in cols:
                c.execute("ALTER TABLE videos ADD COLUMN stage TEXT NOT NULL DEFAULT 'Video uploaded'")
            c.execute("UPDATE videos SET status='Queued', progress=0, stage='Video uploaded'")
            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        else:
            c.executescript(SCHEMA)
