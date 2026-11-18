import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Check, Loader2, Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { PageIntro, PageShell } from "@/components/chrono/page-shell";
import { RecentAnalyses } from "@/components/chrono/recent-analyses";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  STAGES,
  reanalyse,
  uploadVideo,
  useVideoStore,
  type VideoAnalysis,
} from "@/lib/video-store";

export const Route = createFileRoute("/analyse")({
  head: () => ({
    meta: [
      { title: "Analyse Video — ChronoVision" },
      {
        name: "description",
        content: "Upload surveillance footage and ChronoVision analyses it automatically.",
      },
      { property: "og:title", content: "Analyse Video — ChronoVision" },
      {
        property: "og:description",
        content: "Upload surveillance footage and ChronoVision analyses it automatically.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: AnalysePage,
});

const VIDEO_EXT = /\.(mp4|mov|webm|avi|mkv|m4v)$/i;

/** Live pipeline: the stage list is the backend's real stage, not an animation. */
function ProcessingCard({ video }: { video: VideoAnalysis }) {
  const failed = video.status === "Failed";
  const current = Math.max(0, STAGES.indexOf(video.stage as (typeof STAGES)[number]));
  return (
    <div className="cv-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-bold text-ink" title={video.filename}>
            {video.filename}
          </p>
          <p className="text-sm text-muted-foreground">
            {failed
              ? "Analysis failed"
              : video.status === "Queued"
                ? "Waiting for the analysis worker"
                : video.stage}
          </p>
        </div>
        {failed ? (
          <Button variant="peche" size="sm" onClick={() => void reanalyse(video.id)}>
            Try again
          </Button>
        ) : (
          <span className="text-2xl font-bold tabular-nums text-ink">
            {Math.round(video.progress * 100)}%
          </span>
        )}
      </div>

      <div
        className="mt-3 h-2.5 overflow-hidden rounded-full bg-secondary"
        role="progressbar"
        aria-valuenow={Math.round(video.progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            failed ? "bg-nectarine" : "bg-menthe",
          )}
          style={{ width: `${Math.max(3, video.progress * 100)}%` }}
        />
      </div>

      {failed ? (
        <p className="mt-3 flex items-start gap-2 rounded-xl bg-nectarine-soft px-3 py-2 text-sm text-ink">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {video.error ?? "Unknown error"}
        </p>
      ) : (
        <ol className="mt-4 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2 xl:grid-cols-4">
          {STAGES.slice(0, -1).map((s, i) => {
            const done = i < current;
            const active = i === current && video.status === "Processing";
            return (
              <li
                key={s}
                className={cn(
                  "flex items-center gap-2 text-[0.88rem]",
                  done || active ? "text-ink" : "text-muted-foreground",
                )}
              >
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full",
                    done ? "bg-menthe" : active ? "bg-peche" : "bg-secondary",
                  )}
                >
                  {done ? (
                    <Check className="size-3" />
                  ) : active ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : null}
                </span>
                {s}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

function AnalysePage() {
  const { videos } = useVideoStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    const ok = list.filter((f) => VIDEO_EXT.test(f.name));
    if (ok.length < list.length)
      toast.error("Only MP4, MOV, WEBM, AVI or MKV videos are supported.");
    if (!ok.length) return;
    setBusy(true);
    for (const f of ok) {
      try {
        await uploadVideo(f);
        toast.success(`${f.name} uploaded`, { description: "Analysis started automatically." });
      } catch (e) {
        toast.error(`Could not upload ${f.name}`, { description: (e as Error).message });
      }
    }
    setBusy(false);
  };

  const active = videos.filter((v) => v.status !== "Completed");
  const latestDone = videos.find((v) => v.status === "Completed");

  return (
    <PageShell title="Analyse Video">
      <PageIntro eyebrow="Analyse" title="Bring in new" accent="footage.">
        Drop in a recording. ChronoVision detects and tracks people, animals and objects, then
        describes what happens in every 10-second interval.
      </PageIntro>

      <div className="relative flex flex-col gap-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault();
            setDragging(false);
            void upload(e.dataTransfer.files);
          }}
          className={cn(
            "cv-card flex flex-col items-center justify-center gap-4 border-2 border-dashed p-10 text-center transition-colors",
            dragging ? "border-nectarine bg-secondary" : "border-border",
          )}
        >
          <div className="grid size-16 place-items-center rounded-full bg-peche-soft text-ink">
            <Upload className="size-7" />
          </div>
          <p className="text-xl font-bold text-ink">Drop a video here</p>
          <p className="text-muted-foreground">
            MP4, MOV, WEBM, AVI or MKV — analysis starts automatically
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="video/*,.mkv"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) void upload(e.target.files);
              e.target.value = "";
            }}
          />
          <Button
            variant="peche"
            size="action"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            <Upload /> {busy ? "Uploading…" : "Choose Video"}
          </Button>
        </div>

        {active.length > 0 && (
          <div className="flex flex-col gap-4" aria-label="Analyses in progress">
            {active.map((v) => (
              <ProcessingCard key={v.id} video={v} />
            ))}
          </div>
        )}

        {active.length === 0 && latestDone && (
          <p className="rounded-2xl bg-menthe-soft px-5 py-3 text-ink">
            Latest analysis is ready:{" "}
            <Link
              to="/timeline"
              search={{ video: latestDone.id }}
              className="font-semibold underline underline-offset-4"
            >
              {latestDone.filename}
            </Link>{" "}
            — {latestDone.stats?.people ?? 0} people, {latestDone.stats?.animals ?? 0} animals,{" "}
            {latestDone.stats?.objects ?? 0} objects, {latestDone.stats?.events ?? 0} events.
          </p>
        )}

        <RecentAnalyses videos={videos} showAllLink={false} />
      </div>
    </PageShell>
  );
}
