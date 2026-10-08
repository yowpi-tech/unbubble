# Level-up assessment checklist & translation guide

Evidence-first: every item you flag must cite the clone docs / inventory JSONs. Items are
grouped by the priority order (security & reliability → data → performance → maintainability →
UX). The Bubble→modern translation table and the migration decision matrix are at the end.

## 1 · Security (priority 1)

- [ ] **Endpoints without auth** — `summary.json.security_flags.endpoints_without_auth`
      (Bubble `auth_unecessary: true`). Each is a publicly callable URL. Who calls it? Is there
      a shared-secret param (weak) or nothing?
- [ ] **Endpoints ignoring privacy rules** — `ignore_privacy_rules: true` on exposed WFs means
      the workflow reads/writes with admin-like power; combined with no-auth this is critical.
- [ ] **Data API over-exposure** — `data_api.json` exposed tables vs their `privacy_rules` in
      `database.json`. A table exposed with `everyone: view_all=true` leaks to anyone with the
      URL. Bubble privacy rules are the ONLY server-side guard; page-level "hide if not admin"
      conditionals are client-side and worthless as security.
- [ ] **Existing Data API tokens** — each one (`BUBBLE_API_TOKEN_*` in the clone's
      `secrets/ENV-KEYS.md`) is an admin key: privacy rules do not limit it, it reads and writes
      every exposed type and can run any public API workflow. Who holds each token, which
      integration still needs it, which can be revoked now? None of them is reused for the
      migration ETL.
- [ ] **Role model** — how are roles stored? (Bubble typical: text field / option set on User,
      checked in page conditionals). Flag anything client-enforced. Note sentinel values shared
      across users (e.g. one shared ADMIN code for a whole team = no per-user accountability).
- [ ] **Secrets** — plugins/API-connector with keys: the full inventory is the clone's
      `secrets/ENV-KEYS.md` (var ↔ service ↔ in-use; values live only in `secrets/.env`).
      Where will each live in the new system (vault/env)? Any key visible client-side in
      Bubble (the ENV-KEYS "client-safe" section) must be rotated at migration; keys of
      unused providers/plugins are drop candidates.
- [ ] **PII inventory** — which tables hold personal data (emails, SSN-like, licenses)? LGPD:
      retention, deletion capability (Bubble soft-delete patterns), export capability.
- [ ] **Audit trail** — does the app log who changed what? (Bubble: usually Modified By only.)

## 2 · Reliability / correctness of results (priority 1)

- [ ] **No real constraints** — Bubble has no unique/not-null/FK enforcement. Look for
      workflow-enforced uniqueness (search-then-create patterns) → race-condition duplicates.
- [ ] **Multi-step workflows without transactions** — a Bubble WF that creates 3 things can
      fail at step 2 and leave partial state. List the critical ones (payments, hierarchy
      changes, policy status).
- [ ] **Scheduled/recurring jobs** — `backend_workflows.json` DatabaseTriggerEvent + Recurring:
      what happens on failure? (Bubble: silent retry or nothing.) Which computations are
      cached into tables (rank caches, KPI tables) and can drift from source data?
- [ ] **Calculation correctness** — reports/dashboards: are numbers computed in repeating-group
      client expressions (unauditable) or in backend WFs? Timezone handling (`tz_*` flags).
- [ ] **Idempotency** — endpoints called by external systems: safe to retry?
- [ ] **No tests** — Bubble apps have zero automated tests by construction. The BR-xxx rules
      from clone docs become the test suite of the rebuild.

## 3 · Data model quality

- [ ] **Text-as-foreign-key** — text fields holding what should be a relation (code
      strings used as join keys). Fragile: renames/typos break joins.
- [ ] **List fields** — `is_list: true` on custom/user refs = embedded many-to-many with no
      integrity and 10k-item ceiling → join tables.
- [ ] **God tables** — User with 100+ fields mixing profile, prefs, cached KPIs → decompose.
- [ ] **Cache/satellite tables** — `*_cache`, denormalized rank/KPI tables → views,
      materialized views, or computed-on-read.
