# Connected mode — runtime evidence for audit candidates

Static analysis of an export cannot see callers outside the app: a backend workflow exposed as an
endpoint that a partner system calls, a webhook a payment provider hits, a page opened only by
direct link, an API Connector call that does run. Bubble's server logs can — within the plan's log
retention.

## Run

```bash
python3 <unbubble>/skills/connect/scripts/runtime_evidence.py \
    ~/UnBubble-Projects/<app>/audit/<app>-vN_audit.json --profile <app> [--days 14] \
    [--app-version live] [--max-candidates 40] [--out …]
```

- Input: the audit round's `--json` summary (`summary_version` 2).
- Candidates: unused pages and pages referenced only by URL; unused backend workflows (hard and
  transitive) and endpoints flagged "verify: webhook"; unused API Connector calls; uncalled backend
  custom events.
- Logs of `live` by default (reading is safe; that is where the real traffic is).
- One paginated pull of the whole window, matched locally per candidate by whole identifier (`home`
  does not count rows about `homepage`) — method `window`.
- When that pull stops early (page limit, row cap, an incomplete pagination) its hits still count,
  but its zeros prove nothing: those candidates are asked again one by one with a server-side
  `contains` query — method `window (partial) + per-candidate`.
- When Bubble returns an empty window (busy apps need a search term) or the pull fails, every
  candidate gets its own `contains` query — method `per-candidate`.
- Per-candidate queries are capped by `--max-candidates`; the rest are marked `skipped`. A query that
  fails or stops early with zero rows gives `unknown`, never `not seen`. When every query failed
  (typically an expired session) the script exits 1 — ask the user to sign in again.
- Output: `<proj>/audit/runtime-evidence__<app>-vN.json` (0600) with, per candidate, `hits`,
  `first_seen`, `last_seen` — **counts only, never log rows** — plus the window, the method used and
  the pull's truncation info. The script prints only a summary: `seen`, `not_seen`, `unknown`.

## Reading the result

- **Seen** → the candidate is alive: take it off the deletion list and tell the owner who seems to
  call it (an external system, a scheduled job, direct links). For a page "seen" means it was
  served; for a backend workflow, that it ran.
- **Not seen** → not seen *in this window*, nothing more. Say the window and the plan's retention;
  monthly jobs, yearly renewals and seasonal flows can sit outside it. It strengthens a static
  "unused" verdict; it never proves death on its own.
- **Unknown** (skipped or the query failed) → no evidence either way.
- A truncated pull (`source.truncated`) means the window had more rows than were read: shorten the
  window or rely on the per-candidate fallback for the important candidates.

Relay the counts in the conversation (e.g. "the `stripe_webhook` endpoint ran 1,284 times in 14
days, last at 09:12 today"), never the rows. When `unbubble:audit` is re-run on the same round, the
evidence file can be cited next to each candidate; in `unbubble:clone` (step 3b) the same evidence
answers "does this endpoint have external consumers?" and "is the integration behind this flag
alive?".
