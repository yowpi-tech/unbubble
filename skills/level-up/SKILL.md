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
  Output is an AI-ready rebuild pack (assessment, target architecture, frontend design brief, new
  data model + mapping, migration plan, PRD v2, backlog, risks). When the `enterprise-best-practices`
  skill is available it is applied as a production-readiness lens (13 layers + 5 business themes);
  otherwise the user is asked whether to install it. Use when the user asks to: "level up", "sair do Bubble",
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

### 0 · Gate: resolve open questions with the user FIRST

Read `docs/08-open-questions.md` before anything else. If any question that affects security,
architecture, data model or migration is still unanswered, ASK THE USER NOW (AskUserQuestion tool
when available, batches of up to 4 with concrete options + free-text; otherwise ask in chat) and
record the answers in 08 as dated owner decisions ("Decisões do dono (YYYY-MM-DD)"). Do not design
around an unanswered blocking question — an assessment built on guesses produces a rebuild pack
the owner has to redo.

### 0b · Load the production-gate lens (`enterprise-best-practices` skill)

The level-up is exactly a "day-0 architecture + production-readiness" moment, which is what the
**`enterprise-best-practices`** skill exists for (13 production layers + 5 business themes as
quality gates). Use it as a lens across the whole pack — assessment dimensions, target-architecture
day-0 decisions, and the backlog's readiness stories.

1. **Check availability.** If `enterprise-best-practices` is in this session's available-skills
   list, **invoke it now** (Skill tool) and carry its 13-layer / 5-theme gates into steps 1, 2 and
   5 — cite the layer next to the finding/story it drives.
2. **If it is NOT available, ASK the user** (AskUserQuestion when available) whether to install it,
   offering:
   - **Install it** — clone `https://github.com/yowpi-tech/enterprise-best-practices` into
     `~/.claude/skills/enterprise-best-practices` (a new interactive session then sees it); then
     invoke it.
   - **Proceed without it** — continue using only `references/assessment-checklist.md`; note in
     `ASSESSMENT.md` that the enterprise gates were not applied.
   Do not clone anything without the user's yes, and never block the level-up on it — it enriches
   the pack, it is not a hard dependency.

When applied, record in `ASSESSMENT.md` which layers/themes were checked, so the pack states its
own coverage.

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
  accessibility and responsiveness baseline. Two recurring UX translations worth calling out:
  **theme (light/dark)** is CSS + client state (custom properties / `prefers-color-scheme`), never
  a DB enum/column — drop the Bubble theme option set and per-user theme field; and a **WYSIWYG
  HTML editor** is a candidate to become a **Markdown WYSIWYG** (e.g. Milkdown) when the owner
  wants Markdown as the canonical content — if so, plan the HTML→Markdown conversion in the
  migration (archive the original HTML) and render Markdown→HTML server-side for any PDF pipeline.
- Integration map: every external API/plugin-service from the clone docs → how the new system
  talks to it (direct SDK, webhook, queue) and which credentials must be re-issued.
- **Plugin translation policy (standing owner decision):** plugins that provide FRONTEND
  functionality (editors, toasts, icons, masks/validation, QR rendering, JS utils…) are rebuilt
  as **native code** in the new stack — turn each one (from `03-plugins.md`) into a build task;
  only EXTERNAL-SERVICE integrations get a keep/replace/SaaS evaluation here.

### 2b · Frontend design brief for Claude Design

Deliver `FRONTEND-DESIGN.md` — a self-contained brief the owner runs through **Claude Design**
BEFORE any UI implementation starts. It must contain:

- **Design tokens extracted from the actual export** (not invented): the real color palette
  (`settings.client_safe.color_tokens_user`, ranked by usage in the raw export), the fonts in use,
  and neutrals — mapped to CSS-variable token names with a light/dark note and an accessibility
  caveat (flag brand colors that fail AA on text).
- **Design principles** tied to what the app IS (a dense work tool vs a marketing site, the tone
  the domain needs).
- **Component inventory** (design-system pieces) and a **screen inventory** ranked by priority
  using `pages.json` element/workflow counts.
