# UnBubble console (ui/)

A local web console for the UnBubble pipeline. It reads `~/UnBubble-Projects/<app-id>/` and
shows, per project, how far the three stages are:

| Stage | Derived from |
|---|---|
| **Audit** | `audit/<app>-vN_audit.json` (findings per category per round) + the HTML reports (embedded) + `audit/bubble_cleanup_progress__<app>.json` (deletions, per-section sign-offs and items kept on purpose — auto-saved by the embedded report through `PUT /api/projects/<app>/audit-progress`) + `audit/cleanup-applied__<app>.json` (deletions applied through the connected mode; the entries that count — applied to `test` or on a merged branch — are merged into the tracker by `GET …/audit-progress` and kept out of the progress file on `PUT`) |
| **Clone · docs** | `inventory/summary.json`, `secrets/ENV-KEYS.md` (+ `.env` existence only), `docs/00…08-*.md`, `PRD-clone.md`, `PARITY-MATRIX.md` (rows with/without disposition), `08-open-questions.md` (blocking / decisions) |
| **Level-up · docs** | the nine files of `levelup/` + `spec-coverage.json` (gate) + `parity-report.json` |
| **Level-up · implementation** | stories parsed from `levelup/BACKLOG.md` (same rules as `spec_coverage.py`) ticked off in the UI |

It also detects **where the skills are installed** (Claude Code, Codex/ChatGPT, `~/.agents`,
Cursor, Gemini, Copilot, OpenCode, Windsurf) — the three core skills plus the optional `connect` —,
whether each copy is in sync with this repo, and walks a new user through a 4-step onboarding
(`/setup`).

**Connected mode** (optional, `mcp/` + `unbubble:connect`): `/setup` shows its installation from
`python3 ../mcp/launch.py doctor --json` — vendored commit, checks, hosts where the MCP server is
registered, Bubble profiles with whether each has a session and when it was saved, test-user roles,
downloaded exports. A project page shows a "connected" badge when a profile is bound to the app,
with the provenance of its newest downloaded export. Session files are never read — only whether
they exist and their date.

## Run

```bash
cd ui
npm install
npm run dev        # http://localhost:3333
```

`npm run build && npm start` for a production build. Node 20+.

Optional env vars (see `.env.example`): `UNBUBBLE_PROJECTS_DIR` (default `~/UnBubble-Projects`),
`UNBUBBLE_REPO_DIR` (default: the parent of `ui/`), `UNBUBBLE_MCP_HOME` (the connected mode's state
folder, default `~/.unbubble/mcp` — the same variable `mcp/launch.py` reads).

## Storage model — files are the source of truth

There is **no database**. Everything the console shows is derived, on every request, from the
files the skills already write. The only file the console writes is
**`<project>/unbubble.json`** (manual stage overrides + notes, ticked backlog stories, links,
display name). It is plain JSON, safe to commit, and safe to delete (the derived status comes
back).

```json
{
  "version": 1,
  "name": "My App",
  "stages": { "audit": { "status": "done", "note": "re-exported lean on 2026-07-15" } },
  "stories_done": ["H1-1", "H1-2"],
  "links": { "rebuild_repo": "~/Code/my-app-v2", "github": "https://github.com/…" }
}
```

The live secrets file (`secrets/.env`) is never read nor served; `ENV-KEYS.md` and
`.env.example` (names only) are.

## Layout

```
src/lib/scan/      audit.ts · clone.ts · levelup.ts · backlog.ts · project.ts · journal.ts  (derivation)
src/lib/install.ts skill-install detection across agent hosts
src/lib/connect.ts connected mode: launch.py doctor for /setup, profile + export provenance per project
src/lib/state.ts   unbubble.json read/patch
src/app/api/       projects, projects/[id], …/docs, …/file, …/state, setup
src/components/    ui/ (shadcn base-nova, same kit as BubbleDocs), layout/, project/, docs/, setup/
```

UI kit, sidebar, breadcrumb, doc viewer with table of contents and the Mermaid renderer were
reused from BubbleDocs; Markdown is rendered with `react-markdown` (the skills emit plain
Markdown, not MDX).

## Preferences

Theme and language are per-viewer preferences stored in the browser's localStorage and restored
when the console is reopened: `unbubble.theme` (`light` / `dark`, managed by next-themes, applied
before the first paint) and `unbubble.locale` (a registered locale code). The locale is also
mirrored in the `unbubble_locale` cookie so the server renders the right language on the first
paint; when the two disagree (for example after clearing cookies), localStorage wins and the
cookie is rewritten.

## Adding a language

The console ships in English, Português (Brasil) and Español. Translations live in
`src/lib/i18n/locales/`, one file per language, registered in `src/lib/i18n/index.ts`; English is
the reference dictionary and anything a locale leaves out falls back to it. The step-by-step
recipe, written so an LLM can follow it, is the **Languages** chapter of the
[root README](../README.md#languages): copy `locales/en.ts`, translate the values (keep keys,
placeholders and product terms), append one entry to `LOCALES`, run `tsc` + `eslint`, check the
menu.

## Logo animation

`public/brand/unbubble.gif` (and the static `unbubble.png` + `src/app/icon.png` favicon) are rendered
by `scripts/make-logo.py`: a soap bubble grows, pops and frees the cube that was inside it. Regenerate
with `python3 scripts/make-logo.py --sheet` (needs Pillow; `--sheet` also writes a contact sheet of
key frames for review).

## Known build notice

`next build` prints a Turbopack warning ("Encountered unexpected file in NFT list … src/lib/install.ts").
It comes from the install detector walking home-directory paths at runtime; it only affects
`output: 'standalone'` file tracing, which this app does not use. Safe to ignore.
