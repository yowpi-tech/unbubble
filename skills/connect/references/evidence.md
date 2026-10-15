# Connected mode — runtime evidence for audit candidates

Static analysis of an export cannot see callers outside the app: a backend workflow exposed as an
endpoint that a partner system calls, a webhook a payment provider hits, a page opened only by
direct link, an API Connector call that does run. Two read-only sources of the live app can, each
with its own blind spot:

| Source | Counts | Good for | Blind spot |
|---|---|---|---|
| `--source workload` | runs per workflow in the editor's workload metrics; every version; about 31 days | backend workflows (scheduled, Workflow API calls, database triggers, recurring) and custom events, through the workflows that trigger them | pages and API Connector calls are not metered |
| `--source logs` (default) | server-log rows that name the candidate; one version; the plan's log retention | pages (served), API Connector calls, workflows | some large apps answer every query "ok, 0 rows" |

**Prefer workload for workflows.** Use the logs for pages and API Connector calls, and trust their
zeros only after the positive control passed.

## Run

```bash
# workflows: run counts, joined to the export the round ran on
python3 <unbubble>/skills/connect/scripts/runtime_evidence.py \
    ~/UnBubble-Projects/<app>/audit/<app>-vN_audit.json --profile <app> \
    --source workload --export <the round's .bubble> [--days 30]

# pages and API calls: server logs behind a positive control
python3 <unbubble>/skills/connect/scripts/runtime_evidence.py \
    ~/UnBubble-Projects/<app>/audit/<app>-vN_audit.json --profile <app> \
    [--export <the round's .bubble>] [--days 14] [--app-version live] [--max-candidates 40] \
    [--control "<a workflow you know runs>"]
```

- Input: the audit round's `--json` summary (`summary_version` 2). Candidates: unused pages and
  pages referenced only by URL; unused backend workflows (hard and transitive) and endpoints flagged
  "verify: webhook"; unused API Connector calls; uncalled backend custom events.
- `--export`: the `.bubble` the round ran on. Workload needs it for the joins; the logs use it to
  name the positive control. An export downloaded with `fetch_export.py` is found through the audit's
  provenance (sha256); otherwise pass it.
- Output, both 0600 and the same shape — per candidate `hits`, `first_seen`, `last_seen`,
  `coverage` (and `reason` when unknown), **counts only, never log rows**:
  `<proj>/audit/runtime-evidence__<app>-vN.json` (logs) and `…-vN.workload.json` (workload). The
  script prints only a summary: `seen`, `not_seen`, `unknown`, the control.
- Exit codes: `0` usable; `1` every query failed (an expired session, most likely: ask the user to
  sign in again); `3` the source showed nothing for something known to run, so every zero became
  unknown — **do not pass that file to `bubble_audit.py --evidence`**; follow the printed `hint`
  (for the logs: use the workload source for the workflows).

## Workload (`--source workload`)

One `metrics workload-breakdown` call per family, each row a workflow with its `activity_count`
(runs) and `workload_used`, joined to the export:

| Family (`tag1`) | Rows keyed by |
|---|---|
| `schedule_api_event` | APIEvent inner `id` (scheduled backend workflows) |
| `run_data_trigger_workflow` | DatabaseTriggerEvent `id` |
| `recurring_event` | RecurringEvent `id` |
| `workflow` | page or reusable workflow inner `id` |
| `api` | Workflow API endpoint name as the caller typed it (folded case-insensitively), plus Data API calls keyed by data-type name (not workflows) |

- A backend workflow ran = its scheduled runs + Workflow API calls to its name. An exposed endpoint
  whose name is also a data type's cannot be told apart from Data API calls: unknown unless it ran
  through the schedule.
- **Custom events**: a backend custom event is not metered on its own — it runs inside the workflow
  that invokes it — so it counts through its triggerers, across chains of custom events: the runs of
  every workflow that leads to it, an upper bound (the trigger may be conditional). Page and
  reusable custom events that run server-side actions also get rows of their own in `workflow`,
  which count as well. Nothing leads to one → unknown, never 0.
