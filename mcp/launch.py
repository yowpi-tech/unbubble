#!/usr/bin/env python3
"""Run the vendored befree-bubble-mcp (UnBubble edition) with a safe environment.

    python3 mcp/launch.py serve          # stdio MCP server — the command agent hosts register
    python3 mcp/launch.py cli <args...>  # allowlisted CLI: login, export download, logs, captures
    python3 mcp/launch.py doctor [--json]

Every run uses the private venv created by mcp/install.py, the vendored source (no package build),
a private config folder, umask 077, a neutral empty working directory, and remote/egress features
off. State lives in ~/.unbubble/mcp (override with UNBUBBLE_MCP_HOME):

    venv/     Python >= 3.11 with the hash-pinned dependencies (mcp/requirements.lock)
    config/   BUBBLE_MCP_CONFIG_DIR: profiles, sessions, browser profiles, cached exports (0700)
    exports/  immutable copies of downloaded exports, one per audit round (0600)
    work/     the server's working directory (kept empty)
    pycache/  bytecode, so nothing is written next to the vendored source

stdlib only, Python 3.8+.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
REPO = MCP_DIR.parent
VENDOR = MCP_DIR / 'befree-bubble-mcp'
SRC = VENDOR / 'src'
SERVER_NAME = 'befree-bubble-mcp'


def unbubble_home():
    return Path(os.environ.get('UNBUBBLE_MCP_HOME') or '~/.unbubble/mcp').expanduser()


HOME = unbubble_home()
VENV = HOME / 'venv'
CONFIG = HOME / 'config'
EXPORTS = HOME / 'exports'
WORK = HOME / 'work'
PYCACHE = HOME / 'pycache'

# CLI subcommands an agent may run through this launcher (None = any subcommand). Writes, deploys,
# plugin installs, extension packs, transfers and HTML/Figma imports are refused here and, again,
# by the vendored CLI and the write guard underneath.
CLI_ALLOW = {
    ('session', 'login'), ('session', 'list'), ('session', 'inspect'),
    ('profile', 'add'), ('profile', 'list'), ('profile', 'status'),
    ('context', 'detect'), ('context', 'inspect-bubble'), ('context', 'summary'),
    ('metrics', None), ('changelog', 'fetch'),
    ('branch', 'list'), ('branch', 'contributors'),
    ('readiness', None),
    ('eval', 'capture-app-session'), ('eval', 'capture-bubble-visual'), ('eval', 'capture-visual'),
}
DROPPED_ENV = (
    'BUBBLE_CLI_WEBHOOK_URL', 'BUBBLE_CLI_WEBHOOK_ENVELOPE_MODE', 'BUBBLE_CLI_RENDER_ENDPOINT',
    'BUBBLE_CLI_NL_AI', 'OPENAI_API_KEY', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT',
    'PYTHONUSERBASE',
)


def venv_python():
    return VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in DROPPED_ENV}
    env.update({
        'BUBBLE_MCP_CONFIG_DIR': str(CONFIG),
        'PYTHONPATH': str(SRC),  # replaces, never appends: only the vendored code is importable
        'PYTHONPYCACHEPREFIX': str(PYCACHE),
        'PYTHONNOUSERSITE': '1',
        'PYTHONSAFEPATH': '1',  # the working directory is never put on sys.path
        'BUBBLE_MCP_KNOWLEDGE_REMOTE': '0',
        'BUBBLE_CLI_DISCOVERY_CACHE': '0',
    })
    return env


def require_install():
    python = venv_python()
    if not python.exists():
        sys.stderr.write('UnBubble connected mode is not installed (no venv at %s).\n'
                         'Run: python3 %s\n' % (VENV, MCP_DIR / 'install.py'))
        sys.exit(1)
    if not (SRC / 'bubble_mcp' / '__init__.py').exists():
        sys.stderr.write('Vendored source missing at %s. Run: python3 %s\n' % (SRC, MCP_DIR / 'sync_vendor.py'))
        sys.exit(1)
    return python


def run(module, args):
    python = require_install()
    for folder in (HOME, CONFIG, EXPORTS, WORK):
        private_dir(folder)
    PYCACHE.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    os.chdir(str(WORK))
    argv = [str(python), '-m', module] + list(args)
    if os.name == 'nt':  # no exec on Windows: keep stdio attached through a child
        sys.exit(subprocess.call(argv, env=child_env()))
    os.execve(str(python), argv, child_env())


# Top-level CLI commands that take a subcommand (the vendored cli/main.py subparsers).
TWO_LEVEL = {'profile', 'session', 'context', 'metrics', 'changelog', 'branch', 'eval', 'browser', 'transfer',
             'plugin', 'extension', 'tool-wizard', 'import', 'skill', 'language', 'framework', 'learning',
             'knowledge', 'tools', 'smoke'}


def cli_path(args):
    words = [a for a in args if not a.startswith('-')]
    command = words[0] if words else ''
    sub = words[1] if command in TWO_LEVEL and len(words) > 1 else None
    return command, sub


def cli_allowed(args):
    command, sub = cli_path(args)
    return (command, sub) in CLI_ALLOW or (command, None) in CLI_ALLOW


# ------------------------------------------------------------------ doctor

def _probe(python, code):
    proc = subprocess.run([str(python), '-c', code], env=child_env(), cwd=str(private_dir(WORK)),
                          capture_output=True, text=True, timeout=120)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def _registered_hosts():
    hosts = {}
    claude = Path('~/.claude.json').expanduser()
    try:
        data = json.loads(claude.read_text(encoding='utf-8'))
        servers = data.get('mcpServers') or {}
        entry = servers.get(SERVER_NAME)
        hosts['claude-code'] = bool(entry) and str(MCP_DIR / 'launch.py') in ' '.join(entry.get('args') or [])
    except (OSError, ValueError, AttributeError):
        hosts['claude-code'] = False
    codex = Path(os.environ.get('CODEX_HOME') or '~/.codex').expanduser() / 'config.toml'
    try:
        hosts['codex'] = '[mcp_servers.%s]' % SERVER_NAME in codex.read_text(encoding='utf-8')
    except OSError:
        hosts['codex'] = False
    cursor = Path('~/.cursor/mcp.json').expanduser()
    try:
        hosts['cursor'] = SERVER_NAME in (json.loads(cursor.read_text(encoding='utf-8')).get('mcpServers') or {})
    except (OSError, ValueError, AttributeError):
        hosts['cursor'] = False
    return hosts


def _profiles():
    try:
        settings = json.loads((CONFIG / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    out = []
    for name, profile in sorted((settings.get('profiles') or {}).items()):
        session = CONFIG / 'sessions' / (''.join(c if c.isalnum() or c in '-_' else '_' for c in name) + '.json')
        out.append({
            'name': name,
            'app_id': profile.get('app_id'),
            'app_version': profile.get('app_version'),
            'session_profile': profile.get('session_profile'),
            'session_captured': session.exists(),  # existence only: the content is never read
        })
    return out


def doctor(as_json=False):
    report = {'home': str(HOME), 'vendored': None, 'checks': []}

    def check(name, ok, detail=''):
        report['checks'].append({'name': name, 'ok': bool(ok), 'detail': detail})

    manifest = MCP_DIR / 'VENDORED.json'
    try:
        vend = json.loads(manifest.read_text(encoding='utf-8'))
        report['vendored'] = {'commit': vend['source']['commit'], 'ref': vend['source']['ref'],
                              'files': vend['file_count']}
        check('vendored source', (SRC / 'bubble_mcp').exists(), vend['source']['commit'][:12])
    except (OSError, ValueError, KeyError):
        check('vendored source', False, 'run python3 mcp/sync_vendor.py')
    python = venv_python()
    check('venv', python.exists(), str(VENV))
    if python.exists():
        ok, out = _probe(python, 'import sys; print("%d.%d.%d" % sys.version_info[:3])')
        version_ok = ok and tuple(int(x) for x in out.split('.')[:2]) >= (3, 11)
        check('python >= 3.11', version_ok, out)
        ok, out = _probe(python, 'import bubble_mcp, requests, bs4, playwright; print(bubble_mcp.__file__)')
        check('vendored package importable', ok and out.startswith(str(SRC)), out.splitlines()[-1] if out else '')
        ok, out = _probe(python, 'from playwright.sync_api import sync_playwright\n'
                                 'import os\np = sync_playwright().start()\n'
                                 'path = p.chromium.executable_path\np.stop()\n'
                                 'print(path if os.path.exists(path) else "missing: " + path)')
        check('playwright chromium', ok and not out.startswith('missing'), out.splitlines()[-1] if out else '')
    check('config folder private', CONFIG.exists() and (CONFIG.stat().st_mode & 0o077) == 0, str(CONFIG))
    report['hosts'] = _registered_hosts()
    report['profiles'] = _profiles()
    report['ok'] = all(c['ok'] for c in report['checks'])
    if as_json:
        print(json.dumps(report, indent=1))
        return 0 if report['ok'] else 1
    for c in report['checks']:
        print('%s %-28s %s' % ('✓' if c['ok'] else '✗', c['name'], c['detail']))
    print('  registered in: %s' % (', '.join(h for h, on in report['hosts'].items() if on) or 'no host yet'))
    for profile in report['profiles']:
        print('  profile %-28s app=%s version=%s session=%s'
              % (profile['name'], profile['app_id'], profile['app_version'] or 'test',
                 'yes' if profile['session_captured'] else 'no'))
    if not report['ok']:
        print('next: python3 %s' % (MCP_DIR / 'install.py'))
    elif not report['profiles']:
        print('next: python3 %s cli profile add <app-id> --app-id <app-id>' % (MCP_DIR / 'launch.py'))
        print('      python3 %s cli session login --profile <app-id> --app-id <app-id>' % (MCP_DIR / 'launch.py'))
    return 0 if report['ok'] else 1


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    if command == 'serve':
        run('bubble_mcp.server.stdio', [])
    if command == 'cli':
        if not rest or rest[0] in ('-h', '--help'):
            print('allowed: ' + ', '.join(sorted(' '.join(filter(None, item)) for item in CLI_ALLOW)))
            return 0
        if not cli_allowed(rest):
            sys.stderr.write('`%s` is not available through the UnBubble launcher (allowed: login, profiles, '
                             'export download, logs/metrics, changelog, branch list, readiness, captures).\n'
                             % ' '.join(filter(None, cli_path(rest))))
            return 2
        run('bubble_mcp.cli.main', rest)
    if command == 'doctor':
        return doctor(as_json='--json' in rest)
    if command == 'paths':
        print(json.dumps({'home': str(HOME), 'venv': str(VENV), 'config': str(CONFIG), 'exports': str(EXPORTS),
                          'work': str(WORK), 'src': str(SRC), 'launcher': str(Path(__file__).resolve())}, indent=1))
        return 0
    sys.stderr.write('unknown command %r (serve | cli | doctor | paths)\n' % command)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
