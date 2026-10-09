"""Configuration loading for local Bubble MCP profiles."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "bubble-mcp"
SETTINGS_FILENAME = "settings.json"


@dataclass(frozen=True)
class BubbleProfile:
    """A configured Bubble app profile."""

    name: str
    app_id: str
    appname: str
    editor_url: str | None = None
    app_version: str | None = None
    app_json_path: str | None = None
    consolelog_json_path: str | None = None
    context_path: str | None = None
    crawler_index_path: str | None = None
    # Reuse another profile's captured session (same app, same account). A branch gets its own
    # profile -- and so its own export/context caches -- without a second login or a copy of the
    # cookies on disk.
    session_profile: str | None = None
    # UnBubble edition: a browser profile of its own (e.g. a dedicated collaborator per client)
    # instead of the shared one every profile signs in with.
    browser_profile: str | None = None


@dataclass(frozen=True)
class BubbleMcpSettings:
    """Parsed Bubble MCP settings."""

    config_dir: Path
    default_profile: str | None
    profiles: dict[str, BubbleProfile]


def normalize_profile_name(value: str | None) -> str:
    """Normalize profile identifiers for tolerant matching."""

    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


SAFE_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def browser_profile_dir(profile: str, config_dir: Path | None = None) -> Path:
    """The persistent browser profile of a Bubble MCP profile. Names are plain identifiers: a name
    like `x/../other` must not reach another profile's logged-in browser data."""

    name = str(profile or "").strip()
    if not SAFE_PROFILE_NAME.match(name) or ".." in name:
        raise ValueError(f"Invalid profile name for a browser profile: {profile!r}")
    return (config_dir or get_config_dir()) / "browser-profiles" / name


SHARED_BROWSER_PROFILE = "default"


def resolve_browser_profile_dir(profile: str, config_dir: Path | None = None) -> Path:
    """UnBubble edition: the browser profile that holds the Bubble sign-in of an MCP profile.

    Bubble signs in an account, not an app, so every profile shares one browser profile — sign in
    (or import a signed-in profile) once and every app's session capture reuses it. A profile may
    name its own (`browser_profile`, e.g. a dedicated collaborator per client); a branch profile
    follows the profile whose session it reuses; a per-profile folder created before the shared
    one existed keeps working until the shared one is there.
    """

    base = config_dir or get_config_dir()
    name = str(profile or "").strip()
    browser_profile_dir(name, base)  # validates the name
    try:
        profiles = load_settings(base).profiles
    except Exception:
        profiles = {}
    seen: set[str] = set()
    while name in profiles and name not in seen:
        seen.add(name)
        entry = profiles[name]
        if entry.browser_profile:
            return browser_profile_dir(entry.browser_profile, base)
        if not entry.session_profile:
            break
        name = entry.session_profile
    shared = browser_profile_dir(SHARED_BROWSER_PROFILE, base)
    own = browser_profile_dir(name, base)
    if not shared.exists() and own.exists():
        return own
    return shared


def get_config_dir() -> Path:
    """Return the configured local config directory."""

    configured = os.environ.get("BUBBLE_MCP_CONFIG_DIR", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_DIR


def get_settings_path(config_dir: Path | None = None) -> Path:
    """Return the settings path for a config directory."""

    return (config_dir or get_config_dir()) / SETTINGS_FILENAME


def resolve_config_artifact_path(config_dir: Path, raw_path: str | None) -> Path | None:
    """Resolve a configured artifact path relative to its settings directory."""

    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else config_dir / path


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk, returning an empty object when absent."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def load_settings(config_dir: Path | None = None) -> BubbleMcpSettings:
    """Load settings and profile files from the local config directory."""

    resolved_dir = config_dir or get_config_dir()
    payload = load_json_file(get_settings_path(resolved_dir))
    raw_profiles = payload.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raw_profiles = {}

    profiles: dict[str, BubbleProfile] = {}
    for name, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, dict):
            continue
        app_id = str(raw_profile.get("app_id") or raw_profile.get("appname") or "").strip()
        appname = str(raw_profile.get("appname") or app_id).strip()
        if not app_id:
            continue
        profile_name = str(name).strip()
        profiles[profile_name] = BubbleProfile(
            name=profile_name,
            app_id=app_id,
            appname=appname,
            editor_url=str(raw_profile.get("editor_url") or "").strip() or None,
            app_version=str(raw_profile.get("app_version") or raw_profile.get("appVersion") or "").strip()
            or None,
            app_json_path=str(raw_profile.get("app_json_path") or "").strip() or None,
            consolelog_json_path=str(raw_profile.get("consolelog_json_path") or "").strip() or None,
            context_path=str(raw_profile.get("context_path") or "").strip() or None,
            crawler_index_path=str(raw_profile.get("crawler_index_path") or "").strip() or None,
            session_profile=str(raw_profile.get("session_profile") or "").strip() or None,
            browser_profile=str(raw_profile.get("browser_profile") or "").strip() or None,
        )

    default_profile = str(payload.get("default_profile") or "").strip() or None
    return BubbleMcpSettings(
        config_dir=resolved_dir,
        default_profile=default_profile,
        profiles=profiles,
    )


def save_settings(settings: BubbleMcpSettings) -> None:
    """Persist settings to disk."""

    settings.config_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_profile": settings.default_profile,
        "profiles": {
            name: {
                "app_id": profile.app_id,
                "appname": profile.appname,
                **({"editor_url": profile.editor_url} if profile.editor_url else {}),
                **({"app_version": profile.app_version} if profile.app_version else {}),
                **({"app_json_path": profile.app_json_path} if profile.app_json_path else {}),
                **(
                    {"consolelog_json_path": profile.consolelog_json_path}
                    if profile.consolelog_json_path
                    else {}
                ),
                **({"context_path": profile.context_path} if profile.context_path else {}),
                **(
                    {"crawler_index_path": profile.crawler_index_path}
                    if profile.crawler_index_path
                    else {}
                ),
                **({"session_profile": profile.session_profile} if profile.session_profile else {}),
                **({"browser_profile": profile.browser_profile} if profile.browser_profile else {}),
            }
            for name, profile in sorted(settings.profiles.items())
        },
    }
    get_settings_path(settings.config_dir).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_profile(settings: BubbleMcpSettings, profile_name: str | None = None) -> BubbleProfile | None:
    """Resolve a profile by exact or tolerant name."""

    requested = profile_name or settings.default_profile
    if not requested:
        return None
    if requested in settings.profiles:
        return settings.profiles[requested]
    target = normalize_profile_name(requested)
    matches = [
        profile
        for name, profile in settings.profiles.items()
        if normalize_profile_name(name) == target
    ]
    return matches[0] if len(matches) == 1 else None


def without_profile(settings: BubbleMcpSettings, name: str) -> BubbleMcpSettings:
    """UnBubble edition: return settings without a profile (its session file is left alone)."""

    profiles = {key: value for key, value in settings.profiles.items() if key != name}
    default_profile = settings.default_profile if settings.default_profile != name else None
    return BubbleMcpSettings(config_dir=settings.config_dir, default_profile=default_profile, profiles=profiles)


def with_profile(settings: BubbleMcpSettings, profile: BubbleProfile) -> BubbleMcpSettings:
    """Return settings with an added or updated profile."""

    profiles = dict(settings.profiles)
    profiles[profile.name] = profile
    default_profile = settings.default_profile or profile.name
    return BubbleMcpSettings(
        config_dir=settings.config_dir,
        default_profile=default_profile,
        profiles=profiles,
    )
