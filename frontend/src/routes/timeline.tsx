import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { FileText, PawPrint, Package, ShieldAlert, Sparkles, Users } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { StatusBadge } from "@/components/chrono/badges";
import {
  DetectionPlayer,
  GROUP_COLOR,
  type PlayerHandle,
} from "@/components/chrono/detection-player";
import { EntityInspector } from "@/components/chrono/entity-inspector";
import { PageIntro, PageShell } from "@/components/chrono/page-shell";
import { SegmentTimeline } from "@/components/chrono/segment-timeline";
import { cn } from "@/lib/utils";
import {
  KIND_LABEL,
  SEVERITY_ORDER,
  useAnalysis,
  useTracks,
  useVideoStore,
  type Entity,
  type Segment,
  type VideoAnalysis,
} from "@/lib/video-store";

const searchSchema = z.object({
  video: z.string().optional(),
  t: z.coerce.number().optional(),
  sev: z.enum(["unusual", "suspicious"]).optional(),
  kind: z.string().optional(),
});

export const Route = createFileRoute("/timeline")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Event Timeline — ChronoVision" },
      {
        name: "description",
        content:
          "A chronological, 10-second-by-10-second account of what happened in each analysed video.",
      },
      { property: "og:title", content: "Event Timeline — ChronoVision" },
      {
        property: "og:description",
        content: "A chronological account of what happened in each analysed video.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: TimelinePage,
});

const selectCls =
  "h-11 rounded-2xl bg-card px-4 text-sm font-medium text-ink shadow-soft outline-none ring-ring/40 focus:ring-2";

function Chip({
  icon: Icon,
  n,
  label,
  tone,
}: {
  icon: typeof Users;
  n: number;
  label: string;
  tone?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold tabular-nums text-ink",
        tone ?? "bg-secondary",
      )}
    >
      <Icon className="size-4" aria-hidden="true" /> {n}{" "}
      <span className="font-medium text-ink/75">{label}</span>
    </span>
  );
}

function VideoSection({
  video,
  sev,
  kind,
  seekT,
}: {
  video: VideoAnalysis;
  sev?: "unusual" | "suspicious";
  kind?: string;
  seekT?: number;
}) {
  const { data, error } = useAnalysis(video.id, video.status, video.stats?.events);
  const tracks = useTracks(video.id, video.status, video.stats?.events);
  const player = useRef<PlayerHandle>(null);
  const section = useRef<HTMLElement>(null);
  const [overlay, setOverlay] = useState(true);
  const [groups, setGroups] = useState({ person: true, animal: true, object: true });
  const [selected, setSelected] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const onTime = useCallback((t: number) => setNow(t), []);

  const seek = useCallback((start: number, end?: number) => {
    player.current?.seek(Math.max(0, start - 0.5), {
      play: true,
      ...(end != null ? { end: end + 0.5 } : {}),
    });
  }, []);

  // Deep link from search / events: ?video=…&t=… jumps to that moment once the player is ready.
  useEffect(() => {
    if (seekT == null || !data) return;
    section.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    player.current?.seek(Math.max(0, seekT - 1), { play: true, end: seekT + 5 });
  }, [seekT, data]);

  const st = video.stats;
  const minSev = sev ? SEVERITY_ORDER[sev] : 0;
  const visible: Segment[] = (data?.segments ?? []).filter(
    (s) =>
      SEVERITY_ORDER[s.classification] >= minSev &&
      (!kind || s.events.some((e) => e.kind === kind)),
  );

  return (
    <section
      ref={section}
      className="cv-card relative p-5 md:p-6"
      aria-label={`Analysis of ${video.filename}`}
    >
      <header className="flex flex-wrap items-center gap-4">
        <div className="h-16 w-28 shrink-0 overflow-hidden rounded-xl bg-muted">
          {video.thumbnail && (
            <img src={video.thumbnail} alt="" className="size-full object-cover" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-2xl font-bold text-ink" title={video.filename}>
            {video.filename}
          </h2>
          <p className="text-sm text-muted-foreground">
            {video.duration ?? "—"}
            {video.width ? ` · ${video.width}×${video.height}` : ""}
            {video.fps ? ` · ${video.fps.toFixed(0)} fps` : ""}
          </p>
        </div>
        <StatusBadge status={video.status} progress={video.progress} />
        {video.status === "Completed" && (
          <Link
            to="/reports"
            search={{ video: video.id }}
            className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-4 py-2 text-sm font-medium text-ink hover:bg-peche-soft"
          >
            <FileText className="size-4" /> Report
          </Link>
        )}
      </header>

      {video.status !== "Completed" ? (
        <p className="mt-5 rounded-xl bg-secondary px-4 py-8 text-center text-muted-foreground">
          {video.status === "Failed"
            ? `Analysis failed: ${video.error ?? "unknown error"}`
            : `${video.stage} (${Math.round(video.progress * 100)}%) — the timeline appears when the analysis finishes.`}
        </p>
      ) : (
        <>
          {st && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Chip icon={Users} n={st.people} label="unique people" />
              <Chip icon={PawPrint} n={st.animals} label="unique animals" />
              <Chip icon={Package} n={st.objects} label="unique objects" />
              <Chip icon={Sparkles} n={st.events} label="events" />
              <Chip
                icon={ShieldAlert}
                n={st.incidents}
                label="suspicious incidents"
                tone={st.incidents ? "bg-nectarine-soft" : "bg-secondary"}
              />
            </div>
          )}

          <div className="mt-5 grid grid-cols-1 gap-6 xl:grid-cols-[1.25fr_1fr]">
            <div className="min-w-0">
              <DetectionPlayer
                ref={player}
                src={video.src}
                tracks={tracks}
                overlay={overlay}
                groups={groups}
                highlightId={selected}
                onTime={onTime}
              />
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  role="switch"
                  aria-checked={overlay}
                  onClick={() => setOverlay(!overlay)}
                  className={cn(
                    "rounded-full px-4 py-2 text-sm font-semibold text-ink",
                    overlay ? "bg-menthe" : "bg-secondary",
                  )}
                >
                  Detection overlay {overlay ? "on" : "off"}
                </button>
                {(["person", "animal", "object"] as const).map((g) => (
                  <button
                    key={g}
                    type="button"
                    aria-pressed={groups[g]}
                    disabled={!overlay}
                    onClick={() => setGroups({ ...groups, [g]: !groups[g] })}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium text-ink disabled:opacity-40",
                      groups[g] ? "bg-card ring-2 ring-border" : "bg-secondary",
                    )}
                  >
                    <span className="size-3 rounded-full" style={{ background: GROUP_COLOR[g] }} />
                    {g === "person" ? "People" : g === "animal" ? "Animals" : "Objects"}
                  </button>
                ))}
              </div>
            </div>
            <div className="min-w-0">
              <h3 className="mb-2 text-lg font-bold text-ink">Inspect entities</h3>
              <EntityInspector
                entities={(data?.entities ?? []) as Entity[]}
                selectedId={selected}
                onSelect={setSelected}
                onSeek={(t, end) => seek(t, end)}
              />
            </div>
          </div>

          <h3 className="mb-3 mt-8 text-lg font-bold text-ink">
            Activity timeline{" "}
            <span className="font-medium text-muted-foreground">
              · {visible.length} of {data?.segments.length ?? 0} segments
            </span>
          </h3>
          {error ? (
            <p className="rounded-xl bg-nectarine-soft px-4 py-3 text-ink">
              Could not load the analysis: {error}
            </p>
          ) : (
            <SegmentTimeline segments={visible} currentTime={now} onSeek={(a, b) => seek(a, b)} />
          )}
        </>
      )}
    </section>
  );
}

