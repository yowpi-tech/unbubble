"""Tool policy for every agent-facing entry point (UnBubble edition).

The stdio server, the MCP skill runner and the framework program runner reach tools through
:func:`guarded_call_tool`; ``tools/list`` is answered with :func:`visible_tool_schemas`. The policy
complements the transport guard in ``core/write_guard.py`` (which stops deploys, live writes and
cross-app writes at the HTTP layer) with rules that need the tool name and the caller's arguments:

* tools that deploy, write raw editor payloads, install plugins, take session cookies as arguments,
  run extension packs, or build INTO Bubble from HTML/Figma are not offered and not callable;
* tools that are not part of the base catalog (for example extension-pack tools) are refused;
* a non-read-only tool never accepts a caller-supplied ``payload``/``write_payload`` — every
  legacy tool would otherwise post it verbatim;
* ``execute=true`` needs an explicit, non-live ``app_version`` from the caller (profile defaults do
  not count) and destructive tools additionally need ``confirm=true``;
* ``bubble_execute_plan`` refuses plans whose steps already carry write payloads.

Direct Python callers of :func:`bubble_mcp.server.tools.call_tool` (the unit tests) are not agents
and are not filtered here; the transport guard still applies to them.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any, Callable

from bubble_mcp.core.config import SAFE_PROFILE_NAME, get_config_dir, load_settings, resolve_profile
from bubble_mcp.core.write_guard import is_live_version
from bubble_mcp.execution.executor_types import extract_write_payload
from bubble_mcp.server.policy_state import agent_call
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool
from bubble_mcp.sessions.store import load_session


class ToolCallBlocked(PermissionError):
    """Raised when an agent-facing call is refused by the UnBubble tool policy."""


DENIED_TOOL_NAMES = frozenset(
    {
        # deploys (test -> live)
        "bubble_schedule_deploy",
        "bubble_list_scheduled_deploys",
        "bubble_cancel_scheduled_deploy",
        "bubble_deploy_history",
        # raw editor writes and multi-command bypasses
        "bubble_editor_write",
        "batch",
        "natural",
        # plugin installs
        "bubble_plugin_install",
        # session cookies as tool arguments end up in the conversation
        "bubble_session_import",
        # building INTO Bubble from HTML/Figma: their render runtimes are not shipped
        "create_from_html",
        "create_styles_from_html",
        "sync_figma_component",
        "sync_component",
        "sync_figma_style",
        "sync_figma_tokens",
        "upload_asset",
    }
)
DENIED_TOOL_PREFIXES = (
    "bubble_extension_",  # extension packs and the capture companion
    "bubble_tool_wizard_",  # generates write tools from captured editor traffic
    "bubble_transfer_",  # copies objects between (client) apps
)

RAW_PAYLOAD_ARGS = ("write_payload", "payload")

# Flags handlers read with bool(...): a string like "no" would be truthy there, so only real JSON
# booleans are accepted.
BOOLEAN_FLAG_ARGS = ("execute", "confirm", "dry_run", "approve_execution", "approved", "headless", "cleanup")

# Composite tools whose execute mode writes to Bubble on their own (write smoke, visual repairs).
NO_EXECUTE_TOOLS = frozenset({"bubble_runtime_smoke", "bubble_visual_audit"})

# Tools whose target version is named by their own arguments (branch name / version ids).
VERSION_FROM_OWN_ARGS = frozenset(
    {
        "bubble_branch_create",
        "bubble_branch_delete",
        "bubble_branch_merge_start",
        "bubble_branch_merge_confirm",
        "bubble_branch_merge_resolve_conflicts",
        "bubble_branch_merge_finalize",
    }
)


def is_tool_denied(name: str) -> bool:
    return name in DENIED_TOOL_NAMES or name.startswith(DENIED_TOOL_PREFIXES)


@lru_cache(maxsize=1)
def _base_tool_index() -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool for tool in list_tool_schemas(include_extensions=False)}


def visible_tool_schemas() -> list[dict[str, Any]]:
    """The tool list an agent sees: the base catalog minus denied tools (no extension tools)."""

    return [tool for tool in _base_tool_index().values() if not is_tool_denied(tool["name"])]


def _is_read_only(name: str) -> bool:
    annotations = _base_tool_index().get(name, {}).get("annotations") or {}
    return annotations.get("readOnlyHint") is True


def _is_destructive(name: str) -> bool:
    return (
        name.startswith(("delete_", "clear_", "remove_"))
        or name.endswith("_permanently")
        or name == "bubble_branch_delete"
    )


def check_tool_call(name: str, arguments: dict[str, Any] | None) -> None:
    """Raise :class:`ToolCallBlocked` when the agent-facing call breaks the policy.

    ``arguments`` must be the caller's own arguments, before profile defaults are merged.
    """

    args = arguments or {}
    if is_tool_denied(name):
        raise ToolCallBlocked(f"{name} is disabled in the UnBubble edition of the Bubble MCP.")
    if name not in _base_tool_index():
        raise ToolCallBlocked(f"{name} is not a tool of the reviewed base catalog; it cannot be called.")
    for flag in dict.fromkeys([*BOOLEAN_FLAG_ARGS, *_boolean_schema_args(name)]):
        if flag in args and not isinstance(args[flag], bool):
            raise ToolCallBlocked(f"{name}: {flag} must be a JSON boolean (true/false), not {args[flag]!r}.")
    _check_paths(name, args)
    _check_profile_names(name, args)
    _check_app_matches_profile(name, args)
    if name in NO_EXECUTE_TOOLS and args.get("execute") is True:
        raise ToolCallBlocked(f"{name} with execute=true writes to Bubble on its own and is disabled.")
    if name in {"bubble_session_login", "bubble_profile_add", "bubble_project_bootstrap"}:
        _check_profile_binding(name, args)
    read_only = _is_read_only(name)
    if not read_only:
        raw = [key for key in RAW_PAYLOAD_ARGS if key in args]
        if raw:
            raise ToolCallBlocked(
                f"{name} does not accept a caller-supplied {raw[0]}: raw editor payloads are refused. "
                "Use the tool's own arguments."
            )
    if name == "bubble_execute_plan":
        _check_plan(args.get("plan"))
    if args.get("execute") is True and not read_only:
        version = str(args.get("app_version") or "").strip()
        if name not in VERSION_FROM_OWN_ARGS and not version:
            raise ToolCallBlocked(
                f"{name} with execute=true needs an explicit app_version ('test' or a branch); the "
                "profile default is not used for writes."
            )
        if is_live_version(version):
            raise ToolCallBlocked(f"{name} cannot write to the live version ({version}).")
        if _is_destructive(name) and args.get("confirm") is not True:
            raise ToolCallBlocked(f"{name} is destructive: execute=true also needs confirm=true.")


def _local_path_of(value: str) -> str | None:
    """The filesystem path a string argument names, if any: `file://` URLs, absolute, home- or
    dot-relative paths, and relative paths with a separator. Bare names resolve against the server's
    working directory, which the UnBubble launcher keeps outside the config dir."""

    text = value.strip()
    if not text:
        return None
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        return unquote(parsed.path) or None
    if "://" in text:
        return None
    if text.startswith(("/", "~", "./", "../")) or "/" in text or "\\" in text:
        return text
    return None


# Config subtree the MCP itself hands back to the agent for round trips: framework artifacts. They
# carry no authority — the program runner re-checks every step through this policy, see
# test_framework_artifacts_carry_no_authority. Everything else in the config dir (sessions, app
# sessions, browser profiles, cached exports with settings.secure, MCP skill state and approvals,
# the guard's branch registry, settings) is off limits to tool arguments.
AGENT_ROUND_TRIP_SUBDIRS = ("frameworks",)
MAX_SCANNED_VALUES = 20_000


def _inside_config_dir(path: str) -> bool:
    try:
        config = get_config_dir().expanduser().resolve()
        target = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    if target != config and config not in target.parents:
        return False
    allowed = [config / sub for sub in AGENT_ROUND_TRIP_SUBDIRS]
    return not any(target == root or root in target.parents for root in allowed)


def _check_paths(name: str, value: Any) -> None:
    """No tool argument, however deeply nested, may point into the MCP config dir: it holds the
    sessions, app sessions, exports with settings.secure and the guard's branch registry, which
    tools must neither read back into the conversation nor overwrite."""

    stack = [value]
    seen = 0
    while stack:
        item = stack.pop()
        seen += 1
        if seen > MAX_SCANNED_VALUES:
            raise ToolCallBlocked(f"{name}: arguments are too large to check.")
        if isinstance(item, str):
            path = _local_path_of(item)
            if path is not None and _inside_config_dir(path):
                raise ToolCallBlocked(f"{name}: paths inside the MCP config directory are not accepted ({item}).")
        elif isinstance(item, dict):
            stack.extend(item.values())
            stack.extend(key for key in item if isinstance(key, str))
        elif isinstance(item, (list, tuple)):
            stack.extend(item)


def _boolean_schema_args(name: str) -> list[str]:
    properties = (_base_tool_index().get(name, {}).get("inputSchema") or {}).get("properties") or {}
    flags = []
    for key, spec in properties.items():
        declared = spec.get("type") if isinstance(spec, dict) else None
        if declared == "boolean" or (isinstance(declared, list) and declared == ["boolean"]):
            flags.append(str(key))
    return flags


def _check_profile_binding(name: str, args: dict[str, Any]) -> None:
    """A profile is bound to one app: it cannot be repointed, and its session is only captured in a
    visible browser (a stored, logged-in browser profile must not mint a session for another app)."""

    profile_name = str(args.get("profile") or args.get("name") or "").strip()
    requested_app = str(args.get("app_id") or "").strip()
    if name == "bubble_session_login" and args.get("headless") is True:
        raise ToolCallBlocked("bubble_session_login must open a visible browser (headless=true is refused).")
    if name == "bubble_session_login" and str(args.get("editor_url") or "").strip():
        raise ToolCallBlocked("bubble_session_login derives the editor URL from the profile's app; editor_url is refused.")
    if not profile_name:
        return
    try:
        configured = resolve_profile(load_settings(), profile_name)
    except (OSError, ValueError):
        configured = None
    if configured is not None and requested_app and requested_app != configured.app_id:
        raise ToolCallBlocked(
            f"{name}: profile '{profile_name}' belongs to app '{configured.app_id}'; create a new profile "
            f"for '{requested_app}' instead of repointing this one."
        )
    if name == "bubble_session_login":
        target_app = requested_app or (configured.app_id if configured else "")
        try:
            existing = load_session(profile_name)
        except (OSError, ValueError):
            existing = None
        if existing is not None and target_app and existing.app_id and existing.app_id != target_app:
            raise ToolCallBlocked(
                f"bubble_session_login: profile '{profile_name}' already holds a session for "
                f"'{existing.app_id}'; use a profile of '{target_app}' instead."
            )


PROFILE_NAME_ARGS = ("profile", "source_profile", "target_profile", "session_profile")
# The MCP's own smokes and recipes pass template placeholders such as "$profile".
TEMPLATE_PLACEHOLDER = re.compile(r"^\$[A-Za-z_][A-Za-z0-9_]*$")


def _check_profile_names(name: str, args: dict[str, Any]) -> None:
    keys = PROFILE_NAME_ARGS + (("name",) if name == "bubble_profile_add" else ())
    for key in keys:
        value = args.get(key)
        if value is None or value == "":
            continue
        text = str(value).strip()
        if TEMPLATE_PLACEHOLDER.match(text) and args.get("execute") is not True:
            continue  # previews/routing only; an executing call needs a real profile name
        if not SAFE_PROFILE_NAME.match(text) or ".." in text:
            raise ToolCallBlocked(f"{name}: {key} must be a plain profile name (letters, digits, . _ -), got {value!r}.")


def _check_app_matches_profile(name: str, args: dict[str, Any]) -> None:
    """With a configured profile, the tool works on that profile's app: an app_id/appname argument
    naming another app (with the same account session) is refused."""

    profile_name = str(args.get("profile") or "").strip()
    if not profile_name:
        return
    try:
        configured = resolve_profile(load_settings(), profile_name)
    except (OSError, ValueError):
        return
    if configured is None:
        return
    for key in ("app_id", "appname"):
        requested = str(args.get(key) or "").strip()
        if requested and requested not in {configured.app_id, configured.appname}:
            raise ToolCallBlocked(
                f"{name}: profile '{profile_name}' belongs to app '{configured.app_id}'; {key}='{requested}' "
                "names another app. Use (or create) a profile of that app instead."
            )


def _check_plan(plan: Any) -> None:
    steps = plan.get("steps") if isinstance(plan, dict) else None
    if not isinstance(steps, list):
        return
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        if extract_write_payload(step) is not None:
            raise ToolCallBlocked(
                f"bubble_execute_plan step {index + 1} carries a write payload; raw payload steps are "
                "refused. Pass abstract steps with compile_missing=true instead."
            )
        tool = str(step.get("tool_name") or step.get("tool") or "")
        if tool and is_tool_denied(tool):
            raise ToolCallBlocked(f"bubble_execute_plan step {index + 1} uses {tool}, which is disabled.")


def guarded_call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Agent-facing entry point: apply the policy, then dispatch (nested calls are checked too)."""

    with agent_call():
        check_tool_call(name, arguments)
        return call_tool(name, arguments, cancelled=cancelled, progress=progress)
