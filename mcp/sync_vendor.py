#!/usr/bin/env python3
"""Vendor a curated snapshot of the befree-bubble-mcp fork into mcp/befree-bubble-mcp/.

    python3 mcp/sync_vendor.py                       # snapshot the fork's unbubble/hardening branch
    python3 mcp/sync_vendor.py --ref <sha|branch>    # snapshot another commit
    python3 mcp/sync_vendor.py --check               # verify the vendored tree against its manifest

The snapshot is an exact `git archive` of ONE commit of the fork (yowpi-tech/befree-bubble-mcp,
checked out locally) minus the paths in EXCLUDE. Nothing is ever edited here: every change goes to
the fork, passes its test suite, and comes back through a new sync. The manifest (VENDORED.json)
records the commit and a sha256 per file so --check can prove the tree was not touched.

stdlib only, Python 3.8+.
"""
import argparse
import fnmatch
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
VENDOR_DIR = MCP_DIR / 'befree-bubble-mcp'
MANIFEST = MCP_DIR / 'VENDORED.json'
NOTES = MCP_DIR / 'VENDORED.md'
DEFAULT_FORK = Path('~/befree-bubble-mcp').expanduser()
DEFAULT_REF = 'unbubble/hardening'
UPSTREAM = 'https://github.com/pedrobefree/befree-bubble-mcp'

# path prefix / glob -> why it is not shipped
EXCLUDE = {
    'bridge/': 'Figma bridge (builds INTO Bubble; listened on 0.0.0.0 and wrote by default)',
    'chrome-extension/': 'Chrome capture extension (trusted every page script on *.bubbleapps.io)',
    'test-node/': 'Node tests of the excluded bridge/extension',
    'tests/': 'test suite: it runs in the fork, against the same commit',
    'scripts/': 'developer scripts (install_local.py re-signs binaries; audits run in the fork)',
    'docs/superpowers/': 'agent-directed planning docs',
    '.github/': 'upstream CI configuration',
    'package.json': 'npm scripts for the excluded bridge/renderer',
    'package-lock.json': 'npm lockfile for the excluded bridge/renderer',
    'src/bubble_mcp/aria_runtime/package.json': 'puppeteer for the HTML renderer',
    'src/bubble_mcp/aria_runtime/package-lock.json': 'puppeteer for the HTML renderer',
    'src/bubble_mcp/aria_runtime/scripts/*.mjs': 'Node renderers (render_server listened on 0.0.0.0)',
}


def excluded(path):
    for pattern in EXCLUDE:
        if pattern.endswith('/'):
            if path == pattern[:-1] or path.startswith(pattern):
                return True
        elif fnmatch.fnmatch(path, pattern):
            return True
    return False


def git(fork, *args):
    return subprocess.run(['git', '-C', str(fork), *args], check=True, capture_output=True).stdout


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def vendored_files():
    out = {}
    for path in sorted(VENDOR_DIR.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            out[path.relative_to(VENDOR_DIR).as_posix()] = path
    return out


def git_ignored(paths):
    """Vendored paths that the repository's .gitignore rules (including the fork's own nested
    .gitignore) would leave out of a commit: they would exist locally and be missing elsewhere."""

    repo = MCP_DIR.parent
    rels = [(VENDOR_DIR / p).relative_to(repo).as_posix() for p in paths]
    if not rels:
        return []
    proc = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '--stdin'],
                          input='\n'.join(rels).encode(), capture_output=True)
    return sorted(line for line in proc.stdout.decode().splitlines() if line.strip())


def safe_member(member):
    name = member.name
    if name.startswith('/') or '..' in Path(name).parts:
        raise SystemExit('refusing unsafe archive member: %s' % name)
    return member.isfile() or member.isdir()


