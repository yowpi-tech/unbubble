# Connected mode — the Bubble side of the cutover

`unbubble:level-up` decides the migration (MIGRATION-PLAN: CSV or Data API per table, freeze or
dual-run, DNS switch, Bubble kept read-only as an archive). Connected mode carries out and checks
the steps that happen inside Bubble. Every write follows the protocol of `cleanup.md` — branch (or
an owner savepoint), preview, owner approval in the conversation, `execute: true` + `dry_run: false`
+ `confirm: true` + explicit `app_version`, verification by export — and **every deploy is the
owner's, in the editor**. The agent never deploys, never handles API tokens and never reads
database records: the migration ETL runs in the new system.

## 1 · Size the new platform (read-only)

Storage (`bubble_storage_usage_get`), plan usage (`bubble_plan_usage_get`), WU per day and hour
(`bubble_workload_usage_by_date`), what spends it (`bubble_workload_usage_breakdown`), run counts
(`bubble_workflow_runs_get`) → MIGRATION-PLAN sizing, peak hours, the best freeze window
(`diagnostics.md`).

## 2 · Data API for the ETL

What Bubble's Data API grants, per the Bubble manual:

- A request with an **admin API token** (Settings → API) acts with the builder's permissions:
  **privacy rules do not limit it** — it can read, change and delete every record of every exposed
  type, and trigger any public API workflow. Tokens cannot be scoped to read-only or to some tables.
- Requests without a token, or with a user token (from a "Log the user in" API workflow), only get
  what the privacy rules let "everyone" or that user see.
- **Per-type exposure is the only hard boundary**: a type not exposed in the Data API is unreachable
  for every caller, admin tokens included.

So:

1. **Enable the Data API** (Settings → API) — the owner, by hand.
2. **Expose only the types being migrated**, on the cleanup or a migration branch, after reviewing
   each type's privacy rules (`list_privacy_rules`) — what "everyone" may see becomes readable by
   anyone who knows the URL:

   ```
   set_data_type_api_exposure {profile: "<app>--<branch>", data_type_ref: "<type key>", enabled: true,
                               app_version: "<branch>", confirm: true, execute: false}
   ```

   Preview, ask, apply (`execute: true`, `dry_run: false`), verify in the branch's export
   (`exposed_api`). It takes effect on live only when the owner merges and deploys. Exposure on
   `test` also opens the test database at `/version-test/api/1.1/obj/<type>`.
3. **The API token** — the owner creates a dedicated token for the migration in Settings → API and
   puts it straight into the new system's secret store (never in the conversation, a file in the
   repo, or a ticket). The token tools are disabled in this edition. Existing tokens preserved by
   `unbubble:clone` in `secrets/.env` belong to existing integrations: do not reuse them for the ETL.
4. **After the cutover** — the owner deletes the migration token, and the exposures are reverted
   with the same protocol (`enabled: false`).

## 3 · Redirects

301 redirects for routes that change (`list_301_redirects` to read the current ones):

```
create_301_redirect {profile: "<app>--<branch>", from_url: "/old-page", to_url: "https://new.example.com/page",
                     app_version: "<branch>", execute: false}
```

Same protocol; effective on live after the owner's merge and deploy, timed with the switch. DNS
changes happen outside Bubble, by the owner.

## 4 · Before any deploy

A Bubble deploy takes **everything** pending in `test`: the connected-mode cleanup, the exposures,
and whatever collaborators changed meanwhile. Before the owner deploys:

- `bubble_changelog_fetch {profile: "<app>", app_version: "test", start_timestamp: <last deploy, epoch ms>}`
  → summarize the changes by page/area and author (`bubble_branch_contributors` for names). The
  owner gives the time of the last deploy (the deploy-history tool is disabled with the deploy
  tools);
- point out anything unexpected — the owner decides; the deploy itself stays in the editor.

## 5 · Drain checks after the switch

Bubble should go quiet once traffic moves. Daily, until the owner closes the app:

- `bubble_workload_usage_by_date` with `granularity: "hour"` — the curve should fall to background
  level (scheduled jobs that still run there are part of the plan or a leftover to switch off);
- `scripts/runtime_evidence.py` on the round's endpoints and backend workflows, or
  `bubble_logs_fetch` with `contains` per endpoint — anything still **seen** is a caller to re-point
  (payment and messaging webhooks, partner systems, old links, mobile apps in the field);
- report counts per day per endpoint; never log rows.

When live traffic is only the archive's own reads, the owner turns Bubble read-only (privacy rules,
a maintenance page, removing editing roles) and later downgrades or closes the plan — owner actions.

## Never

Deploying · creating, rotating or reading API tokens · exposing types beyond the migration's needs
· reading or exporting database records through the MCP · writing to live.