- **Ready-to-paste prompts** for Claude Design: one for the system/tokens, then one per P0 screen.
- A handoff note: approved tokens → `tailwind.config` + CSS vars, components → shadcn/ui, feeding
  the design story in BACKLOG. The brief changes presentation only — never BR-xxx rules or the
  data model.

Extract the palette/fonts with a small script over the `.bubble` (never hand-wave the tokens);
put the color anchors and font names in the doc so Claude Design has real brand input.

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
  FRONTEND-DESIGN.md       design brief for Claude Design: tokens from the export, screen
                           inventory, ready-to-paste prompts (run BEFORE UI implementation)
  DATA-MODEL.md            new schema + old→new mapping table
  MIGRATION-PLAN.md        per-table mechanism, cutover runbook, validation
  PRD-v2.md                PRD-clone rewritten for the new platform: parity requirements
                           (BR-xxx) + the upgrade requirements (security, reliability, UX)
                           + explicit non-goals
  BACKLOG.md               epics → ATOMIC stories with acceptance criteria, sequenced:
                           foundations (auth, schema, CI) → migration pipeline → modules by
                           business value → cutover; every story CITES the requirement ids it
                           implements. If the enterprise-best-practices gates were applied
                           (step 0b), each unmet production layer becomes a readiness story.
  RISKS.md                 top risks with mitigations (migration data loss, endpoint consumers
                           breaking, scope creep, dual-run drift)
  EXECUTION-CONTRACT.md    rules of engagement for the executing AI — read order, story
                           discipline, the final completeness gate, deviation protocol
```

The pack must be **self-sufficient for an AI to implement**: no reference to "the conversation",
every decision recorded with its why, every requirement testable.

### 5b · Execution contract (so the executing AI leaves nothing behind)

Write `EXECUTION-CONTRACT.md` — the FIRST file the executing AI must read. It contains, at
minimum:

1. **Source of truth & read order**: this pack (PRD-v2 → DATA-MODEL → TARGET-ARCHITECTURE →
   BACKLOG → MIGRATION-PLAN) plus the clone `docs/` for domain context and `PARITY-MATRIX.md` as
   the completeness ledger. Nothing in the pack may be contradicted or "improved away" without a
   dated owner decision.
2. **Story discipline**: implement in BACKLOG order respecting dependencies; a story is DONE only
   when its acceptance criteria demonstrably pass (test or observed behavior); stories are never
   skipped or silently merged.
3. **Final completeness gate** — the rebuild is only "done" when: every `PARITY-MATRIX.md` row is
   checked off (or carries a signed deviation); `spec_coverage.py` and `parity_check.py` both
   pass; the BR-xxx test suite is green; readiness stories from the enterprise gates (if applied)
   are done; MIGRATION-PLAN validation is signed by the owner.
4. **Deviation protocol**: anything the executor cannot or believes should not implement becomes a
   listed deviation (what, why, impact) requiring the owner's dated sign-off — dropping a
   documented item silently is a contract violation, and "the AI decided it was unnecessary" is
   not a valid disposition.

### 5c · Spec-coverage gate — no requirement without an executor (run BEFORE delivering)

The parity matrix guards *legacy → disposition*. This gate guards the opposite direction,
**requirement → story**, which is where documented features die: they are written in the docs and
the PRD, no BACKLOG story ever owns them, and the executor delivers a subset that looks complete.
(Seen in practice: features written in the business rules and in the PRD that no story cited
were simply not built, and only users noticed.)

```bash
python3 scripts/spec_coverage.py \
  --spec <workdir>/docs/07-business-rules.md \
  --spec <workdir>/levelup/PRD-v2.md \
  --backlog <workdir>/levelup/BACKLOG.md \
  --out <workdir>/levelup --strict-acceptance