def sync(fork, ref):
    if not (fork / '.git').exists():
        raise SystemExit('fork checkout not found: %s' % fork)
    sha = git(fork, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    committed = git(fork, 'log', '-1', '--format=%cI', sha).decode().strip()
    try:
        origin = git(fork, 'remote', 'get-url', 'origin').decode().strip()
    except subprocess.CalledProcessError:
        origin = ''
    archive = git(fork, 'archive', '--format=tar', sha)

    tmp = MCP_DIR / ('.befree-bubble-mcp.tmp-%d' % os.getpid())
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    files, skipped, total = {}, 0, 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
        for member in tar.getmembers():
            if member.name in ('pax_global_header',) or member.type == tarfile.XGLTYPE:
                continue
            if not safe_member(member):
                skipped += 1  # symlinks and special files are not shipped
                continue
            rel = member.name.rstrip('/')
            if excluded(rel) or (member.isdir() and excluded(rel + '/')):
                continue
            target = tmp / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = tar.extractfile(member).read()
            target.write_bytes(data)
            if member.mode & 0o111:
                target.chmod(0o755)
            files[rel] = hashlib.sha256(data).hexdigest()
            total += len(data)

    if VENDOR_DIR.exists():
        shutil.rmtree(VENDOR_DIR)
    tmp.rename(VENDOR_DIR)
    manifest = {
        'source': {'repository': origin, 'upstream': UPSTREAM, 'ref': ref, 'commit': sha,
                   'commit_date': committed},
        'synced_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'excluded': EXCLUDE,
        'file_count': len(files),
        'total_bytes': total,
        'files': files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    write_notes(manifest)
    ignored = git_ignored(files)
    if ignored:
        print('ERROR: %d vendored file(s) are git-ignored and would be missing from the commit:' % len(ignored))
        for rel in ignored[:20]:
            print('  ' + rel)
        return 1
    print('vendored %s @ %s: %d files, %.1f MB (%d special entries skipped)'
          % (ref, sha[:12], len(files), total / 1e6, skipped))
    return 0


def write_notes(manifest):
    src = manifest['source']
    lines = [
        '# Vendored: befree-bubble-mcp (UnBubble edition)',
        '',
        'Generated by `mcp/sync_vendor.py` — do not edit by hand.',
        '',
        '| | |',
        '|---|---|',
        '| Upstream | %s (MIT, Copyright (c) 2026 Befree) |' % src['upstream'],
        '| Fork | %s |' % (src['repository'] or 'local checkout'),
        '| Ref | `%s` |' % src['ref'],
        '| Commit | `%s` (%s) |' % (src['commit'], src['commit_date']),
        '| Synced | %s |' % manifest['synced_at'],
        '| Files | %d (%.1f MB) |' % (manifest['file_count'], manifest['total_bytes'] / 1e6),
        '',
        '## Rules',
        '',
        '- **No local edits.** Every change is made in the fork, passes its test suite there',
        '  (`tests/unit`, run with an isolated `BUBBLE_MCP_CONFIG_DIR`), and arrives here through',
        '  `python3 mcp/sync_vendor.py --ref <commit>`.',
        '- `python3 mcp/sync_vendor.py --check` must pass before every commit that touches `mcp/`.',
        '- The license of the vendored code is MIT; keep `befree-bubble-mcp/LICENSE` and the',
        '  third-party section of the repository NOTICE.',
        '',
        '## Not shipped',
        '',
        '| Path | Why |',
        '|---|---|',
    ]
    lines += ['| `%s` | %s |' % (path, why) for path, why in manifest['excluded'].items()]
    NOTES.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def check():
    if not MANIFEST.exists():
        print('no manifest: run python3 mcp/sync_vendor.py first')
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    expected = manifest['files']
    present = vendored_files()
    missing = sorted(set(expected) - set(present))
    extra = sorted(set(present) - set(expected))
    changed = sorted(rel for rel in set(expected) & set(present) if sha256_file(present[rel]) != expected[rel])
    leaked = sorted(rel for rel in present if excluded(rel))
    ignored = git_ignored(present)
    ok = not (missing or extra or changed or leaked or ignored)
    print('%s: %d files, commit %s'
          % ('ok' if ok else 'DRIFT', len(present), manifest['source']['commit'][:12]))
    for label, items in (('missing', missing), ('added', extra), ('modified', changed),
                         ('excluded but present', leaked), ('git-ignored', ignored)):
        for rel in items[:20]:
            print('  %s: %s' % (label, rel))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description='Vendor a curated snapshot of the befree-bubble-mcp fork.')
    ap.add_argument('--fork', type=Path, default=DEFAULT_FORK, help='local checkout of the fork')
    ap.add_argument('--ref', default=DEFAULT_REF, help='commit or branch to snapshot')
    ap.add_argument('--check', action='store_true', help='verify the vendored tree against VENDORED.json')
    args = ap.parse_args()
    return check() if args.check else sync(args.fork.expanduser(), args.ref)


if __name__ == '__main__':
    sys.exit(main())
