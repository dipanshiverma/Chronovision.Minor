import { Link } from "@tanstack/react-router";
import { ArrowRight, Film, Layers, MoreHorizontal, Play, Trash2 } from "lucide-react";

import { StatusBadge } from "@/components/chrono/badges";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { formatDate, reanalyse, removeVideo, type VideoAnalysis } from "@/lib/video-store";

const num = (n: number | undefined) => (n === undefined ? "—" : n);

export function RecentAnalyses({
  videos,
  limit,
  className,
  showAllLink = true,
}: {
  videos: VideoAnalysis[];
  limit?: number;
  className?: string;
  showAllLink?: boolean;
}) {
  const rows = limit ? videos.slice(0, limit) : videos;
  const th = "px-2 py-2.5 font-medium";

  return (
    <section className={cn("cv-card px-5 py-5", className)}>
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Layers className="size-8 text-lagune" strokeWidth={1.8} />
          <h2 className="whitespace-nowrap text-[1.4rem] font-bold text-ink">
            Recent Video Analyses
          </h2>
        </div>
        {showAllLink && (
          <Link
            to="/analyse"
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-ink hover:bg-secondary"
          >
            View All <ArrowRight className="size-4" />
          </Link>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full whitespace-nowrap text-left text-[0.88rem]">
          <thead>
            <tr className="bg-menthe-soft text-sm font-medium text-ink">
              <th className={cn(th, "rounded-l-xl")}>Video</th>
              <th className={th}>Filename</th>
              <th className={th}>Uploaded</th>
              <th className={th}>Duration</th>
              <th className={th}>Status</th>
              <th className={th}>People</th>
              <th className={th}>Animals</th>
              <th className={th}>Objects</th>
              <th className={th}>Events</th>
              <th className="rounded-r-xl px-2 py-2.5">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.id} className="border-b border-border last:border-b-0">
                <td className="px-0 py-2 pr-2">
                  <Link
                    to="/timeline"
                    search={{ video: v.id }}
                    className="group relative block h-[3.1rem] w-[4.8rem] overflow-hidden rounded-lg bg-muted"
                    aria-label={`Open ${v.filename}`}
                  >
                    {v.thumbnail ? (
                      <img
                        src={v.thumbnail}
                        alt=""
                        loading="lazy"
                        className="size-full object-cover"
                      />
                    ) : (
                      <Film className="m-auto mt-4 size-6 text-muted-foreground" />
                    )}
                    <span className="absolute inset-0 grid place-items-center">
                      <span className="grid size-8 place-items-center rounded-full border-2 border-on-brand bg-ink/40 text-on-brand transition-transform group-hover:scale-110">
                        <Play className="size-3.5 fill-current" />
                      </span>
                    </span>
                  </Link>
                </td>
                <td
                  className="max-w-[16rem] truncate px-2 font-semibold text-ink"
                  title={v.filename}
                >
                  {v.filename}
                </td>
                <td className="px-2 text-ink">{formatDate(v.uploadedAt)}</td>
                <td className="px-2 font-medium text-ink">{v.duration ?? "—"}</td>
                <td className="px-2">
                  <StatusBadge
                    status={v.status}
                    progress={v.progress}
                    {...(v.error ? { title: v.error } : {})}
                  />
                </td>
                <td className="px-2 font-semibold text-ink">{num(v.stats?.people)}</td>
                <td className="px-2 font-semibold text-ink">{num(v.stats?.animals)}</td>
                <td className="px-2 font-semibold text-ink">{num(v.stats?.objects)}</td>
                <td className="px-2 font-semibold text-ink">{num(v.stats?.events)}</td>
                <td className="px-2 text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      className="grid size-8 place-items-center rounded-full text-ink hover:bg-secondary"
                      aria-label={`Actions for ${v.filename}`}
                    >
                      <MoreHorizontal className="size-5" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem asChild>
                        <Link to="/timeline" search={{ video: v.id }}>
                          View timeline
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to="/reports" search={{ video: v.id }}>
                          View report
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => void reanalyse(v.id)}
                        disabled={v.status === "Processing"}
                      >
                        Re-analyse
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => void removeVideo(v.id)}
                        className="text-destructive"
                      >
                        <Trash2 className="size-4" /> Remove
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={10} className="py-10 text-center text-muted-foreground">
                  No videos yet. Upload one to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
