import { useEffect, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { api, apiUrl, ApiError } from "@/lib/api";

export type AnalysisStatus = "Completed" | "Processing" | "Queued" | "Failed";
export type Severity = "normal" | "unusual" | "suspicious" | "high";

export const SEVERITY_LABEL: Record<Severity, string> = {
  normal: "Normal Activity",
  unusual: "Unusual Activity",
  suspicious: "Potentially Suspicious",
  high: "High-Priority Incident",
};
export const SEVERITY_ORDER: Record<Severity, number> = {
  normal: 0,
  unusual: 1,
  suspicious: 2,
  high: 3,
};

/** The real pipeline stages, in order. The backend reports which one it is in. */
export const STAGES = [
  "Video uploaded",
  "Extracting frames",
  "Detecting objects",
  "Tracking entities",
  "Analysing activities",
  "Generating event timeline",
  "Analysis completed",
] as const;

export interface VideoStats {
  people: number;
  animals: number;
  objects: number;
  events: number;
  incidents: number;
  objectBreakdown: Record<string, number>;
}

export interface VideoAnalysis {
  id: string;
  filename: string;
  uploadedAt: string;
  duration: string | null;
  durationSec: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: AnalysisStatus;
  stage: string;
  progress: number;
  error: string | null;
  thumbnail: string | null;
  src: string;
  stats: VideoStats | null; // null until the analysis has completed
}

export interface EntityRef {
  id: string;
  name: string;
  label: string;
  group: "person" | "animal" | "object";
}

export interface EventItem {
  id: string;
  videoId: string;
  filename: string | null;
  kind: string;
  severity: Severity;
  severityLabel: string;
  title: string;
  description: string;
  startSec: number;
  endSec: number | null;
  confidence: number | null;
  frame: string | null;
  entities: EntityRef[];
  segmentIndex: number | null;
}

export interface Segment {
  id: string;
  videoId: string;
  index: number;
  startSec: number;
  endSec: number;
  summary: string;
  people: number;
  animals: number;
  objects: number;
  objectsBreakdown: Record<string, number>;
  entities: EntityRef[];
  interactions: string[];
  classification: Severity;
  classificationLabel: string;
  confidence: number | null;
  frame: string | null;
  events: EventItem[];
}

export interface Entity {
  id: string;
  videoId: string;
  group: "person" | "animal" | "object";
  label: string;
  name: string;
  trackIds: number[];
  firstSec: number;
  lastSec: number;
  durationSec: number;
  confidence: number | null;
  thumbnail: string | null;
  trajectory: number[][]; // [t, x, y] normalised
  distance: number | null;
  appearances: number[][]; // [[start, end], ...]
}

export interface Analysis {
  video: VideoAnalysis;
  segments: Segment[];
  events: EventItem[];
  entities: Entity[];
}

export interface TrackedEntity {
  id: string;
  group: "person" | "animal" | "object";
  label: string;
  name: string;
  obs: number[][]; // [t, x1, y1, x2, y2, conf] normalised
}

export interface Overview {
  videos: number;
  analysed: number;
  people: number;
  animals: number;
  objects: number;
  events: number;
  incidents: number;
  distribution: { severity: Severity; label: string; segments: number; events: number }[];
}

export interface SearchResult {
  type: "event" | "entity" | "segment";
  videoId: string;
  filename: string;
  startSec: number;
  endSec: number | null;
  title: string;
  text: string;
  thumbnail: string | null;
  confidence: number | null;
  severity: Severity | null;
  severityLabel: string | null;
  entities: { name: string; label: string }[];
}

export interface SearchResponse {
  query: string;
  source: "rules" | "llm" | null;
  interpretation: string[];
  answer: string;
  results: SearchResult[];
}

interface State {
  videos: VideoAnalysis[];
  events: EventItem[]; // most recent events across videos
  overview: Overview | null;
  /** null = not checked yet, false = backend unreachable */
  online: boolean | null;
}

let state: State = { videos: [], events: [], overview: null, online: null };
const listeners = new Set<() => void>();

function set(patch: Partial<State>) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
const getSnapshot = () => state;
// Server render and first client render must agree, so hydration always starts from this empty state.
const serverState: State = { videos: [], events: [], overview: null, online: null };
const getServerSnapshot = () => serverState;

// ---------------------------------------------------------------- mapping (rewrites backend paths to absolute URLs)
export const mapVideo = (v: VideoAnalysis): VideoAnalysis => ({
  ...v,
  thumbnail: apiUrl(v.thumbnail),
  src: apiUrl(v.src) ?? "",
});
export const mapEvent = (e: EventItem): EventItem => ({ ...e, frame: apiUrl(e.frame) });
const mapSegment = (s: Segment): Segment => ({
  ...s,
  frame: apiUrl(s.frame),
  events: s.events.map(mapEvent),
});
const mapEntity = (e: Entity): Entity => ({ ...e, thumbnail: apiUrl(e.thumbnail) });

// ---------------------------------------------------------------- sync with backend
export async function refresh() {
  try {
    const [videos, events, overview] = await Promise.all([
      api<VideoAnalysis[]>("/api/videos"),
      api<EventItem[]>("/api/events?limit=8&order=recent"),
      api<Overview>("/api/overview"),
    ]);
    const next = videos.map(mapVideo);
    for (const v of next) {
      const prev = state.videos.find((x) => x.id === v.id);
      if (prev && prev.status !== v.status) {
        if (v.status === "Completed")
          toast.success(`${v.filename}: analysis finished`, {
            description: `${v.stats?.people ?? 0} people, ${v.stats?.events ?? 0} events.`,
          });
        if (v.status === "Failed")
          toast.error(`${v.filename}: analysis failed`, { description: v.error ?? "" });
      }
    }
    set({ videos: next, events: events.map(mapEvent), overview, online: true });
  } catch {
    set({ online: false });
  }
}

let timer: ReturnType<typeof setTimeout> | null = null;
let subscribers = 0;

function schedule() {
  if (timer) clearTimeout(timer);
  if (!subscribers) return;
  const busy = state.videos.some((v) => v.status === "Queued" || v.status === "Processing");
  timer = setTimeout(
    async () => {
      await refresh();
      schedule();
    },
    busy ? 1000 : state.online === false ? 5000 : 15000,
  );
}

/** Subscribe a component to backend data. Polls fast while an analysis is running. */
export function useVideoStore() {
  useEffect(() => {
    subscribers += 1;
    if (subscribers === 1) void refresh().then(schedule);
    return () => {
      subscribers -= 1;
      if (!subscribers && timer) clearTimeout(timer);
    };
  }, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

// ---------------------------------------------------------------- actions
/** Upload a video; the backend starts the full analysis automatically. */
export async function uploadVideo(file: File): Promise<VideoAnalysis> {
  const body = new FormData();
  body.append("file", file);
  const v = mapVideo(await api<VideoAnalysis>("/api/videos", { method: "POST", body }));
  await refresh();
  schedule();
  return v;
}

export async function removeVideo(id: string) {
  try {
    await api<void>(`/api/videos/${id}`, { method: "DELETE" });
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 404) {
      toast.error("Could not remove video", { description: (e as Error).message });
      return;
    }
  }
  await refresh();
}

export async function reanalyse(id: string) {
  await api(`/api/videos/${id}/analyse`, { method: "POST" });
  await refresh();
  schedule();
}

export async function searchVideos(q: string): Promise<SearchResponse> {
  const r = await api<SearchResponse>(`/api/search?q=${encodeURIComponent(q)}`);
  return { ...r, results: r.results.map((x) => ({ ...x, thumbnail: apiUrl(x.thumbnail) })) };
}

export const reportUrl = (id: string) => apiUrl(`/api/videos/${id}/report.pdf`) ?? "";

/** Full analysis (segments, events, entities) of one completed video. Refetches if the video is re-analysed. */
export function useAnalysis(
  videoId: string | undefined,
  status: AnalysisStatus | undefined,
  version: unknown,
) {
  const [data, setData] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!videoId || status !== "Completed") {
      setData(null);
      return;
    }
    let live = true;
    api<Analysis>(`/api/videos/${videoId}/analysis`)
      .then((a) => {
        if (!live) return;
        setData({
          video: mapVideo(a.video),
          segments: a.segments.map(mapSegment),
          events: a.events.map(mapEvent),
          entities: a.entities.map(mapEntity),
        });
        setError(null);
      })
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [videoId, status, version]);
  return { data, error };
}

