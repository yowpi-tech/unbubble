#!/usr/bin/env python3
"""Install UnBubble's connected mode (the vendored befree-bubble-mcp, UnBubble edition).

    python3 mcp/install.py                       # venv + dependencies + Chromium + private folders
    python3 mcp/install.py --register claude     # ...and register the MCP server in Claude Code
    python3 mcp/install.py --register all|codex|cursor|none|ask

What it does, in order:
  1. creates ~/.unbubble/mcp/venv with Python >= 3.11 (uv when available, preferring 3.12);
  2. installs mcp/requirements.lock with --require-hashes and wheels only (nothing is built from
     source, so no third-party setup code runs) — the vendored package itself is NOT installed:
     mcp/launch.py puts its source on PYTHONPATH;
  3. installs Playwright's Chromium (reuses the shared browser cache when the version matches);
  4. creates the private folders (config/, exports/, work/ with 0700);
  5. registers the server in the agent hosts you choose, backing up each config file first.
It never signs in to Bubble: run `python3 mcp/launch.py cli session login ...` yourself, in a
terminal, in the visible browser window it opens.

stdlib only, Python 3.8+.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MCP_DIR))
import launch  # noqa: E402  (same folder: paths and doctor)

LOCK = MCP_DIR / 'requirements.lock'
LAUNCHER = MCP_DIR / 'launch.py'
SERVER = launch.SERVER_NAME


def say(message):
    print('[unbubble-mcp] ' + message, flush=True)


def run(argv, **kwargs):
    say('$ ' + ' '.join(str(a) for a in argv))
    return subprocess.run([str(a) for a in argv], check=True, **kwargs)


def python_version(python):
    try:
        out = subprocess.run([str(python), '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return tuple(int(x) for x in out.split('.'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def create_venv(recreate):
    venv_python = launch.venv_python()
    if venv_python.exists() and not recreate:
        version = python_version(venv_python)
        if version and version >= (3, 11):
            say('venv already present (%s, Python %d.%d)' % (launch.VENV, version[0], version[1]))
            return venv_python
        say('existing venv is unusable; recreating it')
    if launch.VENV.exists():
        shutil.rmtree(launch.VENV)
    launch.VENV.parent.mkdir(parents=True, exist_ok=True)
    uv = shutil.which('uv')
    if uv:
        for wanted in ('3.12', '3.13', '3.11'):
            try:
                run([uv, 'venv', '--python', wanted, '--seed', launch.VENV])
                return venv_python
            except subprocess.CalledProcessError:
                continue
    for candidate in ('python3.12', 'python3.13', 'python3.11', 'python3'):
        path = shutil.which(candidate)
        version = python_version(path) if path else None
        if version and version >= (3, 11):
            run([path, '-m', 'venv', launch.VENV])
            return venv_python
    raise SystemExit('No Python >= 3.11 found. Install one (for example `uv python install 3.12`) and retry.')


def install_dependencies(venv_python):
    uv = shutil.which('uv')
    if uv:
        run([uv, 'pip', 'install', '--python', venv_python, '--require-hashes', '--no-build',
             '-r', LOCK])
    else:
        run([venv_python, '-m', 'pip', 'install', '--require-hashes', '--only-binary', ':all:',
             '--no-deps', '-r', LOCK])
    run([venv_python, '-m', 'playwright', 'install', 'chromium'], env=launch.child_env())


def make_folders():
    for folder in (launch.HOME, launch.CONFIG, launch.EXPORTS, launch.WORK):
        launch.private_dir(folder)
    launch.PYCACHE.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ host registration

def server_command():
    # A stable interpreter path (Homebrew's sys.executable is versioned and moves on upgrades); the
    # launcher itself only needs Python 3.8+ and execs the venv's interpreter.
    return [shutil.which('python3') or sys.executable, str(LAUNCHER), 'serve']


def backup(path):
    if path.exists():
        copy = path.with_name(path.name + '.unbubble-backup-' + time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(path, copy)
        os.chmod(copy, 0o600)
        say('backup: %s' % copy)


def register_claude():
    claude = shutil.which('claude')
    if not claude:
        say('Claude Code CLI not found; add it later with:')
        print('  claude mcp add --scope user %s -- %s' % (SERVER, ' '.join(server_command())))
        return False
    backup(Path('~/.claude.json').expanduser())
    subprocess.run([claude, 'mcp', 'remove', '--scope', 'user', SERVER], capture_output=True)
    run([claude, 'mcp', 'add', '--scope', 'user', SERVER, '--'] + server_command())
    return True


def register_codex():
    codex = shutil.which('codex')
    if codex:
        config = Path(os.environ.get('CODEX_HOME') or '~/.codex').expanduser() / 'config.toml'
        backup(config)
        subprocess.run([codex, 'mcp', 'remove', SERVER], capture_output=True)
        run([codex, 'mcp', 'add', SERVER, '--'] + server_command())
        say('Codex: raise tool_timeout_sec for %s in config.toml if long exports time out (default 60 s).'
            % SERVER)
        return True
    say('Codex CLI not found; add this to ~/.codex/config.toml:')
    print('  [mcp_servers.%s]\n  command = %s\n  args = %s\n  tool_timeout_sec = 600'
          % (SERVER, json.dumps(server_command()[0]), json.dumps(server_command()[1:])))
    return False


def register_cursor():
    path = Path('~/.cursor/mcp.json').expanduser()
    if not path.parent.exists():
        say('Cursor not found (~/.cursor missing); skipped.')
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except ValueError:
        raise SystemExit('%s is not valid JSON; fix it or add the server by hand.' % path)
    backup(path)
    servers = data.setdefault('mcpServers', {})
    command = server_command()
    servers[SERVER] = {'command': command[0], 'args': command[1:]}
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    say('Cursor: registered in %s (Cursor limits the number of MCP tools; the catalog is large).' % path)
    return True


REGISTRARS = {'claude': register_claude, 'codex': register_codex, 'cursor': register_cursor}


def detected_hosts():
    found = []
    if shutil.which('claude') or Path('~/.claude').expanduser().exists():
        found.append('claude')
    if shutil.which('codex') or Path('~/.codex').expanduser().exists():
        found.append('codex')
    if Path('~/.cursor').expanduser().exists():
        found.append('cursor')
    return found


def register(choice):
    if choice == 'none':
        return
    hosts = detected_hosts() if choice in ('all', 'ask') else [choice]
    for host in hosts:
        if choice == 'ask':
            if not sys.stdin.isatty():
                say('not a terminal: skipping registration (rerun with --register %s)' % host)
                continue
            answer = input('Register the %s MCP server in %s? [y/N] ' % (SERVER, host)).strip().lower()
            if answer not in ('y', 'yes', 's', 'sim'):
                continue
        try:
            REGISTRARS[host]()
        except subprocess.CalledProcessError as exc:
            say('%s registration failed (%s); register it by hand with: %s'
                % (host, exc, ' '.join(server_command())))


def main():
    ap = argparse.ArgumentParser(description="Install UnBubble's connected mode (vendored befree-bubble-mcp).")
    ap.add_argument('--register', choices=['ask', 'all', 'claude', 'codex', 'cursor', 'none'], default='ask',
                    help='register the MCP server in agent hosts (default: ask in a terminal)')
    ap.add_argument('--recreate', action='store_true', help='recreate the venv from scratch')
    ap.add_argument('--skip-browser', action='store_true', help='do not install Playwright Chromium')
    args = ap.parse_args()

    check = subprocess.run([sys.executable, str(MCP_DIR / 'sync_vendor.py'), '--check'])
    if check.returncode != 0:
        raise SystemExit('The vendored source does not match mcp/VENDORED.json; resync before installing.')
    venv_python = create_venv(args.recreate)
    if args.skip_browser:
        uv = shutil.which('uv')
        cmd = ([uv, 'pip', 'install', '--python', venv_python, '--require-hashes', '--no-build', '-r', LOCK]
               if uv else [venv_python, '-m', 'pip', 'install', '--require-hashes', '--only-binary', ':all:',
                           '--no-deps', '-r', LOCK])
        run(cmd)
    else:
        install_dependencies(venv_python)
    make_folders()
    register(args.register)
    say('checking the installation (sign in yourself, in a terminal: a browser window opens; use email, not Google):')
    return launch.doctor()


if __name__ == '__main__':
    sys.exit(main())
