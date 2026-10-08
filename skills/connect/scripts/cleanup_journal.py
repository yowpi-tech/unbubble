#!/usr/bin/env python3
"""Append-only journal of deletions applied through the connected mode.

    python3 cleanup_journal.py add    --app <app> --key <tracker key> --tool <tool> --app-version <branch>
                                      [--label <text>] [--failed] [--note <text>]
    python3 cleanup_journal.py merged --app <app> --app-version <branch>   # the owner merged the branch into test
    python3 cleanup_journal.py verify --app <app> --app-version <branch> --audit <new round>_audit.json
    python3 cleanup_journal.py show   --app <app>

File: ~/UnBubble-Projects/<app>/audit/cleanup-applied__<app>.json
    {"kind": "unbubble-cleanup-journal", "app": ..., "entries": [{key, label, tool, app_version,
      merged, ok, applied_at, verified, verified_at, note}]}

An entry counts as "deleted in the app" (for bubble_audit.py --state and the console) only when it
was applied to `test` itself or its branch was later merged — deletions on a discarded branch never
count. Entries are never removed; `merged` and `verify` only update flags.

stdlib only, Python 3.8+.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402

LIVE = {'live', 'production', 'prod', 'main', 'version-live'}


def journal_path(app):
    return _mcp.project_dir(app) / 'audit' / ('cleanup-applied__%s.json' % app)


def load(app):
    data = _mcp.load_json(journal_path(app), None)
    if not isinstance(data, dict) or data.get('kind') != 'unbubble-cleanup-journal':
        data = {'kind': 'unbubble-cleanup-journal', 'app': app, 'entries': []}
    return data


def keys_in_audit(audit):
    found = set()

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('key'), str):
                found.add(value['key'])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(audit)
    return found


def main():
    ap = argparse.ArgumentParser(description='Journal of deletions applied through the connected mode.')
    sub = ap.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('--app', required=True)
    add.add_argument('--key', required=True)
    add.add_argument('--tool', required=True)
    add.add_argument('--app-version', required=True)
    add.add_argument('--label', default='')
    add.add_argument('--failed', action='store_true')
    add.add_argument('--note', default='')
    merged = sub.add_parser('merged')
    merged.add_argument('--app', required=True)
    merged.add_argument('--app-version', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--app', required=True)
    verify.add_argument('--app-version', required=True)
    verify.add_argument('--audit', required=True, help='audit JSON of the round run on the fresh export')
    show = sub.add_parser('show')
    show.add_argument('--app', required=True)
    args = ap.parse_args()

    if getattr(args, 'app_version', None):
        _mcp.check_id(args.app_version, 'version')
    data = load(args.app)
    entries = data['entries']
    if args.command == 'add':
        if args.app_version.strip().lower() in LIVE:
            raise SystemExit('the connected mode never writes to the live version')
        entries.append({'key': args.key, 'label': args.label, 'tool': args.tool, 'app_version': args.app_version,
                        'merged': False, 'ok': not args.failed, 'applied_at': _mcp.now_iso(),
                        'verified': None, 'verified_at': None, 'note': args.note})
        result = {'ok': True, 'entries': len(entries)}
    elif args.command == 'merged':
        count = 0
        for entry in entries:
            if entry.get('app_version') == args.app_version and entry.get('ok') and not entry.get('merged'):
                entry['merged'] = True
                entry['merged_at'] = _mcp.now_iso()
                count += 1
        result = {'ok': True, 'marked_merged': count}
    elif args.command == 'verify':
        audit = _mcp.load_json(args.audit)
        if not isinstance(audit, dict) or audit.get('summary_version', 1) < 2:
            raise SystemExit('need an audit JSON with tracker keys (bubble_audit.py --json, summary_version 2)')
        still_there = keys_in_audit(audit)
        gone, remaining = 0, []
        for entry in entries:
            if entry.get('app_version') != args.app_version or not entry.get('ok'):
                continue
            entry['verified'] = entry['key'] not in still_there
            entry['verified_at'] = _mcp.now_iso()
            if entry['verified']:
                gone += 1
            else:
                remaining.append(entry['key'])
        result = {'ok': not remaining, 'verified_deleted': gone, 'still_reported': remaining[:50]}
    else:
        summary = {}
        for entry in entries:
            bucket = summary.setdefault(entry.get('app_version'), {'applied': 0, 'failed': 0, 'merged': 0, 'verified': 0})
            bucket['applied' if entry.get('ok') else 'failed'] += 1
            bucket['merged'] += 1 if entry.get('merged') else 0
            bucket['verified'] += 1 if entry.get('verified') else 0
        print(json.dumps({'ok': True, 'journal': str(journal_path(args.app)), 'by_version': summary}, indent=1))
        return 0
    data['updated_at'] = _mcp.now_iso()
    _mcp.write_private_json(journal_path(args.app), data)
    print(json.dumps(result, indent=1))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
