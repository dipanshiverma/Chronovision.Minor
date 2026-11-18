import { Activity } from "lucide-react";

import { severityDot } from "@/components/chrono/badges";
import { cn } from "@/lib/utils";
import type { Overview } from "@/lib/video-store";

/**
 * Activity distribution: how many analysed 10-second segments fall in each class (time spent), with the number of
 * events of that class alongside. Everything comes from the stored analysis.
 */
export function ActivityChart({
  overview,
  className,
}: {
  overview: Overview | null;
  className?: string;
}) {
  const rows = overview?.distribution ?? [];
  const total = rows.reduce((n, r) => n + r.segments, 0);
  const max = Math.max(1, ...rows.map((r) => r.segments));

  return (
    <section className={cn("cv-card px-5 py-5", className)}>
      <div className="mb-4 flex items-center gap-3">
        <Activity className="size-8 text-menthe" strokeWidth={1.8} />
        <h2 className="text-[1.4rem] font-bold text-ink">Activity Distribution</h2>
      </div>
      {total === 0 ? (
        <p className="py-8 text-center text-muted-foreground">
          Analyse a video to see how its activity breaks down.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-3" aria-label="Segments by activity class">
            {rows.map((r) => (
              <li
                key={r.severity}
                className="grid grid-cols-[10.5rem_1fr_auto] items-center gap-3 text-[0.9rem] text-ink"
              >
                <span className="truncate font-medium">{r.label}</span>
                <span className="h-4 overflow-hidden rounded-full bg-secondary">
                  <span
                    className={cn("block h-full rounded-full", severityDot[r.severity])}
                    style={{
                      width: `${(r.segments / max) * 100}%`,
                      minWidth: r.segments ? "0.75rem" : 0,
                    }}
                  />
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {r.segments} seg · {r.events} ev
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-[0.8rem] text-muted-foreground">
            Segments are consecutive 10-second intervals; each takes the most serious event inside
            it.
          </p>
        </>
      )}
    </section>
  );
}
