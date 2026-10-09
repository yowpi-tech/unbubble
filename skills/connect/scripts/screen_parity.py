#!/usr/bin/env python3
"""Minimum screen parity between the Bubble app and the rebuilt app — content and actions only.

    python3 screen_parity.py --app <app-id> [--roles admin,agent] [--pages home,dashboard]
        [--verdicts levelup/screen-parity-verdicts.json] [--strict]

Compares, per screen and role, the captures listed in visual/INDEX-bubble.json and
visual/INDEX-rebuild.json (written by capture_screens.py; a failed, skipped or live-redirected
capture keeps the gate open, and files without an index row are ignored) and lists what the Bubble
screen offers that the new screen does not: headings, labels and other short UI texts,
buttons and links, fields (by placeholder), images (by alt text). Geometry, typography, colors and
spacing are ignored on purpose — the rebuild follows a new design system and is expected to look
different (and better); only missing content or actions matter.

Inside a Bubble repeating group only what repeats across rows (a per-row "Edit" button, a column
label) counts; one-off texts there are database content and are listed apart, without a verdict.

Every missing item needs a verdict in the verdicts file:
    {"<role>/<page>": {"<kind>:<text>": {"verdict": "renamed|moved|dropped|missing",
                                         "note": "...", "date": "YYYY-MM-DD"}}}
renamed/moved = present under another form; dropped = cut by a dated owner decision; missing = a
real gap (becomes a backlog story). A whole screen takes the key "screen" (e.g. merged into another
route: "moved"), and a role that cannot open the rebuilt screen takes the key "access".
Writes levelup/screen-parity.md|json. --strict exits 1 while any item has no verdict, is still
`missing`, or comes from an unusable or truncated capture — the final gate of the execution contract.

stdlib only, Python 3.8+.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402

VERDICTS = ('renamed', 'moved', 'dropped', 'missing')
HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
ACTION_TAGS = {'button', 'a'}
TEXT_TAGS = {'label', 'span', 'p', 'div', 'th', 'legend', 'li', 'strong', 'b', 'em', 'small', 'td'}
DATA_LIKE = re.compile(
    r'^(?:R\$|US\$|\$|€|£)?\s*[\d\s.,:/%+-]+$'  # numbers, money, dates, times, percentages
    r'|^\S+@\S+$'  # emails
    r'|^https?://'  # urls
)
EDGE_PUNCT = ' *:•·|-–—()[]'


def norm(value):
    return _mcp.normalize_text(value).strip(EDGE_PUNCT).strip()


def kind_of(node, text):
    tag = str(node.get('tag') or '').lower()
    cls = str(node.get('class') or '')
    role = str(node.get('role') or '').lower()
    if tag in HEADINGS or role == 'heading':
        return 'heading'
    if tag in ACTION_TAGS or role in ('button', 'link', 'tab', 'menuitem') or 'Button' in cls or 'Link' in cls:
        return 'action'
    if tag in TEXT_TAGS or 'Text' in cls:
        return 'text'
    return None


def items_of(snapshot, lists=False):
    """{"<kind>:<normalized text>": label}. With lists=True (the Bubble side), content inside
    repeating groups only counts when it repeats; the rest is returned apart as list content."""
    found, inside = {}, {}
    stack = []  # (depth, list id or None) of the current ancestors, rebuilt from the flat DFS order
    for index, node in enumerate(snapshot.get('nodes') or []):
        if not isinstance(node, dict):
            continue
        depth = node.get('depth') if isinstance(node.get('depth'), int) else 0
        while stack and stack[-1][0] >= depth:
            stack.pop()
        list_id = next((ancestor for _, ancestor in reversed(stack) if ancestor is not None), None)
        own_list = index if lists and 'RepeatingGroup' in str(node.get('class') or '') else None
        stack.append((depth, own_list if own_list is not None else list_id))
        entries = []
        if node.get('placeholder'):
            entries.append(('field', node['placeholder']))
        if str(node.get('tag') or '').lower() == 'img' and node.get('alt'):
            entries.append(('image', node['alt']))
        text = str(node.get('text') or '').strip()
        if text and len(text) <= 80 and not DATA_LIKE.search(text):
            kind = kind_of(node, text)
            if kind:
                entries.append((kind, text))
        for kind, label in entries:
            key = '%s:%s' % (kind, norm(label))
            if key.endswith(':'):
                continue
            if list_id is None:
                found.setdefault(key, label)
            else:
                inside.setdefault(list_id, {}).setdefault(key, [label, 0])[1] += 1
    list_content = {}
    for rows in inside.values():
        for key, (label, count) in rows.items():
            if count >= 2 or key.startswith('field:'):
                found.setdefault(key, label)
            else:
                list_content.setdefault(key, label)
    return found, list_content


def compare(bubble, rebuild):
    left, list_content = items_of(bubble, lists=True)
    right, _ = items_of(rebuild)
    right_texts = {key.split(':', 1)[1] for key in right}
    # the same text under another kind (a text that became a button, a placeholder that became a
    # label) is present: only texts absent in every form are missing
    missing = {key: label for key, label in left.items()
               if key not in right and key.split(':', 1)[1] not in right_texts}
    return missing, len(left), len(right), sorted(set(list_content.values()))


def load_index(project, target):
    index = _mcp.load_json(project / 'visual' / ('INDEX-%s.json' % target), None)
    if not isinstance(index, dict):
        return None
    return {(row.get('role'), row.get('page')): row for row in index.get('screens') or [] if isinstance(row, dict)}


def snapshot_path(project, target, role, page):
    return project / 'visual' / target / _mcp.safe_name(role) / (_mcp.safe_name(page) + '.json')


def unusable(row):
    """Why an index row cannot be compared (None when it can)."""
    if row is None:
        return 'not captured'
    if row.get('status') == 'skipped':
        return 'skipped: %s' % row.get('reason')
    if row.get('status') != 'ok':
        return 'capture failed: capture it again'
    if row.get('access') == 'left the test version':
        return 'the capture left the test version (redirect to live): fix the redirect, then capture again'
    return None


def truncated(row, snapshot):
    limit = row.get('max_nodes') if isinstance(row.get('max_nodes'), int) else None
    return bool(limit) and len(snapshot.get('nodes') or []) >= limit


def main():
    ap = argparse.ArgumentParser(description='Minimum screen parity (content and actions) Bubble vs rebuild.')
    ap.add_argument('--app', required=True)
    ap.add_argument('--roles', default='', help='comma-separated (default: every role in the Bubble index)')
    ap.add_argument('--pages', default='', help='comma-separated (default: every page in the Bubble index)')
    ap.add_argument('--verdicts', default='', help='verdicts JSON (default: levelup/screen-parity-verdicts.json)')
    ap.add_argument('--strict', action='store_true',
                    help='exit 1 while any item lacks a verdict, is missing or comes from an unusable capture')
    args = ap.parse_args()
    project = _mcp.project_dir(args.app)
    bubble_index = load_index(project, 'bubble')
    if bubble_index is None:
        raise SystemExit('no visual/INDEX-bubble.json in %s: run capture_screens.py first' % project)
    rebuild_index = load_index(project, 'rebuild') or {}
    verdicts_path = Path(args.verdicts) if args.verdicts else project / 'levelup' / 'screen-parity-verdicts.json'
    verdicts = _mcp.load_json(verdicts_path, {}) or {}
    roles = [r for r in args.roles.split(',') if r] or sorted({role for role, _ in bubble_index if role})
    pages = [p for p in args.pages.split(',') if p]
    keys = [(role, page) for role in roles for page in pages] if pages else sorted(
        key for key in bubble_index if key[0] in roles)

    screens, unresolved, still_missing, truncated_count = [], 0, 0, 0
    for role, page in keys:
        screen_id = '%s/%s' % (role, page)
        screen_verdicts = verdicts.get(screen_id) or {}
        screen_verdict = (screen_verdicts.get('screen') or {}).get('verdict')
        entry = {'screen': screen_id, 'screen_verdict': screen_verdict if screen_verdict in VERDICTS else None}
        if entry['screen_verdict'] in ('renamed', 'moved', 'dropped'):
            screens.append(dict(entry, status='screen %s (owner verdict)' % entry['screen_verdict']))
            continue
        row = bubble_index.get((role, page))
        problem = unusable(row)
        bubble = _mcp.load_json(snapshot_path(project, 'bubble', role, page), None) if problem is None else None
        if problem is None and not isinstance(bubble, dict):
            problem = 'capture file missing: capture it again'
        if problem:
            screens.append(dict(entry, status='Bubble side %s' % problem))
            unresolved += 1
            continue
        if bubble.get('access') == 'redirected':
            screens.append(dict(entry, status='no access in Bubble for this role'))
            continue
        rebuild_row = rebuild_index.get((role, page))
        problem = unusable(rebuild_row)
        rebuild = (_mcp.load_json(snapshot_path(project, 'rebuild', role, page), None)
                   if problem is None else None)
        if problem is None and not isinstance(rebuild, dict):
            problem = 'capture file missing: capture it again'
        if problem:
            screens.append(dict(entry, status='rebuild %s' % problem))
            unresolved += 1
            continue
        if rebuild.get('access') == 'redirected':
            verdict = (screen_verdicts.get('access') or {}).get('verdict')
            verdict = verdict if verdict in VERDICTS else None
            unresolved += verdict is None
            still_missing += verdict == 'missing'
            screens.append(dict(entry, status='the role cannot open this screen in the rebuild',
                                missing=[{'item': 'access', 'text': 'no access in the rebuild', 'verdict': verdict,
                                          'note': (screen_verdicts.get('access') or {}).get('note')}]))
            continue
        cut = [side for side, side_row, snap in (('bubble', row, bubble), ('rebuild', rebuild_row, rebuild))
               if truncated(side_row, snap)]
        missing, n_left, n_right, list_content = compare(bubble, rebuild)
        items = []
        for key, label in sorted(missing.items()):
            verdict = (screen_verdicts.get(key) or {}).get('verdict')
            if verdict not in VERDICTS:
                verdict = None
                unresolved += 1
            elif verdict == 'missing':
                still_missing += 1
            items.append({'item': key, 'text': label, 'verdict': verdict,
                          'note': (screen_verdicts.get(key) or {}).get('note')})
        status = 'compared'
        if cut:
            truncated_count += 1
            status = 'compared on a truncated capture (%s): capture again with a higher --max-nodes' % ', '.join(cut)
        screens.append(dict(entry, status=status, bubble_items=n_left, rebuild_items=n_right, missing=items,
                            list_content=list_content[:20], list_content_total=len(list_content)))

    passes = unresolved == 0 and still_missing == 0 and truncated_count == 0
    report = {'app': args.app, 'generated_at': _mcp.now_iso(), 'verdicts_file': str(verdicts_path),
              'roles': roles, 'pages': pages or None, 'screens': screens, 'unresolved': unresolved,
              'still_missing': still_missing, 'truncated_screens': truncated_count, 'passes_gate': passes}
    out_dir = project / 'levelup'
    _mcp.write_private_json(out_dir / 'screen-parity.json', report)
    lines = ['# Screen parity — %s' % args.app, '',
             'Content and actions only: visual differences are expected and never count. '
             'Generated %s.' % report['generated_at'], '',
             '**%s** · %d unresolved (items without a verdict, screens not comparable) · %d marked missing · '
             '%d truncated capture(s)' % ('Gate passes' if passes else 'Gate open', unresolved, still_missing,
                                          truncated_count), '',
             'Verdicts go in `%s`.' % verdicts_path, '']
    for screen in screens:
        lines.append('## %s — %s' % (screen['screen'], screen['status']))
        for item in screen.get('missing') or []:
            lines.append('- [%s] `%s` — %s' % (item['verdict'] or ' ', item['item'], item['text']))
        if screen.get('list_content_total'):
            lines.append('- (%d one-off text(s) inside lists treated as database content: see screen-parity.json)'
                         % screen['list_content_total'])
        lines.append('')
    _mcp.write_private_text(out_dir / 'screen-parity.md', '\n'.join(lines) + '\n')
    print(json.dumps({'ok': True, 'screens': len(screens), 'unresolved': unresolved, 'still_missing': still_missing,
                      'truncated_screens': truncated_count, 'passes_gate': passes,
                      'report': str(out_dir / 'screen-parity.md')}, indent=1))
    return 1 if args.strict and not passes else 0


if __name__ == '__main__':
    sys.exit(main())
