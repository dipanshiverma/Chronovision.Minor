import { ChevronDown, PawPrint, Package, Play, ShieldAlert, Users } from "lucide-react";
import { useState } from "react";

import { SeverityBadge, severityDot } from "@/components/chrono/badges";
import { cn } from "@/lib/utils";
import { clock, pct, type Segment } from "@/lib/video-store";

function Count({ icon: Icon, n, label }: { icon: typeof Users; n: number; label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-[0.8rem] font-medium tabular-nums text-ink"
      title={label}
    >
      <Icon className="size-3.5" aria-hidden="true" /> {n}
      <span className="sr-only"> {label}</span>
    </span>
  );
}

/** Chronological 10-second activity timeline. Every row is real analysis output; click a time to jump to the moment. */
export function SegmentTimeline({
  segments,
  currentTime,
  onSeek,
}: {
  segments: Segment[];
  currentTime: number;
  onSeek: (start: number, end: number) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (!segments.length) {
    return (
      <p className="rounded-xl bg-secondary px-4 py-8 text-center text-muted-foreground">
        No segments match these filters.
      </p>
    );
  }

  return (
    <ol className="relative flex flex-col gap-3">
      <span
        className="absolute bottom-3 left-[0.72rem] top-3 w-0.5 rounded bg-border"
        aria-hidden="true"
      />
      {segments.map((s) => {
        const active = currentTime >= s.startSec && currentTime < s.endSec;
        const expanded = !!open[s.id];
        const flagged = s.classification === "suspicious" || s.classification === "high";
        return (
          <li key={s.id} className="relative pl-9">
            <span
              className={cn(
                "absolute left-0 top-4 size-6 rounded-full border-4 border-card",
                severityDot[s.classification],
                active && "scale-125",
              )}
              aria-hidden="true"
            />
            <article
              className={cn(
                "rounded-2xl p-4 transition-colors",
                active ? "bg-peche-soft" : "bg-secondary/60",
                flagged && "ring-2 ring-nectarine/60",
              )}
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <button
                  type="button"
                  onClick={() => onSeek(s.startSec, s.endSec)}
                  className="inline-flex items-center gap-2 rounded-full bg-card px-3 py-1.5 text-sm font-bold tabular-nums text-ink hover:bg-peche"
                  aria-label={`Play ${clock(s.startSec)} to ${clock(s.endSec)}`}
                >
                  <Play className="size-3.5 fill-current" /> {clock(s.startSec)} – {clock(s.endSec)}
                </button>
                <SeverityBadge severity={s.classification} />
                {flagged && (
                  <span className="inline-flex items-center gap-1 text-sm font-semibold text-ink">
                    <ShieldAlert className="size-4 text-nectarine" /> Needs review
                  </span>
                )}
                <span className="ml-auto flex flex-wrap items-center gap-1.5">
                  <Count icon={Users} n={s.people} label="people" />
                  <Count icon={PawPrint} n={s.animals} label="animals" />
                  <Count icon={Package} n={s.objects} label="objects" />
                </span>
              </div>

              <p className="mt-3 max-w-3xl text-[0.98rem] leading-relaxed text-ink">{s.summary}</p>

              {(s.interactions.length > 0 || Object.keys(s.objectsBreakdown).length > 0) && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {s.interactions.map((i) => (
                    <span
                      key={i}
                      className="rounded-full bg-nectarine-soft px-2.5 py-1 text-[0.78rem] font-medium text-ink"
                    >
                      {i}
                    </span>
                  ))}
                  {Object.entries(s.objectsBreakdown).map(([k, n]) => (
                    <span
                      key={k}
                      className="rounded-full bg-card px-2.5 py-1 text-[0.78rem] text-ink"
                    >
                      {k}
                      {n > 1 ? ` ×${n}` : ""}
                    </span>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={() => setOpen({ ...open, [s.id]: !expanded })}
                aria-expanded={expanded}
                className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-ink/80 hover:text-ink"
              >
                <ChevronDown
                  className={cn("size-4 transition-transform", expanded && "rotate-180")}
                />
                {expanded ? "Hide details" : "Details"}
              </button>

              {expanded && (
                <div className="mt-3 grid gap-4 border-t border-border pt-3 md:grid-cols-[minmax(0,16rem)_1fr]">
                  {s.frame ? (
                    <img
                      src={s.frame}
                      alt={`Evidence frame ${clock(s.startSec)}`}
                      loading="lazy"
                      className="w-full rounded-xl"
                    />
                  ) : (
                    <div className="rounded-xl bg-card p-6 text-sm text-muted-foreground">
                      No evidence frame.
                    </div>
                  )}
                  <div className="space-y-3 text-sm text-ink">
                    <p>
                      <span className="text-muted-foreground">Detection confidence: </span>
                      <strong>{pct(s.confidence)}</strong>
                    </p>
                    <p>
                      <span className="text-muted-foreground">Tracked IDs in view: </span>
                      {s.entities.length ? s.entities.map((e) => e.name).join(", ") : "none"}
                    </p>
                    {s.events.length > 0 ? (
                      <ul className="space-y-2">
                        {s.events.map((e) => (
                          <li key={e.id} className="rounded-xl bg-card p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <SeverityBadge severity={e.severity} />
                              <button
                                type="button"
                                onClick={() => onSeek(e.startSec, e.endSec ?? e.startSec + 2)}
                                className="font-semibold underline-offset-4 hover:underline"
                              >
                                {e.title}
                              </button>
                              <span className="tabular-nums text-muted-foreground">
                                {clock(e.startSec)} · confidence {pct(e.confidence)}
                              </span>
                            </div>
                            <p className="mt-1 text-[0.88rem] text-ink/80">{e.description}</p>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted-foreground">
                        No interactions or incidents in this interval.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </article>
          </li>
        );
      })}
    </ol>
  );
}
