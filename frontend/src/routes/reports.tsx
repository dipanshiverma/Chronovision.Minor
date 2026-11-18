import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Download, FileText } from "lucide-react";
import type { ReactNode } from "react";
import { z } from "zod";

import { SeverityBadge } from "@/components/chrono/badges";
import { PageIntro, PageShell } from "@/components/chrono/page-shell";
import { cn } from "@/lib/utils";
import {
  clock,
  pct,
  reportUrl,
  useAnalysis,
  useVideoStore,
  type Analysis,
  type Entity,
} from "@/lib/video-store";

const searchSchema = z.object({ video: z.string().optional() });

export const Route = createFileRoute("/reports")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Reports — ChronoVision" },
      {
        name: "description",
        content:
          "Per-video analysis reports with tracking, timeline, incidents and evidence, downloadable as PDF.",
      },
      { property: "og:title", content: "Reports — ChronoVision" },
      { property: "og:description", content: "Per-video analysis reports, downloadable as PDF." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ReportsPage,
});

const th = "px-3 py-2 font-medium";
const td = "px-3 py-2 align-top";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h3 className="mb-3 text-xl font-bold text-ink">{title}</h3>
      {children}
    </section>
  );
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[0.88rem] text-ink">
        <thead>
          <tr className="bg-menthe-soft">
            {head.map((h, i) => (
              <th
                key={h}
                className={cn(
                  th,
                  i === 0 && "rounded-l-xl",
                  i === head.length - 1 && "rounded-r-xl",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function EntityTable({ title, rows }: { title: string; rows: Entity[] }) {
  return (
    <Section title={`${title} (${rows.length})`}>
      {rows.length === 0 ? (
        <p className="text-muted-foreground">None detected.</p>
      ) : (
        <Table
          head={[
            "ID",
            "Category",
            "First seen",
            "Last seen",
            "Observed",
            "Confidence",
            "Appearances",
          ]}
        >
          {rows.map((e) => (
            <tr key={e.id} className="border-b border-border last:border-0">
              <td className={cn(td, "font-semibold")}>{e.name}</td>
              <td className={td}>{e.label}</td>
              <td className={cn(td, "tabular-nums")}>{clock(e.firstSec)}</td>
              <td className={cn(td, "tabular-nums")}>{clock(e.lastSec)}</td>
              <td className={cn(td, "tabular-nums")}>{e.durationSec.toFixed(0)}s</td>
              <td className={td}>{pct(e.confidence)}</td>
              <td className={cn(td, "tabular-nums")}>
                {e.appearances.map((a) => `${clock(a[0] ?? 0)}–${clock(a[1] ?? 0)}`).join(", ")}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Section>
  );
}

const INTERACTION_KINDS = new Set([
  "carry",
  "approach",
  "handover",
  "transfer",
  "pickup",
  "approach_flee",
  "following",
  "vehicle_proximity",
  "abandoned",
  "unattended",
]);

function Report({ a }: { a: Analysis }) {
  const v = a.video;
  const st = v.stats;
  const incidents = a.events.filter((e) => e.severity === "suspicious" || e.severity === "high");
  const interactions = a.events.filter((e) => INTERACTION_KINDS.has(e.kind));
  const frames = a.segments.filter((s) => s.frame);
  const by = (g: Entity["group"]) => a.entities.filter((e) => e.group === g);

  return (
    <article className="cv-card p-6 md:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="eyebrow mb-2 text-ink">Analysis report</p>
          <h2 className="font-display-italic text-4xl leading-tight text-ink">{v.filename}</h2>
        </div>
        <a
          href={reportUrl(v.id)}
          download
          className="inline-flex items-center gap-2 rounded-full bg-peche px-6 py-3 text-base font-semibold text-ink shadow-soft transition-transform hover:scale-[1.02]"
        >
          <Download className="size-5" /> Download PDF
        </a>
      </header>

      <Section title="Video information">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-8 gap-y-1.5 text-[0.95rem] text-ink">
          <dt className="text-muted-foreground">Upload date</dt>
          <dd>{v.uploadedAt}</dd>
          <dt className="text-muted-foreground">Duration</dt>
          <dd>{v.duration ?? "—"}</dd>
          <dt className="text-muted-foreground">Resolution</dt>
          <dd>{v.width ? `${v.width} × ${v.height}` : "—"}</dd>
          <dt className="text-muted-foreground">Frame rate</dt>
          <dd>{v.fps ? `${v.fps.toFixed(1)} fps` : "—"}</dd>
        </dl>
      </Section>

      {st && (
        <Section title="Summary">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
            {[
              ["Unique people", st.people],
              ["Unique animals", st.animals],
              ["Unique objects", st.objects],
              ["Events", st.events],
              ["Suspicious incidents", st.incidents],
            ].map(([l, n]) => (
              <div key={l} className="rounded-2xl bg-secondary px-4 py-3">
                <p className="text-3xl font-bold tabular-nums text-ink">{n}</p>
                <p className="text-sm text-ink/80">{l}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[0.8rem] text-muted-foreground">
            Counts are unique tracked entities, not per-frame detections. Someone who leaves and
            returns may be counted twice.
          </p>
          {Object.keys(st.objectBreakdown).length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(st.objectBreakdown).map(([k, n]) => (
                <span
                  key={k}
                  className="rounded-full bg-peche-soft px-3 py-1.5 text-sm font-medium text-ink"
                >
                  {k} × {n}
                </span>
              ))}
            </div>
          )}
        </Section>
      )}

      <Section title={`Suspicious activity incidents (${incidents.length})`}>
        {incidents.length === 0 ? (
          <p className="text-muted-foreground">
            No potentially suspicious or high-priority activity was detected.
          </p>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {incidents.map((e) => (
              <li key={e.id} className="rounded-2xl bg-secondary/60 p-4">
                {e.frame && (
                  <img
                    src={e.frame}
                    alt={`Evidence for ${e.title}`}
                    loading="lazy"
                    className="mb-3 w-full rounded-xl"
                  />
                )}
                <SeverityBadge severity={e.severity} />
                <p className="mt-2 font-semibold text-ink">{e.title}</p>
                <p className="text-sm text-ink/80">{e.description}</p>
                <p className="mt-1 text-[0.8rem] tabular-nums text-muted-foreground">
                  {clock(e.startSec)} · confidence {pct(e.confidence)} ·{" "}
                  {e.entities.map((x) => x.name).join(", ")}
                </p>
                <Link
                  to="/timeline"
                  search={{ video: v.id, t: e.startSec }}
                  className="mt-2 inline-block text-sm font-semibold text-ink underline underline-offset-4"
                >
                  Jump to this moment
                </Link>
                <p className="mt-2 text-[0.75rem] text-muted-foreground">
                  Automated visual inference, not proof that a crime occurred.
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <EntityTable title="People tracked" rows={by("person")} />
      <EntityTable title="Animals tracked" rows={by("animal")} />
      <EntityTable title="Objects tracked" rows={by("object")} />

      <Section title={`Detected interactions (${interactions.length})`}>
        {interactions.length === 0 ? (
          <p className="text-muted-foreground">
            No person-to-person or person-to-object interactions were detected.
          </p>
        ) : (
          <Table head={["Time", "Interaction", "Classification", "Confidence"]}>
            {interactions.map((e) => (
              <tr key={e.id} className="border-b border-border last:border-0">
                <td className={cn(td, "tabular-nums")}>{clock(e.startSec)}</td>
                <td className={td}>{e.description}</td>
                <td className={td}>
                  <SeverityBadge severity={e.severity} />
                </td>
                <td className={td}>{pct(e.confidence)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Activity timeline (10-second segments)">
        <Table head={["Time", "Activity", "People / animals / objects", "Class", "Confidence"]}>
          {a.segments.map((s) => (
            <tr key={s.id} className="border-b border-border last:border-0">
              <td className={cn(td, "whitespace-nowrap tabular-nums")}>
                {clock(s.startSec)}–{clock(s.endSec)}
              </td>
              <td className={td}>{s.summary}</td>
              <td className={cn(td, "whitespace-nowrap tabular-nums")}>
                {s.people} / {s.animals} / {s.objects}
              </td>
              <td className={td}>
                <SeverityBadge severity={s.classification} />
              </td>
              <td className={td}>{pct(s.confidence)}</td>
            </tr>
          ))}
        </Table>
      </Section>

      {frames.length > 0 && (
        <Section title="Evidence frames">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
            {frames.map((s) => (
              <figure key={s.id}>
                <img
                  src={s.frame ?? ""}
                  alt={`Evidence ${clock(s.startSec)}`}
                  loading="lazy"
                  className="w-full rounded-xl"
                />
                <figcaption className="mt-1 text-[0.8rem] tabular-nums text-muted-foreground">
                  {clock(s.startSec)}–{clock(s.endSec)} · {s.classificationLabel}
                </figcaption>
              </figure>
            ))}
          </div>
        </Section>
      )}
    </article>
  );
}

function ReportsPage() {
  const { video } = Route.useSearch();
  const navigate = useNavigate({ from: "/reports" });
  const { videos } = useVideoStore();
  const done = videos.filter((v) => v.status === "Completed");
  const current = done.find((v) => v.id === video) ?? done[0];
  const { data, error } = useAnalysis(current?.id, current?.status, current?.stats?.events);

  return (
    <PageShell title="Reports">
      <PageIntro eyebrow="Reports" title="Everything we found," accent="in one place.">
        One report per analysed video: counts, tracked entities, the full 10-second timeline,
        interactions, incidents and evidence frames.
      </PageIntro>

      {done.length === 0 ? (
        <p className="cv-card relative px-6 py-12 text-center text-muted-foreground">
          No completed analyses yet.{" "}
          <Link to="/analyse" className="font-semibold text-ink underline underline-offset-4">
            Upload a video
          </Link>{" "}
          to generate a report.
        </p>
      ) : (
        <div className="relative grid grid-cols-1 gap-6 xl:grid-cols-[17rem_1fr] [&>*]:min-w-0">
          <nav
            aria-label="Choose a report"
            className="flex flex-row flex-wrap gap-2 xl:flex-col xl:flex-nowrap"
          >
            {done.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => navigate({ search: { video: v.id }, replace: true })}
                aria-current={current?.id === v.id}
                className={cn(
                  "flex items-center gap-3 rounded-2xl p-2 pr-4 text-left",
                  current?.id === v.id
                    ? "bg-ink text-on-brand"
                    : "bg-card text-ink shadow-soft hover:bg-peche-soft",
                )}
              >
                <span className="h-11 w-16 shrink-0 overflow-hidden rounded-lg bg-muted">
                  {v.thumbnail && (
                    <img src={v.thumbnail} alt="" className="size-full object-cover" />
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{v.filename}</span>
                  <span className="flex items-center gap-1 text-[0.75rem] opacity-80">
                    <FileText className="size-3" /> {v.stats?.events ?? 0} events
                  </span>
                </span>
              </button>
            ))}
          </nav>
          {error ? (
            <p className="cv-card px-6 py-8 text-ink">Could not load the report: {error}</p>
          ) : data ? (
            <Report a={data} />
          ) : (
            <p className="cv-card px-6 py-12 text-center text-muted-foreground">Loading report…</p>
          )}
        </div>
      )}
    </PageShell>
  );
}
