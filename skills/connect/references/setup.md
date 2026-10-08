# Connected mode — setup

One-time per machine (install + register), once per app (profile + sign-in), and a cleanup at the
end of each client project. `<unbubble>` = the UnBubble checkout (the folder with `mcp/launch.py`).

## Requirements

- Python 3.8+ to run the installer and the scripts. The MCP itself needs Python ≥ 3.11: the
  installer uses `uv` when available (it downloads a managed 3.12) or a system Python ≥ 3.11.
- About 500 MB of disk: the venv (~150 MB) and Playwright's Chromium (~350 MB, reused when the shared cache
  already has the same version).
- A Bubble account that is a **collaborator on the app**. Prefer a dedicated collaborator per
  client: the captured session opens everything that account can open in the Bubble editor.
- A **paid Bubble plan** for export downloads (free-plan apps answer 401). Logs keep only what the
  plan's retention allows. Branches need a plan with version control.

## Install

Ask before installing — it creates a venv, downloads Chromium and edits agent-host config files
(each one backed up first).

```bash
python3 <unbubble>/mcp/install.py                 # asks which hosts to register
python3 <unbubble>/mcp/install.py --register claude   # or: all | codex | cursor | none
```

Steps: venv in `~/.unbubble/mcp/venv` → `mcp/requirements.lock` installed with `--require-hashes`
and wheels only (no package build; the vendored source is put on `PYTHONPATH` by the launcher) →
Chromium → private folders (0700) → host registration → `doctor`. Options: `--recreate` (fresh
venv), `--skip-browser`. State lives in `~/.unbubble/mcp/` (relocate with `UNBUBBLE_MCP_HOME`).

Registration per host (the server is always called `befree-bubble-mcp` and started as
`python3 <unbubble>/mcp/launch.py serve`):

- **Claude Code**: `claude mcp add --scope user …` (all sessions of this user). Restart the session;
  `/mcp` must show `befree-bubble-mcp` connected.
- **Codex**: `codex mcp add …`, or a TOML snippet to paste into `~/.codex/config.toml`. Codex gives a
  tool call 60 s — long operations must go through the scripts.
- **Cursor**: `~/.cursor/mcp.json`. The server exposes ~285 tools; Cursor may refuse that many.
- **Other hosts**: the installer prints the command line to register by hand.

There is deliberately no `.mcp.json` in the repo root (the repo is a plugin root: the server would
start in every session that opens it).

## Check

```bash
python3 <unbubble>/mcp/launch.py doctor          # --json for machine-readable output
python3 <unbubble>/mcp/launch.py paths           # where venv, config, exports and work live
```

`doctor` checks the vendored source (against `mcp/VENDORED.json`), the venv and its Python, that
the server imports from the vendored `src/`, Chromium, private folder modes, host registration, and
lists profiles and whether each has a session (existence only — it never reads session contents).

## Per app: profile and sign-in

The MCP profile name is the app id (e.g. `my-app`).

```bash
python3 <unbubble>/mcp/launch.py cli profile add <app-id> --app-id <app-id> --app-version test
```

**Sign-in is done by the human, in a terminal** (the agent may open the command in the user's
terminal panel, but never types credentials):

```bash
python3 <unbubble>/mcp/launch.py cli session login --profile <app-id> --app-id <app-id>
```

A Chromium window opens on the Bubble editor. Sign in with **email + password** (Google sign-in
refuses automated browsers) and any two-factor code; the window closes as soon as the session is
saved (default limit 10 min, `--wait-seconds`). The browser profile is kept per MCP profile, so the
next login is usually one click. Sessions expire: when a call answers that the session is missing
or expired, ask the user to sign in again — do not retry in a loop.

Then confirm readiness (read-only):

```bash
python3 <unbubble>/mcp/launch.py cli readiness --profile <app-id>
```

or the `bubble_readiness_check` tool. `bubble_profile_status` and `bubble_session_list` report
session metadata with secrets redacted — still, never ask for or show the cookies themselves.

### Branch profiles (for writes)

Writes go to a branch through a profile bound to it, reusing the app's session:

```bash
python3 <unbubble>/mcp/launch.py cli profile add <app-id>--<branch-id> --app-id <app-id> \
    --app-version <branch-id> --session-profile <app-id>
```

How the branch is created and used: `cleanup.md`.

## What the launcher allows

`launch.py cli` runs only: `session login|list|inspect`, `profile add|list|status`,
`context detect|inspect-bubble|summary`, `metrics *`, `changelog fetch`,
`branch list|contributors`, `readiness`, `eval capture-app-session|capture-bubble-visual|capture-visual`.
Everything else (writes, deploys, plugin installs, transfers, imports, plan execution) is refused by
the launcher, again by the vendored CLI, and every HTTP request still passes the write guard. Writes
happen only through MCP tool calls, under the policy and the protocol in `cleanup.md`.

## End of a client project

Ask the owner, then remove the access the machine keeps for that app:

```bash
python3 <unbubble>/mcp/launch.py paths     # confirm the config folder
# in <config>: sessions/<app-id>*.json, browser-profiles/<app-id>*/, app-sessions/<app-id>/,
# app-sessions/rebuild-<app-id>/ — delete them (the user runs the rm; never cat them)
```

Also remove the dedicated Bubble collaborator from the app when the engagement ends.

## Uninstall

```bash
claude mcp remove befree-bubble-mcp --scope user   # and the Codex/Cursor entries, if registered
rm -rf ~/.unbubble/mcp                              # venv, sessions, exports — after the owner agrees
```

## Updating the vendored MCP

Never edit `mcp/befree-bubble-mcp/` in place. Changes land on the yowpi fork (branch
`unbubble/hardening`, synced with upstream, PRs to Befree), then:

```bash
python3 <unbubble>/mcp/sync_vendor.py            # snapshot of the fork's pinned branch → mcp/befree-bubble-mcp
python3 <unbubble>/mcp/sync_vendor.py --check    # the tree matches VENDORED.json byte for byte
python3 <unbubble>/mcp/install.py --register none # refresh the venv if requirements.lock changed
```

Commit as `mcp: vendor befree-bubble-mcp @ <sha>` after the fork's full test suite passes.
