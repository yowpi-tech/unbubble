# UnBubble

A 3-step pipeline to take an app **off Bubble.io** with an engineering upgrade.

| Step | Skill | Input | Output |
|---|---|---|---|
| 1 | `unbubble:audit` | `.bubble` export | Interactive HTML report of unused/dead entities (10 areas) + deletion tracker → owner cleans the app in the Bubble editor and **re-exports a lean `.bubble`** |
| 2 | `unbubble:clone` | lean `.bubble` | As-is technical docs (database, external APIs, plugins, Data API, backend workflows, pages & business rules) + **PRD-clone** (feature-parity spec) + **`secrets/.env` + `ENV-KEYS.md`** (every API key/credential from the export preserved for the rebuild — values never enter docs or chat) |
| 3 | `unbubble:level-up` | clone docs + PRD | Assessment, target architecture (security & reliability first, UX second), new data model + mapping, **Bubble→new-system migration plan** (CSV vs Data API), PRD v2, backlog — an AI-ready rebuild pack |

Each skill is standalone (own scripts/references), but they chain: audit → clean → re-export →
clone → level-up → rebuild.

All artifacts of a given app live in **one project folder** — `~/UnBubble-Projects/<app-id>/`
(`audit/`, `inventory/`, `secrets/`, `docs/` + `PRD-clone.md`, `levelup/`) — created by
whichever skill touches the app first. Project inputs (spreadsheets, exports) never go into
this repo, and `secrets/.env` never leaves the machine.

Scripts are dependency-free Python 3.8+ (stdlib only). The canonical `.bubble` export reference
model lives in `skills/audit/references/reference-model.md`.
