# mcp/ — connected mode (optional)

UnBubble's core pipeline works on a `.bubble` export, offline, with Python 3.8+ stdlib only. This
folder adds an **optional** connected mode: an MCP server and CLI that talk to the Bubble editor of
an app you are migrating — download exports, read server logs, workload and the changelog, apply
an audited cleanup on a branch, capture what each screen shows (also logged in, with a test user).

It is a vendored, hardened snapshot of [befree-bubble-mcp](https://github.com/pedrobefree/befree-bubble-mcp)
by Befree (MIT), taken from the fork yowpi-tech/befree-bubble-mcp. See `VENDORED.md` for the exact
commit, what is not shipped and why.

## Files

| File | What it is |
|---|---|
| `befree-bubble-mcp/` | the vendored source — never edited here (see `VENDORED.md`) |
| `VENDORED.json` / `VENDORED.md` | manifest (commit, sha256 per file) and its human summary |
| `sync_vendor.py` | refreshes the snapshot from the fork; `--check` proves the tree is untouched |
| `requirements.in` / `requirements.lock` | runtime dependencies, pinned with hashes |
| `install.py` | private venv, dependencies (hash-checked, wheels only), Chromium, folders, host registration |
| `launch.py` | the one entry point: `serve` (MCP stdio), `cli` (allowlisted), `doctor` |

## Install

```bash
python3 mcp/install.py                    # venv + dependencies + Chromium + private folders
python3 mcp/install.py --register claude  # also register the MCP server in Claude Code (user scope)
python3 mcp/launch.py doctor              # check everything (--json: what the UnBubble console shows)
```

`doctor` also lists the profiles with whether each has a session and when it was saved (file metadata
only — it never reads session contents), the test-user roles captured for screen captures, the
exports downloaded per app (from their provenance sidecars), and whether the shared Bubble sign-in
exists.

All profiles sign in through one shared browser profile (`config/browser-profiles/default`), so one
Bubble sign-in serves every app (`profile add --browser-profile <name>` keeps a client apart). A
browser already signed in to Bubble — an earlier befree-bubble-mcp install, another profile — becomes
the shared one with `python3 mcp/launch.py import-browser-profile`, which the user runs in a terminal
(it copies session material; without a terminal it refuses). `cli profile remove <name>` drops a
profile (for example a deleted branch's) and leaves session files alone; `cli eval save-http-auth`
stores, from a terminal prompt, the password of a protected test version for screen captures.

Then, once per app, **in a terminal** (a browser window opens; sign in with email, not Google):

```bash
python3 mcp/launch.py cli profile add <app-id> --app-id <app-id>
python3 mcp/launch.py cli session login --profile <app-id> --app-id <app-id>
```

Other hosts: `--register codex` uses `codex mcp add`; `--register cursor` edits `~/.cursor/mcp.json`;
any other MCP host can run `python3 <repo>/mcp/launch.py serve` as a stdio server.

## What the edition guarantees

Enforced in code, not configuration (details in the fork's `core/write_guard.py` and
`server/policy.py`):

- no deploys to live, no writes to the live version, no writes into an app other than the one the
  session was captured for, no deleting branches the MCP did not create;
- no raw editor payloads, extension packs, plugin installs, transfers or HTML/Figma builders;
- writes need an explicit `app_version` (`test` or a branch), destructive tools also `confirm=true`;
- logged-in captures are refused on the live version (page-load workflows run as the user);
- settings.secure and common token formats are redacted from tool results; files are private.

These hold for an agent that reaches Bubble through the MCP tools. An agent with unrestricted shell
access can still read or edit `~/.unbubble/mcp` — restrict that in your host's permissions.

## State on disk

`~/.unbubble/mcp/` (override with `UNBUBBLE_MCP_HOME`): `venv/`, `config/` (sessions, browser
profiles, cached exports — 0700), `exports/` (one immutable export per audit round), `work/` (the
server's empty working directory), `pycache/`. Delete `config/browser-profiles/` and `config/sessions/`
at the end of a project, and sign out of Bubble to invalidate the cookies.
