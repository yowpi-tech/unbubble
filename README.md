<p align="center">
  <img src="ui/public/brand/unbubble.gif" width="128" height="128" alt="UnBubble — a soap bubble grows, pops and frees the cube that was inside it">
</p>

<h1 align="center">UnBubble</h1>

<p align="center">
  <strong>Take an app off Bubble.io — audited, documented and re-architected — with the coding agent you already use.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"></a>
  <img alt="Python 3.8+ · stdlib-only core" src="https://img.shields.io/badge/python-3.8%2B%20%C2%B7%20stdlib--only%20core-3776AB.svg">
  <img alt="Agent Skills" src="https://img.shields.io/badge/agent%20skills-SKILL.md-8b5cf6.svg">
  <img alt="Works with Claude Code, Codex, Cursor and more" src="https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Cursor%20%C2%B7%20%E2%80%A6-f97316.svg">
</p>

---

## What UnBubble is

UnBubble is an open-source toolkit for migrating an application built on **Bubble.io** to a
conventional codebase, without losing features, data or credentials on the way. It turns the
`.bubble` export of an app into a complete, verifiable rebuild pack in three steps:

1. **Audit** — find every dead entity in the export (pages, reusables, backend workflows, option
   sets, plugins, styles, design tokens, tables, fields, custom events, API Connector calls,
   references to removed plugins, mobile views) so the owner can clean the app and re-export it
   lean. Interactive HTML report with confidence levels, a deletion tracker and a per-section
   sign-off for items the owner decides to keep.
2. **Clone** — reverse-engineer the lean export into as-is technical documentation (database,
   external APIs, plugins, Data API exposure, backend workflows, pages and business rules written
   in verifiable form), a feature-parity PRD, a parity ledger with one row per entity, and a
   `secrets/.env` that preserves every API key the export carries — values never enter docs or
   chat.
3. **Level-up** — assess the tech debt, design the target architecture (information security
   and result reliability first, UX second), redesign the data model with a field-by-field
   mapping, write the Bubble → new-system data-migration plan, and produce PRD v2, a sequenced
   atomic backlog, risks and an execution contract. Two gates keep the rebuild honest:
   `spec_coverage.py` (every requirement has a story) and `parity_check.py` (every migrated
   column is actually used by the new code).

Every step is a **skill**: a `SKILL.md` with the method, plus dependency-free Python scripts that
do the deterministic work on the export. A **local web console** tracks each project through the
three steps. Everything runs on your machine; nothing is uploaded anywhere.

