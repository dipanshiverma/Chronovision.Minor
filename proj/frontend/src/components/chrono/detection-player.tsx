import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";

import type { TrackedEntity } from "@/lib/video-store";

export interface PlayerHandle {
  /** Jump to a time; optionally play and stop automatically at `end`. */
  seek: (t: number, opts?: { play?: boolean; end?: number }) => void;
}

export const GROUP_COLOR: Record<TrackedEntity["group"], string> = {
  person: "#D7897F", // nectarine
  animal: "#96C7B3", // menthe
  object: "#F9B95C", // peche
};

interface Props {
  src: string;
  tracks: TrackedEntity[];
  overlay: boolean;
  /** Which categories to draw. */
  groups: Record<TrackedEntity["group"], boolean>;
  /** When set, this entity is emphasised and others are dimmed. */
  highlightId?: string | null;
  onTime?: (t: number) => void;
  className?: string;
}

type Box = [number, number, number, number, number];

/** Box of an entity at time t: nearest observation, or linear interpolation across a short gap. */
function boxAt(obs: number[][], t: number): Box | null {
  if (!obs.length) return null;
  let lo = 0;
  let hi = obs.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (obs[mid]![0]! <= t) lo = mid;
    else hi = mid - 1;
  }
  const a = obs[lo]!;
  const b = obs[lo + 1];
  if (Math.abs(a[0]! - t) <= 0.12) return [a[1]!, a[2]!, a[3]!, a[4]!, a[5]!];
  if (b && b[0]! - a[0]! <= 0.7 && t >= a[0]! && t <= b[0]!) {
    const f = (t - a[0]!) / (b[0]! - a[0]!);
    return [0, 1, 2, 3]
      .map((i) => a[i + 1]! + f * (b[i + 1]! - a[i + 1]!))
      .concat(Math.min(a[5]!, b[5]!)) as Box;
  }
  return null;
}

/** Video with a canvas overlay of tracked boxes, labels and confidences, synchronised to playback. */
export const DetectionPlayer = forwardRef<PlayerHandle, Props>(function DetectionPlayer(
  { src, tracks, overlay, groups, highlightId, onTime, className },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stopAt = useRef<number | null>(null);
  const raf = useRef<number | null>(null);
  const latest = useRef({ tracks, overlay, groups, highlightId });
  latest.current = { tracks, overlay, groups, highlightId };

  const draw = useCallback(() => {
    const v = videoRef.current;
    const c = canvasRef.current;
    if (!v || !c) return;
    const r = v.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(r.width * dpr) || c.height !== Math.round(r.height * dpr)) {
      c.width = Math.round(r.width * dpr);
      c.height = Math.round(r.height * dpr);
    }
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    const { tracks: tr, overlay: on, groups: g, highlightId: hid } = latest.current;
    if (!on || !v.videoWidth) return;

    // The video is letterboxed inside its element (object-contain): map normalised boxes onto the picture area.
    const s = Math.min(r.width / v.videoWidth, r.height / v.videoHeight);
    const cw = v.videoWidth * s;
    const ch = v.videoHeight * s;
    const ox = (r.width - cw) / 2;
    const oy = (r.height - ch) / 2;
    const t = v.currentTime;
    ctx.font = "600 12px 'DM Sans', system-ui, sans-serif";
    ctx.textBaseline = "middle";

    for (const e of tr) {
      if (!g[e.group]) continue;
      const b = boxAt(e.obs, t);
      if (!b) continue;
      const hot = hid === e.id;
      const dim = !!hid && !hot;
      const x = ox + b[0] * cw;
      const y = oy + b[1] * ch;
      const w = (b[2] - b[0]) * cw;
      const h = (b[3] - b[1]) * ch;
      const col = GROUP_COLOR[e.group];
      ctx.globalAlpha = dim ? 0.3 : 1;
      ctx.lineWidth = hot ? 4 : 2.5;
      ctx.strokeStyle = col;
      ctx.strokeRect(x, y, w, h);
      const label = `${e.name}${e.group === "person" ? "" : ` ${e.label}`} ${b[4].toFixed(2)}`;
      const tw = ctx.measureText(label).width + 10;
      const ly = Math.max(oy, y - 20);
      ctx.fillStyle = col;
      ctx.fillRect(x - 1, ly, tw, 20);
      ctx.fillStyle = "#2b2523";
      ctx.fillText(label, x + 4, ly + 10.5);
    }
    ctx.globalAlpha = 1;
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      seek(t, opts) {
        const v = videoRef.current;
        if (!v) return;
        stopAt.current = opts?.end ?? null;
        const go = () => {
          v.currentTime = Math.max(0, t);
          if (opts?.play) void v.play().catch(() => undefined); // autoplay may be blocked; the user can press play
          draw();
        };
        if (v.readyState >= 1) go();
        else v.addEventListener("loadedmetadata", go, { once: true });
      },
    }),
    [draw],
  );

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const loop = () => {
      draw();
      raf.current = requestAnimationFrame(loop);
    };
    const onPlay = () => {
      if (raf.current == null) raf.current = requestAnimationFrame(loop);
    };
    const onPause = () => {
      if (raf.current != null) cancelAnimationFrame(raf.current);
      raf.current = null;
      draw();
    };
    const onTimeUpdate = () => {
      if (stopAt.current != null && v.currentTime >= stopAt.current) {
        v.pause();
        stopAt.current = null;
      }
      onTime?.(v.currentTime);
      draw();
    };
    const ro = new ResizeObserver(draw);
    ro.observe(v);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("ended", onPause);
    v.addEventListener("seeked", onTimeUpdate);
    v.addEventListener("timeupdate", onTimeUpdate);
    v.addEventListener("loadedmetadata", draw);
    return () => {
      ro.disconnect();
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("ended", onPause);
      v.removeEventListener("seeked", onTimeUpdate);
      v.removeEventListener("timeupdate", onTimeUpdate);
      v.removeEventListener("loadedmetadata", draw);
      if (raf.current != null) cancelAnimationFrame(raf.current);
      raf.current = null;
    };
  }, [draw, onTime]);

  // Redraw when toggles / highlighted entity / tracks change while paused.
  useEffect(draw, [draw, tracks, overlay, groups, highlightId]);

  return (
    <div className={className}>
      <div className="relative aspect-video w-full overflow-hidden rounded-2xl bg-ink">
        <video
          ref={videoRef}
          src={src}
          controls
          playsInline
          preload="metadata"
          className="absolute inset-0 size-full object-contain"
        />
        {/* pointer-events-none so the native controls stay usable; the canvas stops above the control bar area visually */}
        <canvas
          ref={canvasRef}
          className="pointer-events-none absolute inset-0 size-full"
          aria-hidden="true"
        />
      </div>
    </div>
  );
});
