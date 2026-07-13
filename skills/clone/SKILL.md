---
name: clone
description: >
  Reverse-engineer a Bubble.io app export (a .bubble file) into complete AS-IS technical
  documentation plus a PRD to recreate the system as a functional clone. Covers: DATABASE
  (tables, fields, relationships, option sets, privacy rules), EXTERNAL APIs (API Connector
  providers, endpoints, auth, which are in use), PLUGINS (purpose, which hold API keys, which
  external service each talks to), DATA API exposure (which tables/methods are public),
  BACKEND WORKFLOWS (exposed endpoints vs internally-scheduled, the logic of each), and PAGES
  & REUSABLES (what the system does, the business rules implemented in each workflow — the
  as-is state). Use WHENEVER the user hands you a .bubble export and asks to document the app,
  understand it, extract its schema/APIs/logic, or produce a PRD/spec to rebuild or clone it:
  "document this Bubble app", "documentação técnica do app", "o que esse sistema faz", "regras
  de negócio", "clonar o sistema", "PRD para recriar", "reverse engineer", "as-is", "levantar
  requisitos do Bubble". Step 2 of the UnBubble pipeline — ideally run on the LEAN re-export
  produced after cleaning with unbubble:audit; followed by unbubble:level-up (re-architecture
  + migration plan).
---

# UnBubble · clone — as-is documentation + clone PRD

**Pipeline position: step 2 of 3.** Input should ideally be the **lean** `.bubble` re-exported
after the owner deleted the dead entities found by `unbubble:audit` (running on a dirty export
works, but you will document garbage — warn the user if an audit was never done). Output feeds
`unbubble:level-up` (step 3).

The goal of THIS step is **fidelity, not judgment**: document what the system IS and produce a
PRD to recreate it **as a functional clone** (feature parity). Do NOT redesign, modernize, or
criticize the architecture here — that is `level-up`'s job. Record smells you notice in
`08-open-questions.md` as notes for step 3 instead.

**`<workdir>` is the project folder** `~/UnBubble-Projects/<app-id>/` (same folder the audit
uses; create it if this is the first step run for the app). Everything this skill emits lives
there: `inventory/`, `docs/`, `PRD-clone.md`.

## Workflow

### 1 · Extract the inventory (deterministic)

```bash
python3 scripts/bubble_inventory.py "path/to/export.bubble" --outdir <workdir>/inventory
```

Dependency-free (Python 3.8+). Emits nine JSON files and prints a summary. Read
`summary.json` first — it has counts and **security flags** (endpoints without auth,
endpoints ignoring privacy rules) you must surface in the docs.

| File | Contents |
|---|---|
| `summary.json` | app domain, counts, security flags |
| `database.json` | data types → fields (type, list-ness, reference target), privacy rules per role, Data-API exposure; `relationships` edge list |
| `option_sets.json` | every option set with options (display + db_value) |
| `api_connector.json` | providers → calls: name, method, URL (masked), publish_as (action/data), param key names, **used** flag |
| `plugins.json` | installed plugins: name, version, usage count, config/secure **key names only** |
| `data_api.json` | Data/Workflow API global switches + exposed tables |
| `backend_workflows.json` | every backend WF: kind, endpoint name, expose, auth flags, params, action chain (types), schedule graph (`schedules_workflows` / `scheduled_by`) |
| `pages.json` | per page: title, content type, element census, workflows (trigger + editor-name label + action types), reusables/plugins/API calls used, nav targets |
| `reusables.json` | same census per reusable + `placed_instances` |

For export semantics (what ids mean, how references work, editor names), read
`../audit/references/reference-model.md` — do not re-derive it.

### 2 · Interpret business logic (model work — the part that matters)

The inventory gives structure; **you** extract meaning. The JSONs deliberately contain only
action *types* — for any workflow whose purpose isn't obvious from its trigger + action chain,
open the export itself with targeted python (never `cat` a 100 MB file) and read the action
`properties` to reconstruct the rule in plain language ("when a customer submits an order
above X, notify the account manager and set status to Pending Review").

Prioritize by impact, not page order:
1. **Backend exposed endpoints** (external contract — document every one: params, what it does,
   who calls it).
2. **Database trigger events + recurring events** (invisible automation — the rules nobody
   remembers).
3. The **top pages by workflow_count** and any page whose `content_type` is a core table.
4. Reusables placed on many pages (shared behavior).

For a big app (300+ pages), work in batches and consider subagents (one per module/folder);
group pages into functional modules by name prefix + nav graph (`navigates_to`) before writing.

### 3 · Write the documentation set

Write to `<workdir>/docs/`. Every file starts with a one-paragraph summary. Use tables, use
mermaid for diagrams, cite the source (`pages.json`, page name, workflow trigger) so claims
are checkable. English or the user's language — ask if unclear, default to the language the
user is speaking.

```
docs/
  00-overview.md            what the system is, actors/roles, functional modules, key flows
  01-database.md            per table: purpose, fields table, relationships (mermaid erDiagram),
                            option sets used, privacy rules, Data-API exposure
  02-external-apis.md       per provider: what it's for, auth type, calls table (method, URL,
                            used?), which workflows/pages invoke it
  03-plugins.md             per plugin: purpose, external service, holds API keys? (key NAMES),
                            where used, marketplace link
  04-data-api.md            switches, exposed tables, what privacy rules imply for each,
                            security notes (from summary.security_flags)
  05-backend-workflows.md   endpoints (external contract) vs internal jobs; per WF: trigger,
                            params, logic in plain language, schedule graph
  06-pages-and-reusables.md per module then per page: purpose, content type, key elements,
                            workflows → business rules; reusables and where they're placed
  07-business-rules.md      cross-cutting rules extracted from all of the above, numbered
                            (BR-001 …) so the PRD can reference them
  08-open-questions.md      ambiguities, suspected dead logic, smells noted for level-up,
                            anything requiring the owner's confirmation
```

### 4 · Generate the clone PRD

Write `<workdir>/PRD-clone.md`. This is the **first PRD** — recreate the system as-is on a new
platform. Structure:

1. **Purpose & scope** — what the clone must do; explicit non-goals (no redesign yet).
2. **Actors & permissions** — roles derived from privacy rules + page auth patterns.
3. **Functional requirements** — per module, referencing BR-xxx business rules; every exposed
   endpoint and Data-API table is a requirement (external consumers may exist).
4. **Data model** — the as-is schema (tables/fields/option sets) as the contract to reproduce.
5. **Integrations** — every external API + plugin-service the clone must reconnect (with the
   key NAMES that will need new credentials).
6. **Parity checklist** — a testable list: pages/flows, endpoints, automations (DB triggers,
   recurring), reports/exports.
7. **Out of scope / deferred to level-up** — architecture choices, migration, UX changes.

### Secrets & PII hygiene (non-negotiable)

`settings.secure` holds LIVE API keys and `raw_data` on endpoints can hold real user data. The
inventory script already redacts these — **never** open those export sections to "complete"
the docs with actual values, and never paste any credential-looking string into the docs. Key
NAMES yes, values never. Treat the inventory dir + docs as internal material.

## Quality bar

- Every active table and field appears in `01-database.md`; every provider call in
  `02-external-apis.md` (marked used/unused); every exposed endpoint in `05-…` with params.
- Workflows are described as **rules in plain language**, not action-type lists.
- Anything you could not determine is in `08-open-questions.md` — no silent gaps.
- Numbers in `00-overview.md` match `summary.json` exactly.
- Finish by telling the user the docs + PRD-clone are the input for **`unbubble:level-up`**.
