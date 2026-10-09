"""Fail-closed guard on every request that can change a Bubble app (UnBubble edition).

The MCP drives undocumented Bubble editor endpoints with a captured account session. A captured
session can edit every app the account can reach, so a confused or prompt-injected agent must not
be able to deploy, write to the live version, or write into an app other than the one the session
was captured for. These rules are code, not configuration: no environment variable, settings key
or tool argument turns them off. Previews are refused too, so a blocked change cannot even be
planned as if it were possible.

Every module that sends HTTP to Bubble calls :func:`check_editor_request` (or one of the
``block_*`` helpers) before sending. ``tests/unit/test_write_guard.py`` scans ``src/`` for HTTP
call sites and fails when a new one appears outside the reviewed list.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bubble_mcp.core.config import get_config_dir


class WriteBlocked(PermissionError):
    """Raised when a request would deploy, touch live, or leave the session's app."""


# Version names that mean the production app. Bubble's development version is "test"; branches
# carry their own ids. "main" is treated as live because the preview-URL helpers map it there.
LIVE_VERSIONS = frozenset({"live", "production", "prod", "main"})

# Editor endpoints that only answer questions (or recompute editor-side derived data).
READ_ENDPOINTS = frozenset(
    {
        "/appeditor/calculate_derived",
        "/appeditor/get_plugin_conflicts",
        "/appeditor/notify_ai_app_context_change",
        "/appeditor/load_single_path",
        "/appeditor/load_multiple_paths",
        "/appeditor/get_versions",
        "/appeditor/fetch_contributors_to_branch",
        "/appeditor/fetch_changelog_entries",
        "/appeditor/get_workload_usage_by_date",
        "/appeditor/get_workload_usage_breakdown",
        "/appeditor/get_jetstream_logs",
        "/appeditor/get_current_app_plan_usage",
        "/appeditor/get_workflow_runs",
        "/appeditor/get_storage_size",
        "/appeditor/read_time_series",
    }
)

# Read endpoints whose path continues with app/version segments (context path API).
READ_ENDPOINT_PREFIXES = ("/appeditor/load_single_path/", "/appeditor/load_multiple_paths/")

# Endpoints that change the app, with the payload keys naming the version(s) they change.
# `from_app_version` is a source, not a target, so it is never checked.
WRITE_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "/appeditor/write": ("app_version", "appVersion"),
    "/appeditor/create_new_app_version": ("app_version",),
    "/appeditor/delete_app_version": ("app_version",),
    "/appeditor/sync": ("ours_version_id", "theirs_version_id"),
    "/appeditor/finalize_merge": ("temporary_merge_branch_id", "target_version_id"),
}

# Never allowed, whatever the payload says.
DENIED_ENDPOINTS = frozenset({"/appeditor/deploy_app_test_and_hotfix"})

BUBBLE_HOST_SUFFIXES = (".bubble.io", ".bubble.is", ".bubbleapps.io")


def _endpoint(url: str) -> str:
    """Lower-cased path with repeated slashes collapsed, so `/AppEditor//x` cannot pass as a read."""

    parsed = urlparse(str(url or ""))
    path = (parsed.path or str(url or "")).lower()
    while "//" in path:
        path = path.replace("//", "/")
    return path


