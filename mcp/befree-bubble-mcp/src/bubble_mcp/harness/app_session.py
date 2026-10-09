"""Per-role app sessions for logged-in visual captures (UnBubble edition).

The visual harness renders pages as an anonymous visitor, which leaves out every page behind a
login. Here a human signs in once per role with a TEST user, in a visible browser window, and the
browser's storage state (cookies + localStorage of the app's own origin only) is kept under
``<config>/app-sessions/<app>/<role>.json`` (0600). Captures then reuse it.

Opening an app page runs its page-load workflows as that user, so logged-in captures of a Bubble
app are refused on the live version: only ``version-test`` or a branch preview is allowed.
Rebuilt (non-Bubble) apps are captured the same way with ``target="rebuild"``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import urlparse

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.core.write_guard import WriteBlocked, is_live_version


def _safe(value: str) -> str:
    text = "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in str(value or ""))
    if not text.strip("._"):
        raise ValueError("App and role names are required for app sessions.")
    return text


def app_session_path(app: str, role: str) -> Path:
    return get_config_dir() / "app-sessions" / _safe(app) / f"{_safe(role)}.json"


def is_bubble_app_url(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host.endswith(".bubbleapps.io")


def preview_version(url: str) -> str | None:
    """The version named by a Bubble preview URL (`/version-<v>/...`), or None for the live app."""

    first = (urlparse(str(url or "")).path or "/").lstrip("/").split("/", 1)[0].lower()
    if not first.startswith("version-"):
        return None
    version = first[len("version-"):]
    return None if not version or is_live_version(version) else version


def has_version_segment(url: str) -> bool:
    return preview_version(url) is not None


def ensure_logged_in_capture_allowed(url: str, *, bubble: bool) -> None:
    """Logged-in captures of a Bubble app must target a version-test/branch preview URL."""

    if (bubble or is_bubble_app_url(url)) and not has_version_segment(url):
        raise WriteBlocked(
            "Logged-in captures of a Bubble app run its page-load workflows as the signed-in user, so "
            f"they are refused on the live version ({url}). Use a /version-test/ or branch preview URL."
        )


def filter_storage_state(state: dict[str, Any], url: str) -> dict[str, Any]:
    """Keep only the cookies and localStorage that belong to the captured app's own host."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    origin = f"{parsed.scheme}://{parsed.netloc}"

    def host_matches(domain: str) -> bool:
        domain = str(domain or "").lstrip(".").lower()
        return bool(domain) and (host == domain or host.endswith("." + domain))

    cookies = [cookie for cookie in state.get("cookies") or [] if host_matches(cookie.get("domain", ""))]
    origins = [entry for entry in state.get("origins") or [] if entry.get("origin") == origin]
    return {"cookies": cookies, "origins": origins}


def _write_private(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def save_app_session(app: str, role: str, state: dict[str, Any], *, target: str = "bubble", url: str = "") -> Path:
    """Write the Playwright storage state (as-is, so Playwright can load it) plus a metadata sidecar."""

    path = app_session_path(app, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _write_private(path, state)
    _write_private(path.with_suffix(".meta.json"), {"target": target, "url": url})
    return path


def http_auth_path(app: str) -> Path:
    """HTTP Basic credentials of an app's protected test version (Bubble: Settings > General >
    "Password protect development version"), kept next to the role sessions (0600)."""

    return get_config_dir() / "app-sessions" / _safe(app) / ".http-auth.json"


def save_http_auth(app: str, username: str, password: str, *, origin: str) -> Path:
    """Store the credentials the user typed (never passed through an agent) for `origin` only."""

    if not username or not password:
        raise ValueError("Both the username and the password of the protected version are required.")
    parsed = urlparse(origin)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError(f"Invalid origin for HTTP credentials: {origin!r}")
    path = http_auth_path(app)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    _write_private(path, {"username": username, "password": password, "origin": f"{parsed.scheme}://{parsed.netloc}"})
    return path


def load_http_auth(app: str) -> dict[str, str] | None:
    """Playwright `http_credentials` for an app's protected version, sent to its own origin only."""

    try:
        raw = json.loads(http_auth_path(app).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not raw.get("username") or not raw.get("password") or not raw.get("origin"):
        return None
    return {"username": str(raw["username"]), "password": str(raw["password"]), "origin": str(raw["origin"])}


def resolve_app_session(app: str, role: str) -> tuple[Path, dict[str, Any]]:
    path = app_session_path(app, role)
    if not path.exists():
        raise ValueError(
            f"No app session for app '{app}', role '{role}'. Run `bubble-mcp eval capture-app-session "
            f"--app {app} --role {role} --url <login page>` in a terminal and sign in with a test user."
        )
    try:
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    return path, meta if isinstance(meta, dict) else {}


def capture_app_session(
    *,
    url: str,
    app: str,
    role: str,
    target: str = "bubble",
    wait_for_user: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Open a visible browser on ``url``; the human signs in, then confirms in the terminal."""

    bubble = target != "rebuild"
    ensure_logged_in_capture_allowed(url, bubble=bubble)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on the optional browser extra
        raise RuntimeError("Playwright is required: run UnBubble's mcp/install.py.") from exc

    confirm = wait_for_user or (lambda: input())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            http_credentials = load_http_auth(app)
            # a password-protected test version: the login page only shows with its credentials
            context = browser.new_context(http_credentials=cast(Any, http_credentials)) if http_credentials else browser.new_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            print(
                f"[app-session] Sign in as the TEST user for role '{role}' in the browser window, "
                "then press Enter here. Never use a real user's account.",
                file=sys.stderr,
            )
            confirm()
            final_url = page.url
            state = context.storage_state()
        finally:
            browser.close()
    ensure_logged_in_capture_allowed(final_url, bubble=bubble)
    filtered = filter_storage_state(dict(state), final_url)
    path = save_app_session(app, role, filtered, target="rebuild" if not bubble else "bubble", url=final_url)
    return {
        "ok": bool(filtered["cookies"] or filtered["origins"]),
        "app": app,
        "role": role,
        "target": target,
        "path": str(path),
        "cookies": len(filtered["cookies"]),
        "origins": len(filtered["origins"]),
        "next_user_action": None
        if filtered["cookies"] or filtered["origins"]
        else "No session data for the app's host was found; make sure the login finished on the app itself.",
    }
