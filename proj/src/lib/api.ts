/** Thin client for the ChronoVision FastAPI backend (see /backend). */
const BASE = ((import.meta.env["VITE_API_BASE"] as string | undefined) ?? "").replace(/\/$/, "");

export const API_BASE = BASE || "(same origin, proxied to :8000)";

/** Backend paths like /api/videos/x/file become absolute when VITE_API_BASE is set. */
export const apiUrl = (path: string | null | undefined): string | null =>
  path ? BASE + path : null;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError("Cannot reach the ChronoVision backend", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
