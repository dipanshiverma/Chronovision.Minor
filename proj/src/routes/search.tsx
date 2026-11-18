import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { MessageSquareText, Play, Search, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { z } from "zod";

import { SeverityBadge } from "@/components/chrono/badges";
import { PageIntro, PageShell } from "@/components/chrono/page-shell";
import {
  clock,
  pct,
  searchVideos,
  useVideoStore,
  type SearchResponse,
  type SearchResult,
} from "@/lib/video-store";

const searchSchema = z.object({ q: z.string().optional() });

export const Route = createFileRoute("/search")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Video Search — ChronoVision" },
      {
        name: "description",
        content: "Ask questions about your footage and get timestamps with visual evidence.",
      },
      { property: "og:title", content: "Video Search — ChronoVision" },
      {
        property: "og:description",
        content: "Ask questions about your footage and get timestamps with visual evidence.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: SearchPage,
});

const EXAMPLES = [
  "Show all suspicious activities",
  "How many people appeared?",
  "Were any animals detected?",
  "When was a bag picked up?",
  "Which person stayed the longest?",
  "What happened between 00:20 and 00:40?",
];

const TYPE_LABEL: Record<SearchResult["type"], string> = {
  event: "Event",
  entity: "Tracked entity",
  segment: "10-second segment",
};

function ResultRow({ r }: { r: SearchResult }) {
  return (
    <li className="flex items-center gap-4 rounded-2xl bg-secondary/60 p-3">
      <div className="h-[4.6rem] w-28 shrink-0 overflow-hidden rounded-xl bg-muted">
        {r.thumbnail && (
          <img
            src={r.thumbnail}
            alt={`Evidence for ${r.title}`}
            loading="lazy"
            className="size-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {r.severity ? (
            <SeverityBadge severity={r.severity} />
          ) : (
            <span className="rounded-full bg-card px-3 py-1 text-[0.82rem] font-semibold text-ink">
              {TYPE_LABEL[r.type]}
            </span>
          )}
          <span className="truncate font-semibold text-ink">{r.title}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-[0.9rem] leading-snug text-ink/80">{r.text}</p>
        <p className="mt-0.5 truncate text-[0.8rem] text-muted-foreground">
          {r.filename} · {clock(r.startSec)}
          {r.endSec != null && r.endSec > r.startSec ? ` – ${clock(r.endSec)}` : ""}
          {r.confidence != null ? ` · confidence ${pct(r.confidence)}` : ""}
          {r.entities.length ? ` · ${r.entities.map((e) => e.name).join(", ")}` : ""}
        </p>
      </div>
      <Link
        to="/timeline"
        search={{ video: r.videoId, t: r.startSec }}
        aria-label={`Play ${r.title} at ${clock(r.startSec)}`}
        className="grid size-12 shrink-0 place-items-center rounded-full bg-nectarine-soft text-ink transition-transform hover:scale-105"
      >
        <Play className="size-4 fill-current" />
      </Link>
    </li>
  );
}

function SearchPage() {
  const { q = "" } = Route.useSearch();
  const navigate = useNavigate({ from: "/search" });
  const { online, videos } = useVideoStore(); // a finished analysis changes the answers, so re-run on change
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const analysedKey = videos.map((v) => `${v.id}:${v.status}`).join(",");

  useEffect(() => {
    if (online === false) return;
    const t = setTimeout(() => {
      searchVideos(q.trim())
        .then((r) => {
          setRes(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message));
    }, 300);
    return () => clearTimeout(t);
  }, [q, online, analysedKey]);

  const results = res?.results ?? [];

  return (
    <PageShell title="Video Search">
      <PageIntro eyebrow="Search" title="Ask your footage" accent="anything.">
        Ask in plain language. Answers come only from what ChronoVision actually detected, each with
        a timestamp and evidence frame. If the analysis doesn’t support something, it says so.
      </PageIntro>

      <div className="relative mb-4 max-w-3xl">
        <Search className="absolute left-5 top-1/2 size-5 -translate-y-1/2 text-ink" />
        <input
          value={q}
          onChange={(e) => navigate({ search: { q: e.target.value || undefined }, replace: true })}
          placeholder="Try “When did someone steal the handbag?”"
          aria-label="Search analysed videos"
          className="h-14 w-full rounded-2xl bg-card pl-14 pr-4 text-base text-ink shadow-soft outline-none ring-ring/40 focus:ring-2"
        />
      </div>

      {!q && (
        <div className="relative mb-6 flex max-w-4xl flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => navigate({ search: { q: ex }, replace: true })}
              className="rounded-full bg-secondary px-4 py-2 text-sm font-medium text-ink hover:bg-peche-soft"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <section className="cv-card relative max-w-4xl p-6" aria-live="polite">
        {error ? (
          <p className="text-ink">Search failed: {error}</p>
        ) : online === false ? (
          <p className="text-ink">Backend offline.</p>
        ) : !res ? (
          <p className="text-muted-foreground">Searching…</p>
        ) : (
          <>
            {res.interpretation.length > 0 && (
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <span className="flex items-center gap-1.5 font-medium text-muted-foreground">
                  <Sparkles className="size-4" /> Understood as
                </span>
                {res.interpretation.map((c) => (
                  <span
                    key={c}
                    className="rounded-full bg-menthe-soft px-3 py-1 font-medium text-ink"
                  >
                    {c}
                  </span>
                ))}
                <span className="text-xs text-muted-foreground">
                  ({res.source === "llm" ? "AI-assisted parsing" : "rule-based parsing"})
                </span>
              </div>
            )}
            <div className="mb-4 flex items-start gap-3 rounded-2xl bg-peche-soft px-4 py-3 text-ink">
              <MessageSquareText className="mt-0.5 size-5 shrink-0" />
              <p className="text-[1rem] leading-snug">{res.answer}</p>
            </div>
            {results.length > 0 && (
              <ul className="flex flex-col gap-3">
                {results.map((r, i) => (
                  <ResultRow key={`${r.type}-${r.videoId}-${r.startSec}-${i}`} r={r} />
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </PageShell>
  );
}
