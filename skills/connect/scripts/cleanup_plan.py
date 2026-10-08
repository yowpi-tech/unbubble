#!/usr/bin/env python3
"""Turn an audit round into an ordered cleanup plan for the connected mode.

    python3 cleanup_plan.py <app>-vN_audit.json --profile <app>--<branch> --app-version <branch>
        [--progress audit/bubble_cleanup_progress__<app>.json] [--journal audit/cleanup-applied__<app>.json]
        [--include-review] [--include-destructive] [--out plan.json] [--md plan.md]

Reads the audit --json summary (summary_version 2: every finding carries its tracker `key`) and
writes batches of MCP tool calls, in dependency order — page workflows and custom events, pages,
option sets, styles, color/font variables, data fields, data types (soft delete) — each item with
the exact tool arguments (execute=false: the agent previews, the owner approves the batch, only
then execute=true + confirm=true). Items the owner kept, items already deleted, items already
applied on this target, and items the audit's runtime evidence saw in the server logs
(bubble_audit.py --evidence) are left out. What the MCP cannot delete (reusable definitions, backend
workflows, plugins, API Connector calls, removed-plugin references, mobile views, ambiguous names)
goes to a `manual` list with where to find it in the editor.

Defaults are conservative: only high-confidence categories. `--include-review` adds pages and
workflows on never-rendered elements; `--include-destructive` adds data fields and tables (never
the ones exposed in the Data API).

stdlib only, Python 3.8+.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402

ORDER = [
    ('page_workflows', 'Workflows on deleted elements and uncalled page custom events'),
    ('pages', 'Pages'),
    ('option_sets', 'Option sets'),
    ('styles', 'Styles'),
    ('variables', 'Color and font variables'),
    ('data_fields', 'Data fields (soft delete; data stays recoverable in Bubble)'),
    ('data_types', 'Data types (soft delete)'),
]


TEST_VERSIONS = ('test', 'version-test')


def required_json(path, what):
    """A file the owner pointed at must be readable JSON: silently ignoring it would put kept items
    back into the plan."""
    if Path(path).suffix.lower() != '.json':
        raise SystemExit('%s must be the JSON export (%s): the .md export is for people' % (what, path))
    data = _mcp.load_json(path, None)
    if data is None:
        raise SystemExit('cannot read %s %s (missing or not JSON)' % (what, path))
    return data


def progress_keys(path):
    if not path:
        return set(), set()
    data = required_json(path, '--progress')
    if isinstance(data, list):
        return set(data), set()
    if not isinstance(data, dict):
        raise SystemExit('--progress %s is not a tracker export' % path)
    deleted = set(data.get('deleted') or [])
    kept = {k.get('key') for k in data.get('kept') or [] if isinstance(k, dict)}
    return deleted, kept


def journal_keys(path, app_version):
    if not path:
        return set()
    data = required_json(path, '--journal')
    if not isinstance(data, dict) or data.get('kind') != 'unbubble-cleanup-journal':
        raise SystemExit('--journal %s is not a cleanup journal' % path)
    done = set()
    for entry in data.get('entries') or []:
        if not isinstance(entry, dict) or not entry.get('ok', True):
            continue
        if entry.get('merged') or entry.get('app_version') in TEST_VERSIONS + (app_version,):
            done.add(entry.get('key'))
    return done


def build_plan(audit, *, profile, app_version, deleted, kept, applied, include_review, include_destructive):
    if audit.get('summary_version', 1) < 2:
        raise SystemExit('audit JSON has no tracker keys: regenerate it with the current bubble_audit.py --json')
    integrity = audit.get('export_integrity') or {}
    if integrity.get('incomplete'):
        raise SystemExit('this audit ran on an INCOMPLETE export (missing reusable payloads): '
                         'get a complete export and audit again before cleaning anything')
    base = {'profile': profile, 'app_version': app_version, 'execute': False}
    batches = {name: [] for name, _ in ORDER}
    manual, skipped, alive = [], Counter(), []
    evidence = (audit.get('runtime_evidence') or {}).get('by_key') or {}

    def admit(item):
        key = item['key']
        if key in kept:
            skipped['kept by the owner'] += 1
            return False
        if key in deleted or key in applied:
            skipped['already deleted or applied'] += 1
            return False
        hits = (evidence.get(key) or {}).get('hits')
        if hits:  # the server logs show it running: not a deletion candidate, whatever the export says
            skipped['seen in the server logs (runtime evidence)'] += 1
            alive.append({'key': key, 'label': item.get('label') or key, 'hits': hits,
                          'last_seen': (evidence.get(key) or {}).get('last_seen')})
            return False
        return True

    def add(batch, item, tool, args):
        if admit(item):
            preview = dict(base, **args)
            batches[batch].append({'key': item['key'], 'label': item.get('label') or item['key'], 'tool': tool,
                                   'args': preview,
                                   # after the owner approves the batch; dry_run defaults to true in the schemas
                                   'apply_args': dict(preview, execute=True, dry_run=False)})

    def man(item, where):
        if admit(item):
            manual.append({'key': item['key'], 'label': item.get('label') or item['key'], 'where': where})

    wfa = audit.get('workflow_audit') or {}
    for row in wfa.get('triggers_on_missing_element') or []:
        item = {'key': row['key'], 'label': '%s · %s (element deleted)' % (row.get('container'), row.get('trigger'))}
        if row.get('kind') in ('page', 'reusable') and row.get('container'):
            add('page_workflows', item, 'delete_event',
                {'context': row['container'], 'event_ref': row['id'], 'ref_kind': 'id', 'confirm': True})
        else:
            man(item, 'mobile view %s → workflows → %s' % (row.get('container'), row.get('trigger')))
    for row in wfa.get('page_custom_events_uncalled') or []:
        item = {'key': row['key'], 'label': '%s › %s (custom event, never called)' % (row.get('container'), row.get('name'))}
        if row.get('kind') in ('page', 'reusable') and row.get('container'):
            add('page_workflows', item, 'delete_event',
                {'context': row['container'], 'event_ref': row['id'], 'ref_kind': 'id', 'confirm': True})
        else:
            man(item, 'mobile view %s → workflows → custom event %s' % (row.get('container'), row.get('name')))
    for row in wfa.get('triggers_on_hidden_element_leads') or []:
        item = {'key': row['key'], 'label': '%s · %s on never-rendered %s' % (row.get('container'), row.get('trigger'), row.get('element'))}
        if include_review and row.get('kind') in ('page', 'reusable') and row.get('container'):
            add('page_workflows', item, 'delete_event',
                {'context': row['container'], 'event_ref': row['id'], 'ref_kind': 'id', 'confirm': True})
        elif include_review:
            man(item, 'mobile view %s → workflows' % row.get('container'))
        else:
            skipped['review-only (use --include-review)'] += 1
    for row in wfa.get('backend_custom_events_uncalled') or []:
        man({'key': row['key'], 'label': '%s (backend custom event)' % row.get('name')},
            'Backend workflows → custom event %s → delete' % row.get('name'))

    for row in (audit.get('pages') or {}).get('unused') or []:
        item = {'key': row['key'], 'label': 'page %s' % row.get('name')}
        if include_review:
            add('pages', item, 'delete_page', {'name': row['name'], 'confirm': True})
        else:
            skipped['review-only (use --include-review)'] += 1

    for row in (audit.get('option_sets') or {}).get('unused') or []:
        add('option_sets', {'key': row['key'], 'label': 'option set %s' % (row.get('display') or row.get('name'))},
            'delete_option_set', {'option_set_ref': row['name'], 'confirm': True})

    # Styles go by exact id (style names resolve loosely and could hit a style in use); the display
    # name rides along and must match. Color/font variables go by their token id, matched exactly.
    for row in (audit.get('styles') or {}).get('unused') or []:
        item = {'key': row['key'], 'label': 'style %s (%s)' % (row.get('display'), row.get('type'))}
        if row.get('id') and row.get('display'):
            add('styles', item, 'delete_style', {'style_id': row['id'], 'name': row['display'], 'confirm': True})
        else:
            man(item, 'Styles tab → %s → %s' % (row.get('type'), row.get('display') or row.get('id')))

    variables = audit.get('variables') or {}
    for kind, tool in (('colors', 'delete_color'), ('fonts', 'delete_font')):
        for row in (variables.get(kind) or {}).get('unused') or []:
            item = {'key': row['key'], 'label': '%s variable %s' % (kind[:-1], row.get('name'))}
            if row.get('id'):
                add('variables', item, tool, {'name': row['id'], 'confirm': True})
            else:
                man(item, 'Styles tab → %s variables → %s' % (kind[:-1], row.get('name')))

    for row in (audit.get('data_fields') or {}).get('unused') or []:
        item = {'key': row['key'], 'label': 'field %s > %s' % (row.get('type_display'), row.get('display') or row.get('field_key'))}
        if include_destructive and not row.get('exposed'):
            add('data_fields', item, 'delete_data_field',
                {'data_type_ref': row['type_key'], 'name': row['field_key'], 'confirm': True})
        else:
            skipped['destructive (use --include-destructive)' if not row.get('exposed') else 'exposed in the Data API'] += 1
    for row in (audit.get('data_tables') or {}).get('unused') or []:
        item = {'key': row['key'], 'label': 'data type %s' % (row.get('display') or row.get('type_key'))}
        if include_destructive and not row.get('exposed'):
            add('data_types', item, 'delete_data_type', {'data_type_ref': row['type_key'], 'confirm': True})
        else:
            skipped['destructive (use --include-destructive)' if not row.get('exposed') else 'exposed in the Data API'] += 1

    reus = audit.get('reusables') or {}
    for row in (reus.get('unused_hard') or []) + (reus.get('unused_transitive') or []):
        man({'key': row['key'], 'label': 'reusable %s' % row.get('name')},
            'Reusable elements → %s → delete (the MCP cannot delete reusable definitions)' % row.get('name'))
    back = audit.get('backend') or {}
    for row in (back.get('unused_hard') or []) + (back.get('unused_transitive') or []):
        man({'key': row['key'], 'label': 'backend workflow %s' % row.get('wf_name')},
            'Backend workflows → folder %s → %s → delete' % (row.get('folder') or '(none)', row.get('wf_name')))
    plugins = audit.get('plugins') or {}
    for row in (plugins.get('orphaned') or []) + (plugins.get('configured_no_ui') or []):
        man({'key': row['key'], 'label': 'plugin %s' % (row.get('name') or row.get('id'))},
            'Plugins tab → %s → Uninstall (review: plugins can act without visible elements)' % (row.get('name') or row.get('id')))
    for row in (audit.get('api_connector') or {}).get('unused') or []:
        man({'key': row['key'], 'label': 'API call %s › %s' % (row.get('provider'), row.get('call'))},
            'Plugins → API Connector → %s → %s → delete' % (row.get('provider'), row.get('call')))
    for row in (audit.get('removed_plugin_refs') or {}).get('refs') or []:
        man({'key': row['key'], 'label': 'reference to removed plugin %s' % (row.get('plugin_name') or row.get('plugin_id'))},
            '%s → %s' % (row.get('container'), row.get('location')))
    for row in (audit.get('mobile_views') or {}).get('unused') or []:
        man({'key': row['key'], 'label': 'mobile view %s' % row.get('name')}, 'Mobile views → %s → delete' % row.get('name'))

    ordered = [{'batch': name, 'title': title, 'items': batches[name]} for name, title in ORDER if batches[name]]
    return {
        'app': audit.get('app'),
        'target': {'profile': profile, 'app_version': app_version},
        'created_at': _mcp.now_iso(),
        'options': {'include_review': include_review, 'include_destructive': include_destructive},
        'batches': ordered,
        'manual': manual,
        'seen_at_runtime': alive,
        'skipped': dict(skipped),
        'counts': {'tool_calls': sum(len(b['items']) for b in ordered), 'manual': len(manual)},
    }


def to_markdown(plan):
    lines = ['# Cleanup plan — %s' % plan['app'], '',
             'Target: profile `%s`, version `%s` · created %s'
             % (plan['target']['profile'], plan['target']['app_version'], plan['created_at']), '',
             'Each batch: preview every item with `args` (execute=false) → the owner approves the batch → '
             'call it with `apply_args` (execute=true, dry_run=false) → cleanup_journal.py add. '
             'Protocol: skills/connect/references/cleanup.md.', '']
    for batch in plan['batches']:
        lines += ['## %s (%d)' % (batch['title'], len(batch['items'])), '']
        lines += ['- `%s` — %s · `%s`' % (item['key'], item['label'], item['tool']) for item in batch['items']]
        lines.append('')
    if plan['manual']:
        lines += ['## By hand in the Bubble editor (%d)' % len(plan['manual']), '']
        lines += ['- `%s` — %s: %s' % (item['key'], item['label'], item['where']) for item in plan['manual']]
        lines.append('')
    if plan.get('seen_at_runtime'):
        lines += ['## Seen in the server logs — not planned (%d)' % len(plan['seen_at_runtime']), '',
                  'The export shows no use, but the runtime evidence does: ask the owner who calls these.', '']
        lines += ['- `%s` — %s: %d× (last %s)' % (item['key'], item['label'], item['hits'], item.get('last_seen') or '?')
                  for item in plan['seen_at_runtime']]
        lines.append('')
    if plan['skipped']:
        lines += ['## Left out', ''] + ['- %s: %d' % (why, n) for why, n in plan['skipped'].items()] + ['']
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description='Build a connected-mode cleanup plan from an audit round.')
    ap.add_argument('audit_json')
    ap.add_argument('--profile', required=True, help='MCP profile of the target (a branch profile)')
    ap.add_argument('--app-version', required=True, help="target version: a branch id or 'test' (never live)")
    ap.add_argument('--progress', help='bubble_cleanup_progress__<app>.json (kept + deleted items)')
    ap.add_argument('--journal', help='cleanup-applied__<app>.json (already applied items)')
    ap.add_argument('--include-review', action='store_true', help='also pages and never-rendered triggers')
    ap.add_argument('--include-destructive', action='store_true', help='also data fields and data types')
    ap.add_argument('--out', help='plan JSON path (default: next to the audit JSON)')
    ap.add_argument('--md', help='plan markdown path (default: next to the plan JSON)')
    args = ap.parse_args()
    if args.app_version.strip().lower() in ('live', 'production', 'prod', 'main', 'version-live'):
        raise SystemExit('the cleanup never targets the live version')
    _mcp.check_id(args.profile, 'profile')
    _mcp.check_id(args.app_version, 'version')
    audit = _mcp.load_json(args.audit_json)
    if not isinstance(audit, dict):
        raise SystemExit('cannot read %s' % args.audit_json)
    deleted, kept = progress_keys(args.progress)
    plan = build_plan(audit, profile=args.profile, app_version=args.app_version, deleted=deleted, kept=kept,
                      applied=journal_keys(args.journal, args.app_version),
                      include_review=args.include_review, include_destructive=args.include_destructive)
    out = Path(args.out) if args.out else Path(args.audit_json).with_name(
        Path(args.audit_json).name.replace('_audit.json', '') + '_cleanup-plan.json')
    _mcp.write_private_json(out, plan)
    md = Path(args.md) if args.md else out.with_suffix('.md')
    _mcp.write_private_text(md, to_markdown(plan) + '\n')
    print(json.dumps({'ok': True, 'plan': str(out), 'markdown': str(md), **plan['counts'],
                      'batches': {b['batch']: len(b['items']) for b in plan['batches']},
                      'skipped': plan['skipped']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
