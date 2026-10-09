# Connected mode — screens per role and minimum parity

Captures what each screen of the Bubble app shows and offers, per user role — public pages and
pages behind the login — and later checks that the rebuilt app offers at least the same content and
actions. Each capture is a structured DOM snapshot (texts, headings, buttons and links, fields with
placeholders, images with alt text, boxes) plus a full-page screenshot.

**What the captures are for — and what not:**

- They are the **content inventory** of each screen and role: the information shown, the fields,
  the actions, the navigation, empty states. `unbubble:clone` can link them from its pages doc;
  `unbubble:level-up` turns them into the per-screen content inventory of FRONTEND-DESIGN.md.
- They are **never a style reference.** The rebuild follows a new, stronger design system and is
  expected to look different — and better. Layout, typography, colors and spacing of the Bubble app
  are not targets; the brand tokens extracted from the export are an input, not a ceiling.
- The MCP's geometric tools (`bubble_visual_compare`, and `bubble_visual_audit`, whose repair plans
  target Bubble) are not part of this flow; repair plans are never applied.

## Before capturing (the owner does this)

0. **A password-protected test version** (Bubble: Settings → General → password-protect the
   development version) answers HTTP 401 and renders nothing. The owner saves its username and
   password once, in a terminal — they are asked there, the password without echo, and never pass
   through the agent:

   ```bash
   python3 <unbubble>/mcp/launch.py cli eval save-http-auth --app-id <app-id> --app-version test
   ```

   They are kept owner-only next to the role sessions and sent only to the app's own origin; every
   capture of that app — anonymous or logged in — and `capture-app-session` use them. A capture that
   still gets a 401 is recorded as failed with this command in its error.
1. **Test users, one per role**, created in `version-test` (or the branch) — never a real user's
   account. Roles as the app defines them (e.g. `admin`, `agent`, `customer`).
2. **Test data that can be seen**: the screenshots show whatever the test database holds, so it
   should be fictitious or anonymized. If `test` holds a copy of live data, stop and tell the owner.
3. **Sign in once per role, in a terminal** — the command waits for Enter, so the human runs it (the
   agent may open it in the user's terminal panel, never types the credentials):

   ```bash
   python3 <unbubble>/mcp/launch.py cli eval capture-app-session --app <app-id> --app-id <app-id> \
       --app-version test --page <login page> --role admin
   ```

   A visible Chromium opens on the login page; the owner signs in as the test user of that role, then
   presses Enter in the terminal. Only the app's own cookies and storage are kept, in the MCP config
   folder (0600). Refused on live.

Opening a page runs its page-load workflows as that user: captures can write to the test database,
which is why they run on `version-test` or a branch only.

## Capture the Bubble app

```bash
python3 <unbubble>/skills/connect/scripts/capture_screens.py --app <app-id> --roles anon,admin,agent \
    [--version test] [--pages home,dashboard] [--params params.json] [--limit 40] [--max-nodes 800]
```

- Pages come from the clone inventory (`<proj>/inventory/pages.json`, `unbubble:clone` step 1); by
  default the busiest 40 (most workflows and elements first).
- `anon` = not signed in. Every other role uses its captured session.
- Pages with a content type need an example thing in the URL: `--params` with
  `{"<page>": {"path": "<unique id or slug from the TEST database>", "query": {"tab": "x"}}}`. Pages
  without one are skipped and listed.
- Output: `<proj>/visual/bubble/<role>/<page>.json|png` and `visual/INDEX-bubble.json|md`: per page
  and role, access (`ok` / **no access in this role** — the page redirected), node count, the
  `--max-nodes` used, screenshot. Each run **merges** into the index (re-capturing a few pages keeps
  the others) and deletes the files of a capture that failed or left the test version, so a stale
  file never passes for a fresh one.
- A capture with as many nodes as its `--max-nodes` was cut short: raise it for dense screens.

Only the initial state of each screen is captured: popups, tabs and groups that need a click to
appear are not. SSO-only apps need a test account at the identity provider. A page whose final URL
lost its `/version-…` segment (a redirect to the live app) is marked **left the test version**: tell
the owner which page redirects there and do not use that capture — its page-load workflows ran on
the live app.

## Capture the rebuilt app

Sessions for the new app's test users, then the same screens through a route map:

```bash
python3 <unbubble>/mcp/launch.py cli eval capture-app-session --target rebuild --app rebuild-<app-id> \
    --url http://localhost:3000/login --role admin
python3 <unbubble>/skills/connect/scripts/capture_screens.py --app <app-id> --target rebuild \
    --base-url http://localhost:3000 --route-map routes.json --roles anon,admin,agent
```

`routes.json` maps each Bubble page to its route in the new app: `{"dashboard": "/app", "order":
"/orders/<seed id>"}` — use seeded test data. Output: `<proj>/visual/rebuild/…` and
`INDEX-rebuild.md`. Capture with a `--max-nodes` at least as high as the Bubble side.

## Minimum parity

```bash
python3 <unbubble>/skills/connect/scripts/screen_parity.py --app <app-id> \
    [--roles admin,agent] [--pages dashboard,orders] [--strict]
```

It walks the screens listed in `INDEX-bubble.json` (or the `--roles`/`--pages` asked for) and, for
each screen and role, lists what the Bubble screen offers that the new one does not: headings,
labels and short texts, buttons and links, fields (by placeholder), images (by alt text). Compared
case-, accent- and punctuation-insensitively, and across kinds — a text that became a button or a
placeholder that became a label counts as present. Numbers, money, dates, emails and URLs are data,
not UI. Inside a Bubble repeating group only what repeats across rows counts (a per-row "Edit"
button); one-off texts there are database content and are listed apart, without verdicts.

Writes `<proj>/levelup/screen-parity.md|json`. **Every missing item needs an owner verdict** in
`<proj>/levelup/screen-parity-verdicts.json`:

```json
{"admin/dashboard": {
   "text:email": {"verdict": "renamed", "note": "now 'E-mail'", "date": "2026-10-08"},
   "action:export csv": {"verdict": "missing", "note": "story EXP-3", "date": "2026-10-08"}},
 "admin/reports": {"screen": {"verdict": "moved", "note": "merged into /dashboard", "date": "2026-10-08"}},
 "agent/settings": {"access": {"verdict": "dropped", "note": "agents no longer edit settings", "date": "2026-10-08"}}}
```

- `renamed` / `moved` — present under another form or place;
- `dropped` — cut by a dated owner decision;
- `missing` — a real gap: it becomes a backlog story and keeps the gate open.

A whole screen takes the key `screen`; a role that cannot open the rebuilt screen takes `access`.
A screen that cannot be compared — skipped (no `--params`, not in the inventory), failed, left the
test version, missing from the rebuild index — stays **unresolved** until it is captured properly or
the owner gives it a `screen` verdict. `--strict` exits 1 while anything is unresolved, still
`missing`, or comes from a truncated capture. Visual differences never count.

**When to run it:** whenever a module is reported done (its P0 screens, every role), and before the
cutover as part of the execution contract's final gate — the same discipline as level-up's
`parity_check.py` for data.

## End of the project

The captured sessions open the app as those users: ask the owner to delete
`<config>/app-sessions/<app-id>/` and `<config>/app-sessions/rebuild-<app-id>/`
(`launch.py paths` shows `<config>`), and to remove or disable the test users if they are no longer
needed.
