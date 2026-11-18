import { createFileRoute, Link } from "@tanstack/react-router";
import { Play, Search, Upload } from "lucide-react";

import heroCctv from "@/assets/hero-cctv.jpg";
import { ActivityChart } from "@/components/chrono/activity-chart";
import { PageShell } from "@/components/chrono/page-shell";
import { RecentAnalyses } from "@/components/chrono/recent-analyses";
import { RecentEvents } from "@/components/chrono/recent-events";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useVideoStore } from "@/lib/video-store";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Overview — ChronoVision" },
      {
        name: "description",
        content:
          "Your video surveillance workspace: recent analyses, detected events and quick actions.",
      },
      { property: "og:title", content: "Overview — ChronoVision" },
      {
        property: "og:description",
        content:
          "Your video surveillance workspace: recent analyses, detected events and quick actions.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Overview,
});

function FocusBrackets() {
  const corner = "absolute size-7 border-on-brand";
  return (
    <div className="absolute left-[64%] top-[9%] h-[42%] w-[21%]" aria-hidden="true">
      <span className={`${corner} left-0 top-0 border-l-2 border-t-2`} />
      <span className={`${corner} right-0 top-0 border-r-2 border-t-2`} />
      <span className={`${corner} bottom-0 left-0 border-b-2 border-l-2`} />
      <span className={`${corner} bottom-0 right-0 border-b-2 border-r-2`} />
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number | string;
  tone: string;
  hint?: string;
}) {
  return (
    <div className="cv-card flex flex-col gap-1 px-5 py-4">
      <span className={cn("h-1.5 w-8 rounded-full", tone)} aria-hidden="true" />
      <span className="mt-2 text-[2.1rem] font-bold leading-none tabular-nums text-ink">
        {value}
      </span>
      <span className="text-[0.92rem] font-medium text-ink">{label}</span>
      {hint && <span className="text-[0.78rem] text-muted-foreground">{hint}</span>}
    </div>
  );
}

function Overview() {
  const { videos, events, overview: o } = useVideoStore();

  return (
    <PageShell title="Overview">
      {/* decorative shapes */}
      <div className="blob -right-28 top-[24rem] size-72 bg-peche opacity-90" aria-hidden="true" />

      <section className="relative grid grid-cols-1 items-center gap-6 pt-1 pb-7 xl:grid-cols-[1.2fr_1fr]">
        <div className="min-w-0">
          <p className="eyebrow mb-3 text-ink">Video Surveillance</p>
          <h1 className="font-display-italic text-[clamp(2.2rem,3.7vw,4rem)] font-semibold leading-[1.04] tracking-tight text-ink">
            Your video
            <br />
            surveillance <span className="text-nectarine">workspace.</span>
          </h1>
          <p className="mt-4 max-w-xl text-[1.2rem] leading-snug text-ink/85">
            Review footage, track activity and find important events without watching every frame.
          </p>

          <div className="mt-7 flex flex-wrap gap-3.5">
            <Button asChild variant="peche" size="action">
              <Link to="/analyse">
                <Upload /> Upload Video
              </Link>
            </Button>
            <Button asChild variant="menthe" size="action">
              <Link to="/timeline">
                <Play className="fill-current" /> View Analyses
              </Link>
            </Button>
            <Button asChild variant="lagune" size="action">
              <Link to="/search">
                <Search /> Search Events
              </Link>
            </Button>
          </div>
        </div>

        <div className="relative hidden xl:block">
          <div className="blob -left-10 -top-10 size-64 bg-peche-soft" aria-hidden="true" />
          <div className="relative overflow-hidden rounded-[2rem] shadow-card">
            <img
              src={heroCctv}
              alt="Security camera mounted on a warm terracotta wall"
              width={1600}
              height={720}
              className="aspect-[16/7.2] w-full object-cover"
            />
            <FocusBrackets />
          </div>
        </div>
      </section>

      <section
        aria-label="Statistics"
        className="relative mb-6 grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-7"
      >
        <Stat label="Videos uploaded" value={o?.videos ?? 0} tone="bg-lagune" />
        <Stat label="Videos analysed" value={o?.analysed ?? 0} tone="bg-menthe" />
        <Stat label="Unique people" value={o?.people ?? 0} tone="bg-nectarine" />
        <Stat label="Unique animals" value={o?.animals ?? 0} tone="bg-menthe" />
        <Stat label="Unique objects" value={o?.objects ?? 0} tone="bg-peche" />
        <Stat label="Events detected" value={o?.events ?? 0} tone="bg-lagune" />
        <Stat
          label="Potentially suspicious"
          value={o?.incidents ?? 0}
          tone="bg-nectarine"
          hint="suspicious or high priority"
        />
      </section>

      <section className="relative grid grid-cols-1 gap-6 xl:grid-cols-2 [&>*]:min-w-0">
        <RecentAnalyses videos={videos} limit={4} className="xl:col-span-2" />
        <RecentEvents events={events} limit={4} />
        <ActivityChart overview={o} />
      </section>
    </PageShell>
  );
}
