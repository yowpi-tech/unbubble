#!/usr/bin/env python3
"""Capture what each screen shows, per role, for the Bubble app or for the rebuilt app.

Bubble app (pages from the clone inventory, version-test or a branch only when logged in):
    python3 capture_screens.py --app <app-id> --roles anon,admin,agent [--version test]
        [--pages home,dashboard] [--params params.json] [--limit 40]

Rebuilt app (the same screens, by a route map Bubble page -> route):
    python3 capture_screens.py --app <app-id> --target rebuild --base-url http://localhost:3000
        --route-map routes.json --roles anon,admin [--session-app rebuild-<app-id>]

Roles other than `anon` use the test-user session captured once per role with
`python3 mcp/launch.py cli eval capture-app-session ...` (a human signs in; never a real user).
Pages with a content type need an example in --params ({"page": {"path": "<thing id or slug>",
"query": {...}}}, taken from the TEST database); without one they are skipped and listed.

Writes ~/UnBubble-Projects/<app>/visual/<bubble|rebuild>/<role>/<page>.json|png and
visual/INDEX-<target>.md. Opening a page runs its page-load workflows as that user: captures run
on version-test/branches, against test data — the screenshots show whatever that database holds.

stdlib only, Python 3.8+.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402


def bubble_pages(project, wanted, limit):
    inventory = _mcp.load_json(project / 'inventory' / 'pages.json', None)
    if not isinstance(inventory, list):
        raise SystemExit('no inventory/pages.json in %s: run unbubble:clone step 1 first' % project)
    pages = [p for p in inventory if isinstance(p, dict) and p.get('name')]
    if wanted:
        names = set(wanted)
        pages = [p for p in pages if p['name'] in names]
    else:  # busiest screens first: they carry most of the product
        pages.sort(key=lambda p: (-(p.get('workflow_count') or 0), -(p.get('element_count') or 0), p['name']))
    return pages if wanted else pages[: max(1, limit)]


def capture_bubble(app, profile, version, page, params, role, out_json, out_png, max_nodes):
    spec = params.get(page['name']) or {}
    page_path = page['name'] + ('/' + str(spec['path']).strip('/') if spec.get('path') else '')
    args = ['eval', 'capture-bubble-visual', '--profile', profile, '--app-id', app, '--app-version', version,
            '--page', page_path, '--output', out_json, '--screenshot', out_png,
            '--max-nodes', str(max_nodes), '--wait-ms', '1500']
    if spec.get('query'):
        args += ['--query', json.dumps(spec['query'])]
    if role != 'anon':
        args += ['--role', role]
    return _mcp.run_cli(args, timeout=600)


def left_test_version(final_url):
    """A Bubble capture whose final URL has no /version-<x>/ segment ended on the live app (a redirect)."""
    path = urlparse(str(final_url or '')).path
    return bool(final_url) and not re.match(r'^/version-[^/]+', path)


def capture_rebuild(url, session_app, role, out_json, out_png, max_nodes):
    args = ['eval', 'capture-visual', '--source', url, '--output', out_json, '--screenshot', out_png,
            '--max-nodes', str(max_nodes), '--wait-ms', '1000', '--no-allow-raw-fallback']
    if role != 'anon':
        args += ['--app-session-app', session_app, '--role', role]
    return _mcp.run_cli(args, timeout=600)


def main():
    ap = argparse.ArgumentParser(description='Capture screens per role (Bubble app or rebuilt app).')
    ap.add_argument('--app', required=True)
    ap.add_argument('--target', choices=['bubble', 'rebuild'], default='bubble')
    ap.add_argument('--roles', default='anon', help='comma-separated; `anon` = not signed in')
    ap.add_argument('--profile', default='', help='MCP profile (default: the app id)')
    ap.add_argument('--version', default='test', help="Bubble version: 'test' or a branch (never live)")
    ap.add_argument('--pages', default='', help='comma-separated page names (default: busiest first)')
    ap.add_argument('--params', default='', help='JSON with example URL path/query per page (test data)')
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--max-nodes', type=int, default=800)
    ap.add_argument('--base-url', default='', help='rebuilt app base URL')
    ap.add_argument('--route-map', default='', help='JSON {bubble page: route} for the rebuilt app')
    ap.add_argument('--session-app', default='', help='name the rebuilt app role sessions were captured under')
    args = ap.parse_args()
    if args.version.strip().lower() in ('live', 'production', 'prod', 'main', 'version-live'):
        raise SystemExit('screens are captured on version-test or a branch, never on live')

    project = _mcp.project_dir(args.app)
    roles = [_mcp.check_id(r.strip(), 'role') for r in args.roles.split(',') if r.strip()]
    params = {}
    if args.params:
        params = _mcp.load_json(args.params, None)
        if not isinstance(params, dict):
            raise SystemExit('cannot read --params %s (a JSON object {page: {path, query}})' % args.params)
    rows, skipped = [], []
    if args.target == 'bubble':
        wanted = [p.strip() for p in args.pages.split(',') if p.strip()]
        pages = bubble_pages(project, wanted, args.limit)
        known = {page['name'] for page in pages}
        skipped += [{'page': name, 'reason': 'not in the clone inventory (inventory/pages.json)'}
                    for name in wanted if name not in known]
        jobs = []
        for page in pages:
            if page.get('content_type') and page['name'] not in params:
                skipped.append({'page': page['name'], 'reason': 'needs a %s in the URL: add it to --params'
                                % page['content_type']})
                continue
            jobs.append((page['name'], page))
    else:
        if not args.base_url or not args.route_map:
            raise SystemExit('--target rebuild needs --base-url and --route-map')
        routes = _mcp.load_json(args.route_map, None)
        if not isinstance(routes, dict) or not routes:
            raise SystemExit('cannot read --route-map %s (a JSON object {bubble page: route})' % args.route_map)
        jobs = [(name, route) for name, route in sorted(routes.items())]
        if args.pages:
            wanted = set(p.strip() for p in args.pages.split(','))
            jobs = [job for job in jobs if job[0] in wanted]

    if args.target == 'bubble':
        _mcp.check_id(args.version, 'version')
        _mcp.check_id(args.profile or args.app, 'profile')
    stamp = _mcp.now_iso()
    for role in roles:
        folder = project / 'visual' / args.target / _mcp.safe_name(role)
        _mcp.private_dir(folder)
        for item in skipped:
            rows.append({'page': item['page'], 'role': role, 'status': 'skipped', 'reason': item['reason'],
                         'captured_at': stamp})
        for name, spec in jobs:
            out_json = folder / (_mcp.safe_name(name) + '.json')
            out_png = folder / (_mcp.safe_name(name) + '.png')
            discard(out_json, out_png)  # a stale file must never pass for this run's capture
            if args.target == 'bubble':
                code, result, stderr = capture_bubble(args.app, args.profile or args.app, args.version, spec, params,
                                                      role, out_json, out_png, args.max_nodes)
                url_hint = name
            else:
                url_hint = args.base_url.rstrip('/') + '/' + str(spec).lstrip('/')
                code, result, stderr = capture_rebuild(url_hint, args.session_app or 'rebuild-' + args.app, role,
                                                       out_json, out_png, args.max_nodes)
            snapshot = _mcp.load_json(out_json, {}) if code == 0 else {}
            status = 'ok' if code == 0 and snapshot else 'failed'
            access = snapshot.get('access') or '—'
            if status == 'ok' and args.target == 'bubble' and left_test_version(snapshot.get('final_url')):
                access = 'left the test version'  # redirected to live: report it, never use the capture
            if status != 'ok' or access == 'left the test version':
                discard(out_json, out_png)
            rows.append({
                'page': name, 'role': role, 'status': status, 'access': access,
                'final_url': snapshot.get('final_url'),
                'nodes': len(snapshot.get('nodes') or []), 'max_nodes': args.max_nodes,
                'screenshot': str(out_png) if out_png.exists() else None,
                'error': None if status == 'ok' else _mcp.redact(
                    stderr or (json.dumps(result) if result else 'capture failed'))[-300:],
                'target': url_hint, 'version': args.version if args.target == 'bubble' else None,
                'captured_at': stamp,
            })

    index_path = project / 'visual' / ('INDEX-%s.json' % args.target)
    merged = merge_index(_mcp.load_json(index_path, {}) or {}, rows)
    index = {'app': args.app, 'target': args.target, 'updated_at': stamp,
             'roles': sorted({row['role'] for row in merged}), 'screens': merged,
             'last_run': {'captured_at': stamp, 'roles': roles, 'version': args.version if args.target == 'bubble' else None,
                          'max_nodes': args.max_nodes, 'screens': len(rows)}}
    _mcp.write_private_json(index_path, index)
    _mcp.write_private_text(project / 'visual' / ('INDEX-%s.md' % args.target), index_markdown(index))
    ok = all(row['status'] in ('ok', 'skipped') and row.get('access') != 'left the test version' for row in rows)
    print(json.dumps({'ok': ok, 'screens': len(rows),
                      'failed': sum(1 for r in rows if r['status'] == 'failed'),
                      'no_access': sum(1 for r in rows if r.get('access') == 'redirected'),
                      'left_test_version': sum(1 for r in rows if r.get('access') == 'left the test version'),
                      'skipped': sum(1 for r in rows if r['status'] == 'skipped'),
                      'index': str(project / 'visual' / ('INDEX-%s.md' % args.target))}, indent=1))
    return 0 if ok else 1


def discard(*paths):
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


def merge_index(old, rows):
    """The index keeps the latest capture of every (page, role): a run over a few pages updates
    those rows and leaves the others as they were."""
    merged = {(row.get('page'), row.get('role')): row for row in old.get('screens') or [] if isinstance(row, dict)}
    for row in rows:
        merged[(row['page'], row['role'])] = row
    return [merged[key] for key in sorted(merged, key=lambda k: (str(k[1]), str(k[0])))]


def index_markdown(index):
    lines = ['# Screens — %s (%s)' % (index['app'], index['target']), '',
             'Updated %s · roles: %s' % (index['updated_at'], ', '.join(index['roles'])), '',
             '| Page | Role | Access | Nodes | Screenshot | Captured |', '|---|---|---|---|---|---|']
    for row in index['screens']:
        if row.get('status') == 'skipped':
            access = 'skipped: %s' % row.get('reason')
        elif row.get('status') != 'ok':
            access = 'capture failed'
        elif row.get('access') == 'redirected':
            access = 'no access in this role'
        else:
            access = row.get('access') or '—'
        shot = Path(row['screenshot']).name if row.get('screenshot') else '—'
        lines.append('| %s | %s | %s | %s | %s | %s |' % (row['page'], row['role'], access, row.get('nodes', '—'),
                                                         shot, row.get('captured_at') or '—'))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    sys.exit(main())
