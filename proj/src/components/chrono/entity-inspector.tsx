import { PawPrint, Package, Users } from "lucide-react";
import { useState } from "react";

import { GROUP_COLOR } from "@/components/chrono/detection-player";
import { cn } from "@/lib/utils";
import { clock, pct, type Entity } from "@/lib/video-store";

const TABS = [
  { group: "person", label: "People", icon: Users },
  { group: "animal", label: "Animals", icon: PawPrint },
  { group: "object", label: "Objects", icon: Package },
] as const;

function Trajectory({ entity }: { entity: Entity }) {
  const pts = entity.trajectory;
  if (pts.length < 2) return null;
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="h-32 w-full rounded-xl bg-card"
      role="img"
      aria-label={`Movement path of ${entity.name}`}
    >
      <polyline
        points={pts.map((p) => `${(p[1] ?? 0) * 100},${(p[2] ?? 0) * 100}`).join(" ")}
        fill="none"
        stroke={GROUP_COLOR[entity.group]}
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
      />
      <circle cx={(pts[0]![1] ?? 0) * 100} cy={(pts[0]![2] ?? 0) * 100} r={2.2} fill="#2b2523" />
      <circle
        cx={(pts.at(-1)![1] ?? 0) * 100}
        cy={(pts.at(-1)![2] ?? 0) * 100}
        r={2.2}
        fill={GROUP_COLOR[entity.group]}
        stroke="#2b2523"
        strokeWidth={0.8}
      />
    </svg>
  );
}

/** Pick Person 1 / Animal 1 / Object 1 and inspect where and when it appears; selecting it highlights it on the video. */
export function EntityInspector({
  entities,
  selectedId,
  onSelect,
  onSeek,
}: {
  entities: Entity[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onSeek: (t: number, end?: number) => void;
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]["group"]>("person");
  const list = entities.filter((e) => e.group === tab);
  const sel = entities.find((e) => e.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-3">
      <div role="tablist" className="flex gap-1.5">
        {TABS.map((t) => {
          const n = entities.filter((e) => e.group === t.group).length;
          return (
            <button
              key={t.group}
              role="tab"
              aria-selected={tab === t.group}
              type="button"
              onClick={() => setTab(t.group)}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium",
                tab === t.group
                  ? "bg-ink text-on-brand"
                  : "bg-secondary text-ink hover:bg-peche-soft",
              )}
            >
              <t.icon className="size-4" /> {t.label}{" "}
              <span className="tabular-nums opacity-80">{n}</span>
            </button>
          );
        })}
      </div>

      {list.length === 0 ? (
        <p className="rounded-xl bg-secondary px-4 py-6 text-center text-sm text-muted-foreground">
          None detected in this video.
        </p>
      ) : (
        <ul className="flex max-h-44 flex-wrap gap-2 overflow-y-auto pr-1">
          {list.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => onSelect(selectedId === e.id ? null : e.id)}
                aria-pressed={selectedId === e.id}
                className={cn(
                  "flex items-center gap-2 rounded-xl py-1 pl-1 pr-3 text-left text-sm",
                  selectedId === e.id
                    ? "bg-ink text-on-brand"
                    : "bg-secondary text-ink hover:bg-peche-soft",
                )}
              >
                <span className="size-8 overflow-hidden rounded-lg bg-muted">
                  {e.thumbnail && (
                    <img
                      src={e.thumbnail}
                      alt=""
                      loading="lazy"
                      className="size-full object-cover"
                    />
                  )}
                </span>
                <span className="leading-tight">
                  <span className="block font-semibold">{e.name}</span>
                  {e.group !== "person" && (
                    <span className="block text-[0.72rem] opacity-80">{e.label}</span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {sel && (
        <div className="rounded-2xl bg-secondary p-4">
          <div className="flex gap-4">
            <div className="size-24 shrink-0 overflow-hidden rounded-xl bg-muted">
              {sel.thumbnail && (
                <img src={sel.thumbnail} alt={sel.name} className="size-full object-cover" />
              )}
            </div>
            <dl className="grid flex-1 grid-cols-2 gap-x-4 gap-y-1 text-sm text-ink">
              <dt className="text-muted-foreground">Category</dt>
              <dd className="font-semibold">{sel.label}</dd>
              <dt className="text-muted-foreground">First seen</dt>
              <dd className="font-semibold tabular-nums">{clock(sel.firstSec)}</dd>
              <dt className="text-muted-foreground">Last seen</dt>
              <dd className="font-semibold tabular-nums">{clock(sel.lastSec)}</dd>
              <dt className="text-muted-foreground">Observed</dt>
              <dd className="font-semibold tabular-nums">{sel.durationSec.toFixed(1)}s</dd>
              <dt className="text-muted-foreground">Confidence</dt>
              <dd className="font-semibold">{pct(sel.confidence)}</dd>
            </dl>
          </div>
          <p className="mt-3 text-sm font-medium text-ink">Appearances</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {sel.appearances.map((a, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onSeek(a[0] ?? 0, a[1])}
                className="rounded-full bg-card px-3 py-1 text-[0.82rem] font-medium tabular-nums text-ink hover:bg-peche-soft"
              >
                {clock(a[0] ?? 0)} – {clock(a[1] ?? 0)}
              </button>
            ))}
          </div>
          {sel.group !== "object" && (
            <div className="mt-3">
              <p className="mb-1 text-sm font-medium text-ink">Movement path</p>
              <Trajectory entity={sel} />
            </div>
          )}
          <p className="mt-2 text-[0.75rem] text-muted-foreground">
            Identity is by position and motion only (no face or appearance matching); someone who
            leaves and returns may appear as a new ID.
          </p>
        </div>
      )}
    </div>
  );
}