- [ ] **Soft-delete conventions** — `Deleted` boolean fields + privacy rules like "⚠️ Not
      deleted" → decide: real deletes + audit table, or first-class `deleted_at`.
- [ ] **Option sets as data** — sets whose options change with business (products, carriers)
      belong in lookup TABLES; sets that are truly static (states, statuses) → enums.
- [ ] **Naming drift** — field display names vs meaning (legacy columns frozen at creation);
      the new schema is the chance to fix names (record old→new in the mapping).

## 4 · Performance

- [ ] Client-side filtering of large lists (`:filtered` on full-table searches) → server queries
      with indexes.
- [ ] Repeating groups over 1k+ rows (Bubble hard-paginates; the app may already have
      workarounds like export-to-CSV plugins) → real pagination/virtualization.
- [ ] Chatty external API usage (per-row API calls in RGs).
- [ ] Heavy recurring recomputation that should be event-driven or incremental.

## 5 · Maintainability

- [ ] Workflow spaghetti: count of WFs per page (pages.json `workflow_count`), copy-suffixed
      duplicates ("copy", "copy 2"), dead branches noted by the audit.
- [ ] Duplicate pages (bk_/old/test variants) that encode divergent logic — which is truth?
- [ ] Plugin sprawl: overlapping plugins (several CSV exporters), delisted/removed plugins
      still referenced (audit section 10), paid plugins to not re-license.
- [ ] Bus factor: undocumented rules recovered only via clone step — now codified in BR-xxx.

## 6 · UX/UI (priority 2 — after security & reliability)

- [ ] Flows with the most usage/roles: keep muscle memory unless clearly broken.
- [ ] Mobile behavior (Bubble responsive quirks), accessibility baseline (contrast, keyboard),
      load feel (spinner-heavy pages).
- [ ] Consistency: styles/variables audit (audit section 6) shows how coherent the design is;
      plan a design system with tokens.
- [ ] Error states: Bubble default alerts vs designed empty/error/loading states.

## Bubble → modern translation table

| Bubble construct | Rebuild as |
|---|---|
| Data type | Table with real PK (keep `bubble_id` for migration traceability) |
| Field `list.custom.X` / `list.user` | Join table with FKs |
| Option set (static) | DB enum / constant module |
| Option set (business-managed) | Lookup table + admin CRUD |
| Privacy rules | Server-enforced authz: RLS policies / policy middleware — never client checks |
| Page workflows | Frontend handlers calling typed API endpoints |
| Backend WF (exposed) | Versioned API endpoint with auth + validation + idempotency key |
| Backend WF (scheduled/internal) | Queue job / cron worker with retries + dead-letter + alerting |
| Database trigger event | DB trigger, transactional outbox, or event handler — choose ONE pattern |
| Recurring event | Scheduled job (idempotent, observable) |
| Custom event | Shared service function |
| Reusable element | UI component |
| Plugin (service wrapper) | Official SDK / direct REST integration, keys in secret manager |
| Bubble file storage | Object storage (S3-compatible) with signed URLs |
| Modified/Created Date, Creator | Explicit audited columns + audit log table |

## Migration decision matrix (per table)

| Criterion | CSV export/import | Data API sync |
|---|---|---|
| Volume | fine < ~50k rows | any; paginated (cursor on Modified Date) |
| Relations | manual re-link by unique id column | resolve via `bubble_id` lookups during load |
| Lists | comma-joined text → parse | JSON arrays of unique ids → clean |
| Files/images | URLs in CSV — still must download assets | same; script the download+reupload |
| Delta / dual-run | none (one-shot, needs freeze) | incremental sync → near-zero-downtime cutover |
| Effort | low (small static tables) | one reusable ETL for all tables |
| Auth | editor access only | Data API enabled + the migrated types exposed + a dedicated token the owner creates by hand. An admin token ignores privacy rules and cannot be scoped to read-only or to some tables — per-type exposure is the only boundary; delete the token and revert the exposures after cutover |

Default recommendation: **Data API sync for core/large/hot tables + CSV for small static
lookups**; always keep `bubble_id`, migrate in FK-dependency order, validate with row counts +
per-table checksums + owner-signed spot checks, and keep Bubble read-only as archive after
cutover.