```

It fails (exit 1) on: a requirement no story cites (coverage is transitive — a story citing
`P-DOC-1` covers the `BR-010` it derives from); a story citing no requirement; a story left
undecomposed; and, with `--strict-acceptance`, a requirement without verifiable form.

**Do not deliver the pack until it passes.** Fix by writing the missing story, adding the
citation, splitting the story, or — only with a dated owner decision — descoping the requirement.
Two conscious escape hatches exist and both must be *earned*: `[infra]` on a story that
implements no product requirement (bootstrap, migration, cutover) and `[descritivo]` on a
requirement that is context rather than behaviour.

Write the requirements so this passes by construction:

- **PRD requirements are testable.** `U-REL-1` style: state the behaviour and an explicit
  `*Aceite:*` (or `QUANDO … DEVE …`). "Implementar X bem" is not a requirement.
- **Stories are atomic.** No `(G)` and no "quebrar depois" survives into the delivered pack — an
  epic marked for later decomposition is precisely where the executor improvises. Split until
  each story has its own verifiable acceptance criterion.
- **Every story cites its requirement ids** (`P-DOC-1…5`, `BR-020…023`, `U-SEC-1/2` — ranges and
  slash-lists are understood).

### 6 · Parity check — verify the rebuild actually uses the whole model

The clone step guarantees *every active field is documented*; step 3 guarantees *every as-is
field is mapped* in `DATA-MODEL.md`. Neither guarantees the **rebuilt code reads or writes it**.
That last hop is where fields silently disappear: a column survives the export, the docs, the
mapping and the migrated schema, but the reconstruction wires only a subset — so the feature is
"lost" even though the data is right there. (Seen in practice: a whole group of foreign keys
and their lookup tables existed in the migrated DB, but the module's types/repository/UI never
touched them.)

Run the parity check against the rebuilt app **whenever a module is reported done**, and again
before cutover:

```bash
python3 scripts/parity_check.py \
  --schema <app>/supabase/migrations \   # or a DATA-MODEL DDL file, or {"tables": {...}} JSON
  --app    <app>/src \
  --out    <workdir>/levelup
```

Dependency-free, read-only. It writes `parity-report.md` / `.json` listing **orphan tables**
(a schema table whose name never appears in code) and **orphan columns** (split into
high-confidence composite names and low-signal short names to verify by hand). Structural
columns (`id`, `organization_id`, timestamps, `bubble_id`, `deleted_at`) are ignored. A
column/table counts as referenced when its exact snake_case identifier appears anywhere in the
source (DB names surface in query strings even when the app uses camelCase variables).

For every orphan, record a verdict — this is the gate:
- **Used** elsewhere (view / generated type / RPC) → note where; not a miss.
- **Deferred** on purpose → add a BACKLOG story with the reason (so it is tracked, not lost).
- **Forgotten** → wire the types/repository/UI now.

Never let an orphan pass silently: an unclassified orphan is a candidate lost feature. Record
the run (coverage %, and the classified orphan list) in `ASSESSMENT.md` or a `PARITY.md` note.

## Quality bar

- Every assessment claim cites evidence from the clone docs/inventory.
- Security/reliability decisions are never traded for UX or speed — if a trade-off is forced,
  it is written down in RISKS.md with the user's explicit sign-off required.
- The migration plan accounts for **every** table and file field in DATA-MODEL.md's mapping.
- PRD-v2 keeps full traceability to BR-xxx rules so parity is verifiable after the rebuild.
- FRONTEND-DESIGN.md uses tokens **extracted from the export**, not invented, and is written to be
  run through Claude Design before UI work starts.
- ASSESSMENT.md states whether the `enterprise-best-practices` gates were applied (which layers/
  themes), or that they were skipped and why (step 0b).
- EXECUTION-CONTRACT.md exists and its completeness gate references the clone's PARITY-MATRIX —
  the executor has no path to "done" that skips documented scope.
- `spec_coverage.py --strict-acceptance` **passes** before delivery: every requirement has a story
  that implements it, no story is orphan or undecomposed, every behavioural requirement is
  testable. A pack that fails this gate is not delivered.
- After a module is rebuilt, `scripts/parity_check.py` was run and **every** orphan table/column
  it reports is classified (used / deferred-with-reason / fixed) — no silent drops between the
  DATA-MODEL and the running code (step 6).
