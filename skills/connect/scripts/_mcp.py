"""Shared helpers for the unbubble:connect scripts.

The scripts drive the vendored befree-bubble-mcp CLI through mcp/launch.py (allowlisted
subcommands only), parse its JSON in-process and print only summaries — raw CLI output (log rows,
context metadata) never reaches the terminal or a transcript.

stdlib only, Python 3.8+.
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Everything these scripts write (exports, captures, plans, journals) is owner-only.
os.umask(0o077)


def repo_root():
    """The UnBubble checkout: found from this file's real path, because some hosts (Codex) link only
    the skill folder into their skills directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'mcp' / 'launch.py').exists():
            return parent
    raise SystemExit('UnBubble checkout not found from %s (expected mcp/launch.py above it)' % here)


def launcher():
    return repo_root() / 'mcp' / 'launch.py'


SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


def check_id(value, what='app id'):
    """App ids, branch ids and profile names become path segments: plain identifiers only."""
    text = str(value or '').strip()
    if not SAFE_ID.match(text) or '..' in text:
        raise SystemExit('invalid %s %r: letters, digits, dot, dash and underscore only' % (what, value))
    return text


def projects_dir():
    return Path(os.environ.get('UNBUBBLE_PROJECTS') or '~/UnBubble-Projects').expanduser()


def project_dir(app):
    return projects_dir() / check_id(app)


def mcp_paths():
    proc = subprocess.run([sys.executable, str(launcher()), 'paths'], capture_output=True, text=True, timeout=60)
    return json.loads(proc.stdout)


def _parse_json(text):
    text = (text or '').strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        start = text.find('\n{')
        if start >= 0:
            try:
                return json.loads(text[start + 1:])
            except ValueError:
                return None
    return None


SECRET_PATTERNS = (  # order matters: whole header values first, then single values
    re.compile(r'(?i)(bearer\s+)([A-Za-z0-9._~+/=-]{8,})'),
    re.compile(r'(?i)((?:authorization|(?:set-)?cookie)["\']?\s*[:=]\s*["\']?)([^\r\n"\']+)'),
    re.compile(r'(?i)((?:token|secret|password|api[_-]?key|private[_-]?key|session[_-]?id)'
               r'["\']?\s*[:=]\s*["\']?)([^\s"\',;}]+)'),
)


def redact(text):
    """Mask credential-looking values in free text (CLI stderr tails kept in reports)."""
    text = str(text or '')
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + '[REDACTED]', text)
    return text


def run_cli(args, timeout=1800):
    """Run `mcp/launch.py cli <args>`; returns (returncode, parsed JSON or None, redacted stderr tail)."""
    try:
        proc = subprocess.run([sys.executable, str(launcher()), 'cli'] + [str(a) for a in args],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, None, 'timed out after %d s' % timeout
    return proc.returncode, _parse_json(proc.stdout), redact((proc.stderr or '').strip()[-2000:])


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')


def private_dir(path):
    """mkdir -p where every folder this creates is owner-only (existing folders are left as they are)."""
    path = Path(path)
    missing = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    for folder in reversed(missing):
        folder.mkdir(mode=0o700)
    return path


def write_private_text(path, text):
    """Atomic write readable by the owner only: project folders hold app names, screen texts and
    screenshots of the test database."""
    path = Path(path)
    private_dir(path.parent)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(text)
    try:
        os.chmod(str(tmp), 0o600)
    except OSError:
        pass
    os.replace(str(tmp), str(path))


def write_private_json(path, payload):
    write_private_text(path, json.dumps(payload, indent=1, ensure_ascii=False) + '\n')


def load_json(path, default=None):
    try:
        with open(str(path), encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def normalize_text(value):
    """Case-, accent- and whitespace-insensitive form used to compare screen content."""
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', text).strip().lower()


def safe_name(value):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(value or '')).strip('._') or 'item'
