"""API models. JSON uses camelCase (friendly to JavaScript clients)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


Pt = tuple[float, float]


class AnalysisConfig(CamelModel):
    """OPTIONAL advanced rules. Analysis is fully automatic without them; geometry-based rules (restricted area,
    boundary line) cannot be inferred automatically, so they only run when a zone/line is supplied."""
    restricted_zone: Optional[list[Pt]] = None
    line: Optional[tuple[Pt, Pt]] = None
    presence_zone: Optional[list[Pt]] = None
    dwell_seconds: float = Field(20.0, ge=1, le=3600)

    @field_validator("restricted_zone", "presence_zone")
    @classmethod
    def _poly(cls, v):
        if v is not None and len(v) < 3:
            raise ValueError("a zone needs at least 3 points")
        return v

    @field_validator("restricted_zone", "presence_zone", "line")
    @classmethod
    def _range(cls, v):
        for x, y in v or []:
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError("coordinates must be normalised to 0-1")
        return v


class VideoStats(CamelModel):
    people: int = 0
    animals: int = 0
    objects: int = 0
    events: int = 0
    incidents: int = 0  # potentially suspicious + high priority
    object_breakdown: dict[str, int] = Field(default_factory=dict)


class VideoOut(CamelModel):
    id: str
    filename: str
    uploaded_at: str
    duration: Optional[str]
    duration_sec: Optional[float]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    status: str
    stage: str
    progress: float
    error: Optional[str] = None
    thumbnail: Optional[str]
    src: str
    stats: Optional[VideoStats] = None  # null until analysis has completed


class EntityOut(CamelModel):
    id: str
    video_id: str
    group: str
    label: str
    name: str
    track_ids: list[int]
    first_sec: float
    last_sec: float
    duration_sec: float
    confidence: Optional[float]
    thumbnail: Optional[str]
    trajectory: list[list[float]]
    distance: Optional[float]
    appearances: list[list[float]]  # [[start,end],...] contiguous presence intervals


class EventOut(CamelModel):
    id: str
    video_id: str
    filename: Optional[str] = None
    kind: str
    severity: str
    severity_label: str
    title: str
    description: str
    start_sec: float
    end_sec: Optional[float]
    confidence: Optional[float]
    frame: Optional[str]
    entities: list[dict]  # [{id,name,label,group}]
    segment_index: Optional[int]


class SegmentOut(CamelModel):
    id: str
    video_id: str
    index: int
    start_sec: float
    end_sec: float
    summary: str
    people: int
    animals: int
    objects: int
    objects_breakdown: dict[str, int]
    entities: list[dict]
    interactions: list[str]
    classification: str
    classification_label: str
    confidence: Optional[float]
    frame: Optional[str]
    events: list[EventOut]
