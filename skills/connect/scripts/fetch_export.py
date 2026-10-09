#!/usr/bin/env python3
"""Download a fresh .bubble export through the connected mode and keep an immutable copy.

    python3 fetch_export.py --app <app-id> [--version test|<branch>] [--profile <profile>] [--keep N]

Runs `cli context detect --force` for the profile, confirms that a REAL export download happened
(when the download fails the MCP falls back to an editor crawl and still answers ok — with the old
export, if any, left in place), then copies the export to
~/.unbubble/mcp/exports/<app>/<version>-<UTC timestamp>.bubble (0600) with a `.meta.json` sidecar:
app, version, fetch time, sha256 of the bytes Bubble sent and of the saved file. bubble_audit.py
shows that provenance in the report header. Prints a short JSON summary; never the CLI output.

stdlib only, Python 3.8+.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402


def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def downloaded_attempt(result):
    for attempt in (result or {}).get('attempts') or []:
        if isinstance(attempt, dict) and attempt.get('source') == 'downloaded_bubble' and attempt.get('ok'):
            return attempt
    return None


def failure_reasons(result):
    reasons = []
    for attempt in (result or {}).get('attempts') or []:
        if isinstance(attempt, dict) and not attempt.get('ok'):
            reason = attempt.get('reason') or ''
            status = attempt.get('status')
            reasons.append('%s%s: %s' % (attempt.get('source'), ' (HTTP %s)' % status if status else '', reason))
    return reasons


def prune(folder, version, keep):
    """With --keep N, drop the oldest exports of THIS version beyond N; other versions and older
    rounds of other versions are never touched. keep 0 (default) keeps everything: each audit round
    may need its own export again."""
    if keep <= 0:
        return []
    own = re.compile(r'^%s-\d{8}-\d{6}\.bubble$' % re.escape(version))  # not "test-x-…" of a branch "test-x"
    exports = sorted((path for path in folder.glob('*.bubble') if own.match(path.name)),
                     key=lambda path: path.stat().st_mtime)
    removed = []
    for old in exports[:-keep]:
        old.unlink()
        meta = old.with_name(old.name + '.meta.json')
        if meta.exists():
            meta.unlink()
        removed.append(old.name)
    return removed


def main():
    ap = argparse.ArgumentParser(description='Download a fresh .bubble export through the connected mode.')
    ap.add_argument('--app', required=True, help='Bubble app id')
    ap.add_argument('--version', default='test', help="'test' or a branch id (never live)")
    ap.add_argument('--profile', default='', help='MCP profile (default: the app id; branch profiles: <app>--<branch>)')
    ap.add_argument('--keep', type=int, default=0,
                    help='keep only the newest N exports of this version (default 0: keep all)')
    args = ap.parse_args()
    _mcp.check_id(args.app, 'app id')
    _mcp.check_id(args.version, 'version')
    if args.profile:
        _mcp.check_id(args.profile, 'profile')
    if args.version.strip().lower() in ('live', 'production', 'prod', 'main', 'version-live'):
        raise SystemExit('exports are taken from version-test or a branch: that is what the audit cleans and '
                         'the rebuild documents (live is only what the owner last deployed)')
    profile = args.profile or args.app

    code, result, stderr = _mcp.run_cli(['context', 'detect', '--profile', profile, '--app-id', args.app,
                                         '--app-version', args.version, '--force'], timeout=3600)
    attempt = downloaded_attempt(result)
    if code != 0 or attempt is None:
        print(json.dumps({'ok': False, 'app': args.app, 'version': args.version,
                          'error': 'no fresh export was downloaded (the context, if any, came from another source)',
                          'reasons': failure_reasons(result)[:6] or ([stderr[-400:]] if stderr else []),
                          'hint': 'Free-plan apps cannot export (HTTP 401); an expired session needs '
                                  '`launch.py cli session login` again.'}, indent=1))
        return 1
    source = Path(attempt['path'])
    meta = _mcp.load_json(source.with_name(source.name + '.meta.json'), {}) or {}
    if str(meta.get('app_version') or attempt.get('app_version') or '') != args.version:
        print(json.dumps({'ok': False, 'error': 'downloaded export reports version %r, expected %r'
                          % (meta.get('app_version'), args.version)}, indent=1))
        return 1

    folder = Path(_mcp.mcp_paths()['home']) / 'exports' / _mcp.safe_name(args.app)
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(str(folder), 0o700)
    target = folder / ('%s-%s.bubble' % (_mcp.safe_name(args.version), _mcp.stamp()))
    shutil.copyfile(str(source), str(target))
    os.chmod(str(target), 0o600)
    provenance = {
        'app_id': args.app,
        'app_version': args.version,
        'profile': profile,
        'fetched_at': meta.get('fetched_at') or _mcp.now_iso(),
        'sha256': meta.get('sha256'),  # of the bytes Bubble sent
        'saved_sha256': sha256_file(target),  # of this file (the MCP re-serializes and may hydrate)
        'bytes': meta.get('bytes') or attempt.get('bytes'),
        'source': 'bubble.io/appeditor/export',
    }
    _mcp.write_private_json(target.with_name(target.name + '.meta.json'), provenance)
    removed = prune(folder, _mcp.safe_name(args.version), args.keep)
    print(json.dumps({'ok': True, 'export': str(target), **{k: provenance[k] for k in
                      ('app_id', 'app_version', 'fetched_at', 'sha256', 'bytes')},
                      **({'pruned': removed} if removed else {})}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
