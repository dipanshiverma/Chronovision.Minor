import { Link } from "@tanstack/react-router";
import { Play, Sparkles } from "lucide-react";

import { SeverityBadge } from "@/components/chrono/badges";
import { cn } from "@/lib/utils";
import { clock, pct, type EventItem } from "@/lib/video-store";

/** One detected event: evidence frame (real boxes are drawn onto it by the backend), description, play link. */
export function EventRow({ event, className }: { event: EventItem; className?: string }) {
  return (
    <li className={cn("flex items-center gap-4 rounded-2xl p-2", className)}>
      <div className="relative h-[4.1rem] w-24 shrink-0 overflow-hidden rounded-xl bg-muted">
        {event.frame && (
          <img
            src={event.frame}
            alt={`Evidence for ${event.title}`}
            loading="lazy"
            className="size-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <SeverityBadge severity={event.severity} />
        <p className="mt-1 truncate font-semibold text-ink">{event.title}</p>
        <p className="line-clamp-2 text-[0.85rem] leading-snug text-ink/75">{event.description}</p>
        <p className="mt-0.5 truncate text-[0.8rem] text-muted-foreground">
          {clock(event.startSec)}
          {event.filename ? ` · ${event.filename}` : ""} · confidence {pct(event.confidence)}
        </p>
      </div>
      <Link
        to="/timeline"
        search={{ video: event.videoId, t: event.startSec }}
        aria-label={`Play ${event.title}`}
        className="grid size-11 shrink-0 place-items-center rounded-full bg-nectarine-soft text-ink transition-transform hover:scale-105"
      >
        <Play className="size-4 fill-current" />
      </Link>
    </li>
  );
}

export function RecentEvents({
  events,
  limit,
  className,
}: {
  events: EventItem[];
  limit?: number;
  className?: string;
}) {
  const rows = limit ? events.slice(0, limit) : events;
  return (
    <section className={cn("cv-card px-5 py-5", className)}>
      <div className="mb-3 flex items-center gap-3">
        <Sparkles className="size-8 text-nectarine" strokeWidth={1.8} />
        <h2 className="text-[1.4rem] font-bold text-ink">Recent Events</h2>
      </div>
      {rows.length ? (
        <ul className="flex flex-col gap-2">
          {rows.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </ul>
      ) : (
        <p className="py-8 text-center text-muted-foreground">
          No events yet. Events appear once a video has been analysed.
        </p>
      )}
    </section>
  );
}
