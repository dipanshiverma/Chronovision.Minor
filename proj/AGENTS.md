<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.
<!-- LOVABLE:END -->

## Project rules

- App shell (fixed brand sidebar + routed pages) lives in `src/routes/__root.tsx`; each sidebar item is its own route file so navigation stays real URLs.
- Videos and events flow through `src/lib/video-store.ts`, which now talks to the FastAPI backend in `backend/` via `src/lib/api.ts`. Pages read it via `useVideoStore()`.
- Never fabricate results: counts, events, timestamps and evidence frames all come from the backend. A video with nothing drawn/detected shows 0 events, not sample data.
- Evidence frames already contain the real bounding box, zone and timestamp (drawn by the backend) - do not overlay fake boxes in the UI.
- Analysis is fully automatic (no settings page, no zone editor). Optional zone/line rules are API-only; coordinates are normalised 0-1.
- Backend: `backend/` (FastAPI + YOLO + ByteTrack + SQLite). Tests: `cd backend && pytest`; frontend: `npm test`.
