---
name: level-up
description: >
  Re-architect a Bubble.io app for rebuild OUTSIDE Bubble with an engineering upgrade. Takes
  the as-is documentation + clone PRD produced by unbubble:clone and: assesses the current
  system against market best practices (tech debt, security posture, data-model quality,
  performance, maintainability), designs a state-of-the-art target architecture where
  INFORMATION SECURITY and RESULT RELIABILITY come first and UX/UI second, redesigns the data
  model where Bubble's structure is inadequate, and produces the Bubble→new-system DATA
  MIGRATION PLAN (CSV export/import vs consuming the Bubble Data API, cutover, validation).
  Output is an AI-ready rebuild pack (assessment, target architecture, new data model + mapping,
  migration plan, PRD v2, backlog). Use when the user asks to: "level up", "sair do Bubble",
  "migrar do Bubble", "recriar com melhores práticas", "modernizar o sistema", "upgrade de
  engenharia", "plano de migração", "reengenharia", "novo stack", "repensar o sistema",
  evaluate tech debt of a Bubble app, or plan the rebuild after unbubble:clone. Step 3 (final)
  of the UnBubble pipeline.
---

# UnBubble · level-up — re-architecture + migration plan

**Pipeline position: step 3 of 3.** Inputs: the `docs/` set + `PRD-clone.md` from
`unbubble:clone` (required — if missing, run clone first) and optionally the `.bubble` +
inventory JSONs for spot-checks. Output: a **rebuild pack** an AI (or team) can execute to
recreate the system on a new platform with an engineering upgrade.

All inputs and outputs live in the project folder `~/UnBubble-Projects/<app-id>/` (shared by
the whole pipeline): read `docs/` + `PRD-clone.md` from there and write the `levelup/` pack
next to them.

**Priorities, in order — never trade down:**
1. **Information security** and **reliability of results** (the system must be trustworthy:
   correct numbers, no data leaks, no silent failures).
2. **UX/UI** — preserved where good, improved where weak.
3. Everything else (cost, delivery speed, stack preferences).

## Workflow

### 1 · Assess the as-is system

Read `references/assessment-checklist.md` and score the current system against it. Ground every
finding in evidence from the clone docs / inventory (quote the table, endpoint, or workflow).
Deliver `ASSESSMENT.md`:

- Scorecard (1–5) per dimension: security, reliability/correctness, data model, performance,
  maintainability, UX. One paragraph of evidence per score.
- **Tech-debt register**: each debt item with severity, evidence, and what it costs the business
  (e.g. "all admins share one sentinel account → per-user audit impossible").
- **Security findings first-class**: start from `summary.json.security_flags` (endpoints without
  auth, endpoints ignoring privacy rules), Data-API over-exposure vs privacy rules, secrets
  handling, roles enforced client-side.
- What is **good** and must be preserved (flows users like, rules that encode hard-won domain
  knowledge). A rebuild that loses these is a regression.

### 2 · Design the target architecture

Deliver `TARGET-ARCHITECTURE.md`:

- **2–3 candidate stacks** with trade-offs, then ONE recommendation with justification tied to
  the assessment (team skills, app shape, integration list). "State of the art" means proven
  and appropriate for the case — not fashionable.
- **Security architecture** (priority 1): authn (managed IdP vs roll-your-own), authz model
  translating Bubble privacy rules → server-enforced policies (e.g. Postgres RLS or a policy
  layer), tenancy/hierarchy scoping, secrets management, audit logging, backups/DR, LGPD/PII
  handling.
- **Reliability architecture** (priority 1): typed schema with real constraints (FKs, unique,
  not-null), transactions where Bubble had multi-step workflows, idempotent jobs replacing
  recurring/DB-trigger events, input validation at the boundary, automated tests on the
  BR-xxx business rules, observability (structured logs, error tracking, metrics).
- **UX/UI plan** (priority 2): design system choice, which flows are kept as-is vs redesigned,
  accessibility and responsiveness baseline.
- Integration map: every external API/plugin-service from the clone docs → how the new system
  talks to it (direct SDK, webhook, queue) and which credentials must be re-issued.

### 3 · Redesign the data model

Deliver `DATA-MODEL.md`: the new schema (mermaid erDiagram + DDL sketch) plus a **field-by-field
mapping table** old → new. Apply the Bubble anti-pattern translations in the checklist (option
sets → enums/lookup tables, list-fields → join tables, text-as-FK → real FKs, satellite/cache
tables → views or materialized queries…). Every as-is field must appear in the mapping — mapped,
transformed, or explicitly dropped with a reason.

### 4 · Plan the data migration

Deliver `MIGRATION-PLAN.md`. Decide **per table** between the two mechanisms (decision matrix in
the checklist):

- **CSV export/import** — one-shot, good for small/static tables; loses type fidelity (dates,
  lists serialize as comma-joined text), requires manual re-linking of relations, no delta.
- **Bubble Data API consumption** — the new system (or an ETL job) pages through
  `/api/1.1/obj/<type>` with a **Modified Date cursor**: preserves the Bubble `unique id` (keep
  it as `bubble_id` column for traceability + FK resolution), supports incremental delta sync,
  enables **dual-run** and a low-downtime cutover. Requires enabling Data API + an API token —
  scope it read-only and to the tables being migrated; note privacy rules DO apply to API
  tokens' visibility unless configured otherwise.

Also cover: file/S3 asset migration (Bubble-hosted files must be downloaded and re-uploaded),
option-set values → enum seed data, ordering of tables by FK dependency, **validation &
reconciliation** (row counts + checksums per table, spot-check queries the owner signs off),
rollback plan, and the cutover runbook (freeze window or dual-write, DNS/embed switch, Bubble
kept read-only as archive).

### 5 · Produce the rebuild pack

```
levelup/
  ASSESSMENT.md            scorecard, tech-debt register, security findings, keepers
  TARGET-ARCHITECTURE.md   stack decision, security & reliability architecture, UX plan
  DATA-MODEL.md            new schema + old→new mapping table
  MIGRATION-PLAN.md        per-table mechanism, cutover runbook, validation
  PRD-v2.md                PRD-clone rewritten for the new platform: parity requirements
                           (BR-xxx) + the upgrade requirements (security, reliability, UX)
                           + explicit non-goals
  BACKLOG.md               epics → stories with acceptance criteria, sequenced: foundations
                           (auth, schema, CI) → migration pipeline → modules by business value
                           → cutover; each story references PRD-v2 sections
  RISKS.md                 top risks with mitigations (migration data loss, endpoint consumers
                           breaking, scope creep, dual-run drift)
```

The pack must be **self-sufficient for an AI to implement**: no reference to "the conversation",
every decision recorded with its why, every requirement testable.

## Quality bar

- Every assessment claim cites evidence from the clone docs/inventory.
- Security/reliability decisions are never traded for UX or speed — if a trade-off is forced,
  it is written down in RISKS.md with the user's explicit sign-off required.
- The migration plan accounts for **every** table and file field in DATA-MODEL.md's mapping.
- PRD-v2 keeps full traceability to BR-xxx rules so parity is verifiable after the rebuild.
