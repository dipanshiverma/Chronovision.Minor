import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils";
import { SEVERITY_LABEL, type AnalysisStatus, type Severity } from "@/lib/video-store";

const statusVariants = cva(
  "inline-flex items-center whitespace-nowrap rounded-full px-3 py-1 text-[0.82rem] font-semibold text-ink",
  {
    variants: {
      status: {
        Completed: "bg-menthe",
        Processing: "bg-peche",
        Queued: "bg-secondary",
        Failed: "bg-nectarine-soft",
      },
    },
  },
);

export function StatusBadge({
  status,
  progress,
  title,
}: {
  status: AnalysisStatus;
  progress?: number;
  title?: string;
}) {
  const pct = status === "Processing" && progress ? ` ${Math.round(progress * 100)}%` : "";
  return (
    <span className={statusVariants({ status })} title={title}>
      {status}
      {pct}
    </span>
  );
}

const severityStyle: Record<Severity, string> = {
  normal: "bg-menthe-soft text-ink",
  unusual: "bg-peche text-ink",
  suspicious: "bg-nectarine-soft text-ink",
  high: "bg-nectarine text-on-brand",
};

/** Dot colour for timelines and charts (matches the badge). */
export const severityDot: Record<Severity, string> = {
  normal: "bg-menthe",
  unusual: "bg-peche",
  suspicious: "bg-nectarine-soft ring-2 ring-nectarine",
  high: "bg-nectarine",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-3 py-1 text-[0.82rem] font-semibold",
        severityStyle[severity],
        className,
      )}
    >
      {SEVERITY_LABEL[severity]}
    </span>
  );
}
