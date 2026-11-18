import { AlertTriangle } from "lucide-react";

import { API_BASE } from "@/lib/api";
import { useVideoStore } from "@/lib/video-store";

/** Shown only when the FastAPI backend cannot be reached. Also mounts the store, which starts data polling. */
export function BackendBanner() {
  const { online } = useVideoStore();
  if (online !== false) return null;
  return (
    <div
      role="alert"
      className="mx-8 mt-4 flex items-start gap-3 rounded-2xl bg-nectarine-soft px-5 py-3 text-ink"
    >
      <AlertTriangle className="mt-0.5 size-5 shrink-0" />
      <div className="text-sm">
        <p className="font-semibold">Can’t reach the ChronoVision backend ({API_BASE}).</p>
        <p className="mt-0.5">
          Start it in another terminal:{" "}
          <code className="rounded bg-card px-1.5 py-0.5">
            cd backend &amp;&amp; python -m uvicorn app.main:app --port 8000
          </code>
        </p>
      </div>
    </div>
  );
}