- Page workflows are metered only when they run server-side actions: their runs prove use, their
  silence proves nothing. Pages and API Connector calls: unknown (`not_metered`).
- Counts cover every version (live and test), web and mobile.
- Bubble keeps about 31 days of workload history and answers wider windows with the same data: the
  script reads `metrics workload-by-date` and states the effective window (`window.data_from`,
  `window.days`). Say that window, not the one asked for.
- Its own control, per family: the rows must add up to the total Bubble reports for the family, and
  most of the runs (`joined_share` ≥ 0.5) must belong to workflows of the export. Rows missing while
  the family shows activity → `blind`; rows short of the total or cut by the limit → `partial`;
  runs that are not this export's workflows → `unjoined` (another export, or tags that are not inner
  ids). In those families only the runs found count. No workload data at all, or an export that no
  active family joins → exit 3.
- No first/last seen: the breakdown covers the window as a whole.

## Logs (`--source logs`)

- Logs of `live` by default (reading is safe; that is where the real traffic is).
- One paginated pull of the whole window, matched locally per candidate by whole identifier (`home`
  does not count rows about `homepage`) — method `window`. When that pull stops early its hits
  still count, but its zeros are asked again one by one with a server-side `contains` query —
  method `window (partial) + per-candidate`. When Bubble returns an empty window (busy apps need a
  search term) or the pull fails, every candidate gets its own query — method `per-candidate`.
  Queries are capped by `--max-candidates`; the rest are `skipped`.
- **Positive control.** On some large apps the logs endpoint answers EVERY query "ok, 0 rows, not
  truncated" — even for workflows the workload metrics show running all day in the same window — which would stamp every candidate "not seen". So no zero is trusted before a
  workflow known to run in the window comes back with rows: `--control`, else the busiest scheduled,
  database-trigger or recurring workflow of the window in `metrics workload-breakdown`, named
  through the audit JSON or the export, else any candidate that came back with hits. A complete
  window that misses the control counts as partial.
  - Control comes back empty → every zero becomes unknown (`coverage: blind`, "logs endpoint
    returned no rows for a known-active workflow"), no candidate is asked, exit 3.
  - No control at all (no export, no `--control`, no hits) → zeros are `unverified`, exit 3.
  - `source.positive_control` records which workflow was asked, where it came from and what came
    back; the printed summary repeats it.
  - The workload metrics count every version: when reading another version than live
    (`--app-version test`), pass `--control` with a workflow that runs there.
- A query that fails or stops early with zero rows gives `unknown`, never `not seen`.

## Reading the result

- **Seen / ran** → the candidate is alive: take it off the deletion list and tell the owner who
  seems to call it (an external system, a scheduled job, direct links). For a page "seen" means it
  was served; for a workflow, that it ran.
- **Not seen / did not run** → *in this window*, nothing more. Say the window (for the logs, also
  the plan's retention); monthly jobs, yearly renewals and seasonal flows can sit outside it. It
  strengthens a static "unused" verdict; it never proves death on its own.
- **Unknown** → no evidence either way. `coverage` says why: `not_metered` (the source cannot
  measure it), `partial`/`failed`/`skipped` (incomplete data), `blind`/`unverified` (the source
  showed nothing for what is known to run); `reason` spells it out.

Feed both files to the report — `bubble_audit.py --evidence <logs file> --evidence <workload
file>` (only files that exited 0). For each candidate, seen beats not seen beats unknown, so a source
that cannot measure an item never hides one that did, and each badge names its source: **logs: N×**
for server logs, **runs: N×** (pt **execuções: N×**) for workflow runs.

Relay the counts in the conversation (e.g. "the `payment_webhook` endpoint ran 1,284 times in 30
days"), never the rows. In `unbubble:clone` (step 3b) the same evidence answers "does this endpoint
have external consumers?" and "is the integration behind this flag alive?".