def _is_bubble_host(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return host == "bubble.io" or any(host.endswith(suffix) for suffix in BUBBLE_HOST_SUFFIXES)


def _as_dict(payload: Any) -> dict[str, Any]:
    # Callers pass exactly what goes on the wire (the normalized write body, the posted endpoint
    # payload, or the raw request bytes); nothing is unwrapped, so a wrapper cannot hide a target.
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


VERSION_KEYS = (
    "app_version",
    "appVersion",
    "ours_version_id",
    "theirs_version_id",
    "target_version_id",
    "temporary_merge_branch_id",
)
# Endpoints whose payload nests other entries (merge changelogs) that also name versions/apps.
DEEP_SCAN_ENDPOINTS = frozenset({"/appeditor/sync", "/appeditor/finalize_merge"})


def _top_level_values(payload: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    return [str(payload[key]).strip() for key in keys if payload.get(key) is not None and str(payload[key]).strip()]


def _deep_values(value: Any, keys: tuple[str, ...], *, depth: int = 0) -> list[str]:
    found: list[str] = []
    if depth > 6:
        return found
    if isinstance(value, dict):
        found.extend(_top_level_values(value, keys))
        for child in value.values():
            found.extend(_deep_values(child, keys, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.extend(_deep_values(child, keys, depth=depth + 1))
    return found


def is_live_version(version: str | None) -> bool:
    text = str(version or "").strip().strip("/").lower()
    if text.startswith("version-"):
        text = text[len("version-"):]
    return text in LIVE_VERSIONS


def check_editor_request(url: str, payload: Any = None, *, session_app_id: str | None = None) -> str:
    """Raise :class:`WriteBlocked` unless the request is a read, or a write to a non-live
    version of the session's own app. Returns the request kind ("read" or "write")."""

    endpoint = _endpoint(url)
    if not endpoint.startswith("/appeditor/"):
        return "read"  # not an editor endpoint (export downloads go through check_export_download)
    if endpoint in DENIED_ENDPOINTS or "deploy" in endpoint.lower():
        raise WriteBlocked(
            f"{endpoint} is disabled: the UnBubble edition never deploys. Deploy from the Bubble "
            "editor yourself after reviewing the changes."
        )
    if endpoint in READ_ENDPOINTS or endpoint.startswith(READ_ENDPOINT_PREFIXES):
        return "read"
    if endpoint not in WRITE_ENDPOINTS:
        raise WriteBlocked(
            f"{endpoint} is not in the UnBubble guard's endpoint table; unknown editor endpoints are "
            "refused until they are reviewed and added to core/write_guard.py."
        )
    body = _as_dict(payload)
    deep = endpoint in DEEP_SCAN_ENDPOINTS
    versions = (
        _deep_values(body, VERSION_KEYS) if deep else _top_level_values(body, WRITE_ENDPOINTS[endpoint])
    )
    if endpoint == "/appeditor/write" and not versions:
        raise WriteBlocked("/appeditor/write without an explicit app_version is refused.")
    live = [version for version in versions if is_live_version(version)]
    if live:
        raise WriteBlocked(
            f"{endpoint} targets the live version ({live[0]}); writes are only allowed on 'test' or "
            "on a branch."
        )
    appnames = _deep_values(body, ("appname",)) if deep else _top_level_values(body, ("appname",))
    appname = str(body.get("appname") or "").strip()
    bound_app = str(session_app_id or "").strip()
    if bound_app:
        if not appname:
            raise WriteBlocked(f"{endpoint} without an appname is refused; writes name their app.")
        foreign = [name for name in appnames if name != bound_app]
        if foreign:
            raise WriteBlocked(
                f"{endpoint} targets app '{foreign[0]}' but the session belongs to '{bound_app}'; writes "
                "are bound to the app the session was captured for."
            )
    if endpoint == "/appeditor/delete_app_version":
        branch = versions[0] if versions else ""
        if not is_created_branch(appname or bound_app, branch):
            raise WriteBlocked(
                f"Branch '{branch}' was not created through this MCP; only branches it created can be "
                "deleted. Delete other branches in the Bubble editor."
            )
    return "write"


def check_export_download(url: str, *, session_app_id: str | None = None) -> None:
    """Exports are reads, but only from Bubble's own editor host and only for the session's app:
    an export carries settings.secure, so other apps' exports must not land on disk."""

    if not _is_bubble_host(url) or "/appeditor/export/" not in _endpoint(url):
        raise WriteBlocked(f"Refusing to fetch an export from an unexpected URL: {url}")
    bound_app = str(session_app_id or "").strip()
    exported = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    if exported.endswith(".bubble"):
        exported = exported[: -len(".bubble")]
    if bound_app and exported != bound_app:
        raise WriteBlocked(
            f"Refusing to download the export of '{exported}' with a session captured for '{bound_app}'."
        )


def block_asset_upload(url: str = "") -> None:
    """Asset uploads write files into an app's storage; UnBubble never needs them."""

    block_external_write_channel("asset upload", url)


def block_external_write_channel(kind: str, target: str = "") -> None:
    """The Aria runtime can post write payloads to a webhook or a remote renderer. The UnBubble
    edition sends writes only through the guarded editor client, so these channels are closed."""

    suffix = f" ({target})" if target else ""
    raise WriteBlocked(
        f"The {kind} channel is disabled in the UnBubble edition{suffix}; writes go only through the "
        "guarded Bubble editor client."
    )


def block_deploys(action: str = "deploy") -> None:
    raise WriteBlocked(
        f"Scheduled and browser-driven deploys are disabled in the UnBubble edition ({action}). "
        "Deploy from the Bubble editor yourself after reviewing the changes."
    )


# ------------------------------------------------------------------ branches created by this MCP

def _branch_registry_path() -> Path:
    return get_config_dir() / "unbubble-guard" / "branches.json"


def _load_branch_registry() -> dict[str, list[dict[str, Any]]]:
    path = _branch_registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_created_branch(app_id: str, branch: str, response: Any = None) -> None:
    """Remember a branch this MCP created so it may later delete it."""

    app = str(app_id or "").strip()
    name = str(branch or "").strip()
    if not app or not name:
        return
    ids = {name}
    if isinstance(response, dict):
        for key in ("app_version", "version", "id", "version_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                ids.add(value.strip())
    registry = _load_branch_registry()
    entries = [entry for entry in registry.get(app, []) if isinstance(entry, dict)]
    entries.append({"names": sorted(ids), "created_at": datetime.now(timezone.utc).isoformat()})
    registry[app] = entries
    path = _branch_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def is_created_branch(app_id: str, branch: str) -> bool:
    app = str(app_id or "").strip()
    name = str(branch or "").strip()
    if not app or not name or is_live_version(name) or name == "test":
        return False
    for entry in _load_branch_registry().get(app, []):
        if isinstance(entry, dict) and name in (entry.get("names") or []):
            return True
    return False
