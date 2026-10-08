# Connected mode — applying the audit cleanup

Turns an audit round into deletions made through the MCP, on a branch, batch by batch, each batch
approved by the owner — then verified with a fresh export and a new audit round. The owner merges
the branch and later deploys, both by hand.

`<unbubble>` = the UnBubble checkout; `<proj>` = `~/UnBubble-Projects/<app>`; `<app>` = the app id;
`<branch>` = the cleanup branch id.

## Before starting

- **An audit round run with `--json`** by the current `bubble_audit.py` (`summary_version` 2: every
  finding carries its tracker key) on a **complete** export. If that round says `EXPORT INCOMPLETE`,
  stop — nothing gets deleted from an incomplete export (`cleanup_plan.py` refuses it too).
- **The owner reviewed the report.** Items they keep are marked "kept" in the report's tracker, and
  its export (`<proj>/audit/bubble_cleanup_progress__<app>.json`) is passed to the plan.
- A working session for the app (`setup.md`).

## 1 · Isolate the writes

**Preferred — a branch.** Preview, ask, then create:

```
bubble_branch_create  {profile: "<app>", name: "unbubble-cleanup-v<N>", from_app_version: "test", execute: false}
```

After the owner's yes, the same call with `execute: true`. Branch names: lowercase letters, digits
and dashes. Confirm the id with `bubble_branch_list`, then add the branch profile:

```bash
python3 <unbubble>/mcp/launch.py cli profile add <app>--<branch> --app-id <app> \
    --app-version <branch> --session-profile <app>
```

**No branches on the plan** — write on `test` only after the owner has created a savepoint by hand
in the editor's version control and confirmed it in the conversation. Everything else below stays
the same, with `test` as the target.

## 2 · Build the plan

```bash
python3 <unbubble>/skills/connect/scripts/cleanup_plan.py <proj>/audit/<app>-vN_audit.json \
    --profile <app>--<branch> --app-version <branch> \
    --progress <proj>/audit/bubble_cleanup_progress__<app>.json \
    --journal  <proj>/audit/cleanup-applied__<app>.json
```

Writes `<app>-vN_cleanup-plan.json` and `.md` next to the audit JSON: batches in dependency order —
workflows on deleted elements and uncalled page custom events → pages → option sets → styles →
color and font variables → data fields → data types — each item with its tracker key, a label, the
tool, its preview arguments `args` (`execute: false`) and the approved-write arguments
`apply_args` (`execute: true`, `dry_run: false`); a **manual** list; and what was left out and why.

Styles are targeted by their exact `style_id`, with the display name as a cross-check — style
names resolve loosely in the MCP and could hit another style that is in use. Color and font
variables are targeted by their token id. A `--progress` or `--journal` file that is missing or not
JSON stops the script: ignoring it would put items the owner kept back into the plan.

- Default: high-confidence categories only.
- `--include-review` adds unused pages and workflows on never-rendered elements — the owner looks at
  each of those in the report first.
- `--include-destructive` adds data fields and data types: soft deletes (Bubble keeps the data
  recoverable until someone permanently deletes it, which this edition cannot do), never the ones
  exposed in the Data API. Ask the owner explicitly before using it.
- Items kept by the owner, already deleted (progress) or already applied to this target (journal)
  are left out.

Show the owner the plan's markdown: counts per batch, the manual list, what was left out.

## 3 · Apply, batch by batch

For each batch, in the plan's order:

1. **Preview** every item: call `item.tool` with `item.args` exactly as written (`execute: false`).
   An item whose preview fails (not found any more, a style id whose name no longer matches) leaves
   the batch; note why.
2. **Ask.** Summarize the batch — how many items, their labels, the failed previews — and ask with
   AskUserQuestion: *Apply all N* / *Let me choose* / *Skip this batch*. A yes covers this batch only.
3. **Apply** each approved item: call `item.tool` with `item.apply_args` as written — `execute: true`,
   `dry_run: false` (the schemas default `dry_run` to `true`; some hosts fill defaults),
   `confirm: true` and the explicit `app_version`. One call per item, and right after each call
   record it:

   ```bash
   python3 <unbubble>/skills/connect/scripts/cleanup_journal.py add --app <app> --key "<item.key>" \
       --tool <item.tool> --app-version <branch> --label "<item.label>"
   # failed call: add  --failed --note "<short error, no data>"
   ```

4. **Stop** at the first refusal from the write guard or the policy (`WriteBlocked`,
   `ToolCallBlocked`) or any unexpected error: report it and wait. Never change the arguments to get
   around a refusal.

## 4 · Verify

```bash
python3 <unbubble>/skills/connect/scripts/fetch_export.py --app <app> --version <branch> --profile <app>--<branch>
python3 <unbubble>/skills/audit/scripts/bubble_audit.py <the downloaded .bubble> \
    --out  <proj>/audit/<app>-v<N+1>_unused_report.html --json <proj>/audit/<app>-v<N+1>_audit.json \
    --state <proj>/audit/bubble_cleanup_progress__<app>.json --state <proj>/audit/cleanup-applied__<app>.json
python3 <unbubble>/skills/connect/scripts/cleanup_journal.py verify --app <app> --app-version <branch> \
    --audit <proj>/audit/<app>-v<N+1>_audit.json
```

`verify` marks each applied item as verified when round N+1 no longer reports it, and lists the
ones still reported (applied but not effective — look at those before anything else). Report to the
owner: applied, verified, failed, still reported, plus the manual list.

## 5 · The owner merges (and later deploys)

The owner opens the branch in the Bubble editor, reviews it and merges it into the main version
(`test`) themselves — conflicts with work done on `test` meanwhile are resolved there. Then:

```bash
python3 <unbubble>/skills/connect/scripts/cleanup_journal.py merged --app <app> --app-version <branch>
```

From then on the journal entries count as deleted for the tracker (`bubble_audit.py --state …
cleanup-applied__<app>.json`) and in the console. **Entries of an unmerged or discarded branch never
count.** Deploying `test` to live stays with the owner — check `cutover.md › Before any deploy`.

The MCP also has merge tools (`bubble_branch_merge_*`); use them only when the owner explicitly asks
for it, with a preview and an approval per step.

**The owner rejects the branch** — they delete it in the editor, or, after their yes, preview and
call `bubble_branch_delete {profile: "<app>", app_version: "<branch>", execute: true, confirm: true}`
(the write guard only lets the MCP delete branches it created).

## 6 · The manual list

What the MCP cannot delete — reusable definitions, backend workflows and backend custom events,
plugins, API Connector calls, references to removed plugins, mobile views, styles or variables
whose name is shared — goes to the owner with where to find each item in the editor
(`manual` in the plan). Best done on the same branch before the merge; the next audit round shows
what is left, and the owner ticks them in the report's tracker as usual.

## Never

Writing to live · deploying · permanent deletes · deleting data types or fields exposed in the Data
API · uninstalling plugins through the MCP (no tool; manual) · applying a batch the owner did not
approve in this conversation · treating a tool's "ok" as proof (the export is the proof).