export function useTracks(
  videoId: string | undefined,
  status: AnalysisStatus | undefined,
  version: unknown,
) {
  const [tracks, setTracks] = useState<TrackedEntity[]>([]);
  useEffect(() => {
    if (!videoId || status !== "Completed") {
      setTracks([]);
      return;
    }
    let live = true;
    api<TrackedEntity[]>(`/api/videos/${videoId}/tracks`)
      .then((t) => live && setTracks(t))
      .catch(() => live && setTracks([]));
    return () => {
      live = false;
    };
  }, [videoId, status, version]);
  return tracks;
}

// ---------------------------------------------------------------- formatting
export function formatDate(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function clock(sec: number) {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${String(m).padStart(2, "0")}:${ss}`;
}

export const pct = (c: number | null | undefined) => (c == null ? "—" : `${Math.round(c * 100)}%`);

/** Human names for the event kinds the backend can report. */
export const KIND_LABEL: Record<string, string> = {
  transfer: "Object taken from a person",
  handover: "Object handed over",
  pickup: "Object picked up",
  carry: "Person carries object",
  approach: "Person approaches person",
  approach_flee: "Close contact, then leaving fast",
  following: "Person follows person",
  running: "Running",
  loitering: "Staying in one place",
  unattended: "Unattended object",
  abandoned: "Object left behind",
  vehicle_proximity: "Moving around a vehicle",
  restricted_entry: "Restricted-area entry",
  line_crossing: "Boundary line crossing",
  prolonged_presence: "Prolonged presence",
};
