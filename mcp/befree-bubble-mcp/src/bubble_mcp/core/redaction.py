"""Utilities for redacting sensitive values from logs and reports."""

from __future__ import annotations

import json
import re
from typing import Any


# `secure` covers Bubble's settings.secure (API Connector private params, plugin keys, Data API
# tokens): the whole subtree is redacted, whatever its inner key names are.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(authorization|bearer|cookie|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|secret|password|private[_-]?key|token|secure)",
    re.IGNORECASE,
)

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}\b"),  # Stripe secret / restricted keys
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS access key ids
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),  # SendGrid
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bBasic\s+[A-Za-z0-9+/=]{12,}", re.IGNORECASE),  # HTTP basic auth
    re.compile(r"\bkey-[0-9a-f]{32}\b"),  # Mailgun
    re.compile(r"\bSK[0-9a-fA-F]{32}\b"),  # Twilio API key sid
]

# Credentials passed in query strings or form bodies (`...?api_key=VALUE&...`): keep the name.
QUERY_SECRET_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|private[_-]?key)=)[^&\s\"']+"
)
JSON_STRING_LIMIT = 2_000_000
PATH_KEYS = ("path_array", "path", "path_parts")
VALUE_KEYS = ("body", "value", "values", "data", "result")


def _path_is_sensitive(value: dict[str, Any]) -> bool:
    for key in PATH_KEYS:
        path = value.get(key)
        parts = path if isinstance(path, list) else str(path).split(".") if isinstance(path, str) else []
        if any(SENSITIVE_KEY_PATTERN.search(str(part)) for part in parts):
            return True
    return False


def redact_string(value: str) -> str:
    """Redact secret-like substrings from a string (JSON text is parsed and redacted structurally)."""

    stripped = value.strip()
    if stripped[:1] in ("{", "[") and len(stripped) <= JSON_STRING_LIMIT:
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            return json.dumps(redact_sensitive(parsed), separators=(",", ":"))
    redacted = value
    for pattern in SENSITIVE_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return QUERY_SECRET_PATTERN.sub(lambda match: match.group(1) + "[REDACTED]", redacted)


def redact_sensitive(value: Any) -> Any:
    """Recursively redact secret-like keys and values."""

    if isinstance(value, dict):
        output: dict[str, Any] = {}
        # A change/value addressed by a path through a sensitive key (e.g. ["settings", "secure", ...])
        # carries that secret in its value, whatever the value's own keys are called.
        path_is_sensitive = _path_is_sensitive(value)
        for key, child in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_PATTERN.search(key_text) or (path_is_sensitive and key_text in VALUE_KEYS):
                output[key_text] = "[REDACTED]"
            else:
                output[key_text] = redact_sensitive(child)
        return output
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return redact_string(value)
    return value