function TimelinePage() {
  const { video, t, sev, kind } = Route.useSearch();
  const navigate = useNavigate({ from: "/timeline" });
  const { videos } = useVideoStore();
  const shown = video ? videos.filter((v) => v.id === video) : videos;
  const set = (
    patch: Partial<{
      video: string | undefined;
      sev: "unusual" | "suspicious" | undefined;
      kind: string | undefined;
    }>,
  ) => navigate({ search: (prev) => ({ ...prev, ...patch, t: undefined }), replace: true });

  return (
    <PageShell title="Event Timeline">
      <PageIntro eyebrow="Timeline" title="What happened," accent="moment by moment.">
        Each video is split into 10-second intervals with a description of the people, animals and
        objects in view and what they do. Select a time to jump to it.
      </PageIntro>

      <div className="relative mb-6 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by video">
          <button
            type="button"
            onClick={() => set({ video: undefined })}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-medium",
              !video ? "bg-ink text-on-brand" : "bg-card text-ink hover:bg-peche-soft",
            )}
          >
            All videos
          </button>
          {videos.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => set({ video: v.id })}
              className={cn(
                "max-w-[14rem] truncate rounded-full px-4 py-2 text-sm font-medium",
                video === v.id ? "bg-ink text-on-brand" : "bg-card text-ink hover:bg-peche-soft",
              )}
              title={v.filename}
            >
              {v.filename}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-3">
          <select
            aria-label="Filter by suspicion level"
            className={selectCls}
            value={sev ?? ""}
            onChange={(e) =>
              set({ sev: (e.target.value || undefined) as "unusual" | "suspicious" | undefined })
            }
          >
            <option value="">All activity</option>
            <option value="unusual">Unusual or worse</option>
            <option value="suspicious">Suspicious or worse</option>
          </select>
          <select
            aria-label="Filter by event type"
            className={selectCls}
            value={kind ?? ""}
            onChange={(e) => set({ kind: e.target.value || undefined })}
          >
            <option value="">All event types</option>
            {Object.entries(KIND_LABEL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="relative flex flex-col gap-6">
        {shown.map((v) => (
          <VideoSection
            key={v.id}
            video={v}
            {...(sev ? { sev } : {})}
            {...(kind ? { kind } : {})}
            {...(t != null && (!video || video === v.id) ? { seekT: t } : {})}
          />
        ))}
        {shown.length === 0 && (
          <p className="cv-card px-6 py-12 text-center text-muted-foreground">
            No analysed videos yet.{" "}
            <Link to="/analyse" className="font-semibold text-ink underline underline-offset-4">
              Upload one
            </Link>{" "}
            to see its timeline.
          </p>
        )}
      </div>
    </PageShell>
  );
}