An optional fourth skill, **`connect`**, works on the *live* app instead of a file — logs, workload
and changelog, fresh exports, logged-in screen captures, and the audit cleanup applied on a branch
with the owner's approval — through a hardened MCP server vendored in `mcp/`. The three core steps
never need it ([Connected mode](#connected-mode-optional)).

## Not only for Claude Code

The skills follow the **Agent Skills** convention — a folder with a `SKILL.md` — so any coding
agent that reads that format can run the pipeline. The Python scripts also run on their own, with
no agent at all.

| Host | How the skills are installed | How they show up |
|---|---|---|
| **Claude Code** (Anthropic) | symlink the repo into `~/.claude/skills/unbubble` (auto-loads as the `unbubble` plugin), or `claude --plugin-dir <repo>` | `unbubble:audit`, `unbubble:clone`, `unbubble:level-up` (+ the optional `unbubble:connect`) |
| **Codex** (OpenAI / ChatGPT) | link each skill into `~/.codex/skills/` (`unbubble-audit`, `unbubble-clone`, `unbubble-level-up`; optionally `unbubble-connect`) | `audit`, `clone`, `level-up` (+ `connect`) |
| **Cursor, Gemini CLI / Antigravity, GitHub Copilot CLI, OpenCode, Windsurf** and any other Agent Skills host | link each skill into the host's skills folder or into the shared `~/.agents/skills/` | `audit`, `clone`, `level-up` (+ `connect`) |
| **No agent** | run the scripts from a terminal (see below) | HTML report, JSON inventories, `.env`, coverage reports |

The console's **Install & onboarding** page detects where the skills are installed on the machine,
checks whether each copy is in sync with the repo, and prints the exact install commands per host.

## The pipeline

| Step | Skill | Input | Output |
|---|---|---|---|
| 1 | `audit` | `.bubble` export | Interactive HTML report of unused/dead entities (10 areas) with confidence levels, a deletion tracker and a per-section sign-off (items kept on purpose are recorded and questioned in step 2) → the owner cleans the app in the Bubble editor and **re-exports a lean `.bubble`** |
| 2 | `clone` | lean `.bubble` | As-is docs (database, external APIs, plugins, Data API, backend workflows, pages & business rules) + **PRD-clone** (feature-parity spec) + **PARITY-MATRIX** (one disposition per entity) + **`secrets/.env` + `ENV-KEYS.md`** (every credential preserved for the rebuild) |
| 3 | `level-up` | clone docs + PRD | Assessment, target architecture, frontend design brief, new data model + old→new mapping, **migration plan** (CSV vs Data API, cutover, validation), PRD v2, atomic backlog, risks, execution contract — an AI-ready rebuild pack that passes the `spec_coverage` gate |

The steps chain — audit → clean → re-export → clone → level-up → rebuild — but each skill is
standalone, with its own scripts and references. With the optional connected mode the same chain
reaches into the live app: fresh exports with provenance, runtime evidence on the audit's
candidates, the cleanup applied on a branch, what each user role sees per screen, and the Bubble
side of the cutover.

## What is in the repository

```
skills/
  audit/        SKILL.md · scripts/bubble_audit.py · references/ (export reference model,
                marketplace plugin names and pricing)
  clone/        SKILL.md · scripts/bubble_inventory.py · scripts/bubble_secrets.py
  level-up/     SKILL.md · scripts/spec_coverage.py · scripts/parity_check.py ·
                references/assessment-checklist.md
  connect/      optional connected mode · SKILL.md · references/ (setup, diagnostics, cleanup,
                evidence, screens, cutover) · scripts/ (export download, runtime evidence, cleanup
                plan + journal, screen captures, screen parity)
ui/             the local console (Next.js) — progress per project, embedded reports,
                docs viewer, backlog tracking, install detection and onboarding
mcp/            the connected mode's MCP server: vendored befree-bubble-mcp (MIT, hardened
                UnBubble edition), installer, launcher
.claude-plugin/ plugin manifest for Claude Code
LICENSE · NOTICE
```

`skills/audit/references/reference-model.md` is the canonical description of how a `.bubble`
export stores and references entities — the knowledge the scripts encode.

## Install

Clone the repository and link the skills into the agent(s) you use. Symlinks are recommended: a
`git pull` updates every agent at once.

```bash
git clone https://github.com/yowpi-tech/unbubble.git ~/UnBubble
```

**Claude Code**

```bash
mkdir -p ~/.claude/skills && ln -sfn ~/UnBubble ~/.claude/skills/unbubble
# or, without installing: claude --plugin-dir ~/UnBubble
```

**Codex (ChatGPT)**

```bash
mkdir -p ~/.codex/skills && for s in audit clone level-up; do ln -sfn ~/UnBubble/skills/$s ~/.codex/skills/unbubble-$s; done
ln -sfn ~/UnBubble/skills/connect ~/.codex/skills/unbubble-connect   # optional: connected mode
```

**Other Agent Skills hosts** — same three links into the host's skills folder (for example
`~/.cursor/skills`, `~/.copilot/skills`, `~/.gemini/skills`) or into the shared
`~/.agents/skills`, plus `connect` if you want the connected mode. Check the host's documentation
for the exact folder.

The connected mode also needs its MCP server installed once — see
[Connected mode › Install](#install-1).

## Quick start

1. In the Bubble editor: **Settings → General → Export application**. Keep the `.bubble` file
   wherever you like (Downloads is fine); the skills read it in place and never copy it.
2. Ask your agent to audit it, for example:
   > Audit this Bubble export and tell me what I can delete: ~/Downloads/my-app.bubble
3. Open the report, delete the dead entities in the Bubble editor, tick them off as you go, sign
   each section off, and re-export a lean `.bubble` — or, with the connected mode, let the agent
   apply the deletions on a branch, batch by batch, for your approval.
4. Ask for the clone (as-is docs + PRD-clone) on the lean export, then for the level-up.
5. Follow everything in the console:

```bash
cd ~/UnBubble/ui && npm install && npm run dev     # http://localhost:3333
```

## Project folder

All artifacts of a given app live in **one folder**, created by whichever skill touches the app
first:

```
~/UnBubble-Projects/<app-id>/
  audit/       one report per round + bubble_cleanup_progress__<app>.json (deletions,
               section sign-offs, items kept on purpose); with the connected mode also
               cleanup-applied__<app>.json (deletions applied through it) and
               runtime-evidence__<app>-vN.json (log counts per candidate)
  inventory/   JSON inventories extracted from the export                 (clone)
  secrets/     .env (live keys, chmod 600, gitignored) · .env.example · ENV-KEYS.md
  docs/        00-overview … 08-open-questions                            (clone)
  PRD-clone.md · PARITY-MATRIX.md                                          (clone)
  levelup/     ASSESSMENT · TARGET-ARCHITECTURE · FRONTEND-DESIGN · DATA-MODEL ·
               MIGRATION-PLAN · PRD-v2 · BACKLOG · RISKS · EXECUTION-CONTRACT ·
               spec-coverage · parity-report · screen-parity             (level-up)
  visual/      screens per role, Bubble and rebuilt app             (connected mode)
  unbubble.json  the console's own state (manual overrides, stories done, notes)
```

Project inputs (exports, spreadsheets) never go into this repository, and `secrets/.env` never
leaves the machine.

## Running the scripts without an agent

The core scripts are Python 3.8+ with the standard library only. They never modify the export.
The connected-mode scripts (`skills/connect/scripts/`) are stdlib too, but drive the MCP server
installed by `mcp/install.py`.

```bash
# 1 · audit → interactive HTML report + JSON summary
python3 skills/audit/scripts/bubble_audit.py app.bubble --lang en --out report.html --json results.json

# 2 · clone → inventories and preserved credentials
python3 skills/clone/scripts/bubble_inventory.py app.bubble --outdir inventory
python3 skills/clone/scripts/bubble_secrets.py   app.bubble --outdir secrets

# 3 · level-up gates
python3 skills/level-up/scripts/spec_coverage.py --spec docs/07-business-rules.md --spec levelup/PRD-v2.md \
        --backlog levelup/BACKLOG.md --out levelup --strict-acceptance
python3 skills/level-up/scripts/parity_check.py --schema <app>/supabase/migrations --app <app>/src --out levelup
```

The interpretive parts of the pipeline — reading business rules out of workflows, writing the
docs and the PRDs, designing the target architecture — are what the skills guide an agent
through; the scripts give it deterministic facts to work from.

## Connected mode (optional)

The three core steps work offline on a `.bubble` file and never need this. The fourth skill,
**`connect`**, adds what only the live Bubble editor can answer, through **befree-bubble-mcp** (MIT,
by Befree) vendored in `mcp/` as a hardened *UnBubble edition*:

- **Read-only diagnostics** — server logs, workload units (WU) and what spends them, workflow run
  counts, plan usage, file storage, and the editor changelog ("who changed what, when").
- **Fresh exports** of `version-test` or a branch, each kept as an immutable copy with its
  provenance (version, time, sha256), which the audit report shows in its header.
- **Runtime evidence** for the audit's candidates — is this endpoint, webhook, page or API call
  still used? — as `logs: N×` badges in the report (`bubble_audit.py --evidence`).
- **The audit cleanup applied for you** on a dedicated branch, batch by batch: every batch is
  previewed and approved by the owner, applied, recorded in a journal and verified with a fresh
  export and a new audit round. The owner merges the branch and deploys, by hand.
- **Screens per user role** — public and logged-in pages, captured with test users — as the content
  inventory of every screen, and a **minimum screen-parity gate** for the rebuilt app (content and
  actions only: the new design system rules the visuals).
- **The Bubble side of the cutover** — Data API exposure, 301 redirects, traffic-drain checks.

### Requirements

- Python ≥ 3.11 for the MCP (the installer uses `uv` when available, or a system Python ≥ 3.11) and
  about 500 MB of disk (venv + Chromium).
- A Bubble account that is a **collaborator on the app** — preferably a dedicated one per client.
- A paid Bubble plan to download exports, and a plan with branches for the cleanup on a branch.

### Install

```bash
python3 ~/UnBubble/mcp/install.py --register claude   # or codex | cursor | all | none (it asks by default)
python3 ~/UnBubble/mcp/launch.py doctor
```

The installer creates `~/.unbubble/mcp/venv`, installs the hash-pinned dependencies (wheels only —
the vendored package itself is not installed; the launcher puts its source on the path), downloads
Chromium, creates owner-only folders and registers the MCP server `befree-bubble-mcp` in the hosts
you choose, backing up each config file first. On hosts that link one folder per skill, link the
skill too (see [Install](#install)).

Then, once per app, **in your own terminal** — a browser window opens on the Bubble editor; sign in
with email and password (Google sign-in refuses automated browsers):

```bash
python3 ~/UnBubble/mcp/launch.py cli profile add <app-id> --app-id <app-id> --app-version test
python3 ~/UnBubble/mcp/launch.py cli session login --profile <app-id> --app-id <app-id>
```

### Safety model

The MCP drives Bubble's **undocumented editor endpoints** with the session of a Bubble account, so
the UnBubble edition is built to fail closed:

- **Never live.** A write guard on every HTTP request refuses writes to the live version, the
  deploy endpoints, payloads bound to another app, and deleting a branch the MCP did not create.
  The deploy tools are removed.
- **A policy at the MCP boundary** hides and refuses raw editor writes, `batch`/`natural`, plugin
  installs, extension packs, cross-app transfers, session import, the HTML/Figma builders, the Data
  API token tools and permanent data-type deletion. A write needs `execute: true` and an explicit
  non-live `app_version`; a deletion also `confirm: true`.
- **The launcher** runs only allowlisted CLI commands, in an empty working folder, with umask 077
  and the MCP's remote features off. On top of that, the skill's write protocol adds a dedicated
  branch, a preview and the owner's approval per batch, and verification by a fresh export.
- **Secrets stay out of transcripts.** `settings.secure`, cookies and token formats are redacted
  from tool results and CLI output; sessions live under `~/.unbubble/mcp/config` (owner-only);
  logins are done by a human in a visible browser; logs are reported as counts, never rows.

Use it only with the app owner's consent and never unattended — Bubble can change its editor
endpoints without notice. Details in [`skills/connect/SKILL.md`](skills/connect/SKILL.md) and
[`mcp/README.md`](mcp/README.md).

### What it does not do

Delete reusable-element definitions, backend workflows, plugins or API Connector calls (they stay
on a manual list for the owner); read database records (the migration ETL belongs to the new
system); create savepoints on `test` (only branches isolate writes); export the design to Figma or
code; deploy.

## Local console (`ui/`)

A small Next.js app that reads `~/UnBubble-Projects/` and shows, per project, how far each of the
three steps is: audit rounds and remaining findings (with the report embedded and its deletion
tracker saving straight to the project folder), the clone documentation checklist (docs, PRD,
parity matrix, open questions, preserved credentials), the level-up pack with the coverage and
parity gates, and the backlog stories ticked off as the rebuild lands. It also detects where the
skills are installed and walks a newcomer through a 4-step onboarding. With the connected mode it
shows the MCP installation, the Bubble profiles and whether each has a session (existence and date
only), a "connected" badge per project with its latest downloaded export, and the deletions applied
through it in the audit tracker. English, Portuguese and Spanish, light and dark.

There is no database: everything is derived from the files the skills write, and the console's
only own state is `<project>/unbubble.json`. Details in [`ui/README.md`](ui/README.md).

## Languages

The console ships in **English**, **Português (Brasil)** and **Español**; the language menu in
the header lists whatever is registered, and a first visit follows the browser's
`Accept-Language`. The audit report has its own language switch (`bubble_audit.py --lang pt|en`),
and the skills themselves are written in English but work in whatever language the user speaks.

### How an LLM (or a human) adds a language

These instructions are written so a coding agent can execute them verbatim. Replace `xx` with the
language code (`es`, `fr`, `de`, `it`…).

1. **Create the dictionary.** Copy `ui/src/lib/i18n/locales/en.ts` to
   `ui/src/lib/i18n/locales/xx.ts`. Rename the export to `xx`, type it as `Dictionary`
   (`export const xx: Dictionary = { … }`) and translate **only the values**. Rules:
   - keep every key exactly as it is, in the same order — the type checker fails on a missing or
     unknown key;
   - keep `{placeholders}` such as `{export}`, `{id}`, `{round}` untouched — they are filled at
     runtime;
   - keep product terms untranslated: *audit*, *clone*, *level-up*, *backlog*, *PRD*,
     *PARITY-MATRIX*, *Data API*, *option set*, *backend workflow*, *plugin*, file and folder names,
     command lines and paths;
   - keep the tone of the English source: short, direct, sentence case; UI labels use the
     infinitive or a noun, not an imperative aimed at the reader;
   - `'project.prompt.rebuild_done'` stays an empty string.
2. **Register it.** In `ui/src/lib/i18n/index.ts`, import the dictionary and append one entry to
   `LOCALES`:
   ```ts
   { code: 'xx', label: '<name of the language, in that language>', tag: '<BCP-47 tag>', matches: ['xx'], dictionary: xx },
   ```
   `tag` feeds `<html lang>` and date formatting (`es`, `fr-FR`, `pt-BR`…); `matches` lists the
   `Accept-Language` primary subtags that should select the locale automatically.
3. **Check.** Run `cd ui && npx tsc --noEmit && npx eslint src`. Then start the console, open the
   language menu, pick the new language and skim the dashboard, a project page, the audit page and
   *Install & onboarding* for strings that overflow or read wrong.
4. **Optional — the audit report.** The HTML report is generated by
   `skills/audit/scripts/bubble_audit.py` and carries its own strings in the `STR` dictionary
   (`'pt'` and `'en'` blocks). To add a report language, add a `'xx'` block with the same keys as
   `'en'` and add `'xx'` to the `--lang` choices in `main()`. Regenerate a report with
   `--lang xx` and open it to check.
5. Mention the new language in this chapter and in `ui/README.md`.

Do not translate the skills (`skills/*/SKILL.md`) or the scripts' output files: agents read them
as instructions, and the pipeline's artifacts are written in the language the user is working in.

## Privacy and safety

- The core pipeline runs locally on the export. No telemetry, no uploads, no accounts.
- The `.bubble` export is streamed from where it is; it is never copied into the repo or the
  project folder.
- Credentials found in the export are written once, by script, to `secrets/.env` (chmod 600,
  gitignored). Docs and reports only ever carry variable **names**; the console never reads or
  serves the `.env`.
- The console binds to localhost and has no authentication by design — it is a local tool.
- The optional connected mode talks only to bubble.io (the editor endpoints of the apps you sign in
  to) and, for screen captures, to the app's own pages; the MCP's remote knowledge lookups, webhooks
  and render endpoints are off. Its sessions live in `~/.unbubble/mcp/config` (owner-only) — the
  console checks only whether a session exists and when it was saved — and logs are reported as
  counts, never rows.

## License and attribution

UnBubble is released under the **Apache License 2.0** — see [`LICENSE`](LICENSE).

Copyright © 2026 **Yowpi Tech** and **Marlon Trettin**.

You may use, modify and redistribute it, commercially or not, provided that every copy or
derivative work keeps the [`LICENSE`](LICENSE) and the [`NOTICE`](NOTICE) file — that is, the
attribution to Yowpi Tech and Marlon Trettin as the original authors — and states the changes
you made (Section 4 of the license). A suggested credit line for derivative works:

> Based on UnBubble (https://github.com/yowpi-tech/unbubble), © 2026 Yowpi Tech and Marlon
> Trettin, Apache License 2.0.

Contributions are welcome and are accepted under the same license.

The optional connected mode in `mcp/` vendors **befree-bubble-mcp** by Befree
(https://github.com/pedrobefree/befree-bubble-mcp), MIT License — its license is kept in
`mcp/befree-bubble-mcp/LICENSE` and credited in [`NOTICE`](NOTICE).

## Author

**Marlon Trettin** · [Yowpi Tech](https://yowpi.com) · marlon@yowpi.com
