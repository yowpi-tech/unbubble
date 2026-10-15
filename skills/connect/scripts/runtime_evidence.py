#!/usr/bin/env python3
"""Runtime evidence for audit candidates: do they still run in the live app?

    python3 runtime_evidence.py <app>-vN_audit.json --profile <app> [--source logs|workload]
        [--export <the round's .bubble>] [--days N] [--app-version live] [--max-candidates 40]
        [--control "<workflow name>"] [--out audit/runtime-evidence__<app>-vN[.workload].json]

Static analysis of an export cannot see who calls an exposed backend workflow from outside, which
API Connector calls really run, or whether a page is opened by direct link. Two read-only sources
can, each with its own blind spots. Both write the same shape — per candidate `hits`, `first_seen`,
`last_seen` and `coverage` — and only counts: never log rows, which carry user data.

--source logs (default) reads the server logs of one version within the plan's retention: one
paginated pull of the window matched locally or, when Bubble answers an empty window (busy apps
need a search term), one `contains` query per candidate, capped by --max-candidates. Some large
apps answer EVERY logs query "ok, 0 rows", which would stamp every candidate "not seen", so no zero
is trusted before a POSITIVE CONTROL passes: a workflow known to run in the window must show up in
the logs — --control, else the busiest backend workflow of the workload metrics (named through the
audit JSON or the export), else any candidate that came back with hits. When the control comes back
empty, every zero becomes unknown and the script exits 3: do not feed that file to the report.

--source workload counts runs per workflow in the editor's workload metrics, joined to the export:
scheduled API workflows, database triggers, recurring events and page/reusable workflows by inner
id, Workflow API calls by endpoint name. Custom events are not metered on their own: they count
through the workflows that trigger them. Pages and API Connector calls are not metered (unknown).
The counts cover every version, and Bubble keeps about 31 days of history: the effective window
starts at the first day `metrics workload-by-date` has data.

"Not seen" only covers the window: say so, and never treat it as proof of death.

stdlib only, Python 3.8+.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402

EXIT_BLIND = 3  # zeros were made unknown: the source showed nothing for what is known to run


def iso_z(moment):
    return moment.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def number(value):
    """A metric value as a float: numbers and numeric strings, anything else 0."""
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return 0.0


def values_of(collection):
    return list(collection.values()) if isinstance(collection, dict) else []


def candidates_from(audit, named_only=True):
    """The audit's candidates with their tracker keys. The logs are searched by name, so they only take
    named ones; the workload joins by inner id and also takes unnamed workflows."""
    out = []
    pages = audit.get('pages') or {}
    for row in (pages.get('unused') or []) + (pages.get('referenced_by_url') or []):
        out.append({'key': row['key'], 'kind': 'page', 'name': row.get('name'), 'id': row.get('inner_id')})
    back = audit.get('backend') or {}
    for bucket in ('unused_hard', 'unused_transitive', 'webhook_verify'):
        for row in back.get(bucket) or []:
            out.append({'key': row['key'], 'kind': 'backend_workflow', 'name': row.get('wf_name'),
                        'id': row.get('inner_id'), 'bucket': bucket})
    for row in (audit.get('api_connector') or {}).get('unused') or []:
        out.append({'key': row['key'], 'kind': 'api_call', 'name': row.get('call'), 'provider': row.get('provider')})
    for row in (audit.get('workflow_audit') or {}).get('backend_custom_events_uncalled') or []:
        out.append({'key': row['key'], 'kind': 'backend_custom_event', 'name': row.get('name'), 'id': row.get('id')})
    seen, unique = set(), []
    for item in out:
        if (item.get('name') or (not named_only and item.get('id'))) and item['key'] not in seen:
            seen.add(item['key'])
            unique.append(item)
    return unique


def summarize(results):
    return {'candidates': len(results),
            'seen': sum(1 for r in results if r.get('hits')),
            'not_seen': sum(1 for r in results if r.get('hits') == 0),
            'unknown': sum(1 for r in results if r.get('hits') is None)}


def downgrade(entries, coverage, reason):
    """No evidence either way: a zero that cannot be told from a blind source is unknown."""
    for entry in entries:
        entry.update(hits=None, first_seen=None, last_seen=None, coverage=coverage, reason=reason)


# ------------------------------------------------------------------ the export: who is who, who triggers whom
def walk_dicts(node):
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def export_index(data):
    """Every workflow of the export by inner id, the callers of every custom event (any action whose
    `custom_event` points at it, whatever the action type), and the names the Data API answers to."""
    client_safe = (data.get('settings') or {}).get('client_safe') or {}
    wf_api_on = bool(client_safe.get('exposes_wf_api', True))
    nodes, callers = {}, defaultdict(set)

    def add(wf, scope, container=None):
        if not isinstance(wf, dict) or not wf.get('id'):
            return
        props = wf.get('properties') if isinstance(wf.get('properties'), dict) else {}
        node = {'id': wf['id'], 'type': wf.get('type'), 'scope': scope,
                'name': props.get('wf_name') or props.get('event_name')}
        if container is not None:
            node['container'] = container
        if wf.get('type') == 'APIEvent':  # a missing `expose` key means exposed (bubble_audit.analyze_backend)
            node['exposed'] = bool(props.get('expose', wf_api_on))
        nodes[wf['id']] = node
        for action in walk_dicts(wf.get('actions')):
            target = action.get('properties')
            target = target.get('custom_event') if isinstance(target, dict) else None
            if isinstance(target, str) and target:
                callers[target].add(wf['id'])

    for wf in values_of(data.get('api')):
        add(wf, 'backend')
    for scope, collection in (('page', data.get('pages')), ('reusable', data.get('element_definitions')),
                              ('mobile', data.get('mobile_views'))):
        for container in values_of(collection):
            if isinstance(container, dict):
                for wf in values_of(container.get('workflows')):
                    add(wf, scope, container.get('name') or container.get('id') or '')
    data_types = set()
    user_types = data.get('user_types') if isinstance(data.get('user_types'), dict) else {}
    for key, value in user_types.items():
        for name in (key, value.get('display') if isinstance(value, dict) else None):
            low = str(name or '').strip().lower()
            if low:
                data_types.update((low, low.replace(' ', ''), low.replace(' ', '_')))
    return {'nodes': nodes, 'callers': callers, 'data_types': data_types}


def load_export(path, app):
    data = _mcp.load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get('api', {}), dict):
        raise SystemExit('not a readable .bubble export: %s' % path)
    if app and data.get('_id') and data.get('_id') != app:
        raise SystemExit('the export is for app %r and the audit JSON for %r: pass the export this round ran on'
                         % (data.get('_id'), app))
    return data


def find_export(audit):
    """The export this audit round ran on, when the connected mode downloaded it: its sidecar keeps
    the saved file's sha256, and the audit JSON keeps the sidecar as provenance."""
    digest = (audit.get('provenance') or {}).get('saved_sha256')
    if not digest or not audit.get('app'):
        return None
    try:
        paths = _mcp.mcp_paths()
        folder = Path(paths.get('exports') or Path(paths['home']) / 'exports') / _mcp.safe_name(audit['app'])
        metas = sorted(folder.glob('*.bubble.meta.json'))
    except (Exception, SystemExit):  # connected mode not installed: the caller asks for --export
        return None
    for meta in metas:
        if (_mcp.load_json(meta, {}) or {}).get('saved_sha256') == digest:
            export = meta.with_name(meta.name[:-len('.meta.json')])
            if export.exists():
                return export
    return None


def workflow_names(audit, index):
    """Inner id -> name of the backend workflows, to ask the logs about a workload tag."""
    names = {}
    back = audit.get('backend') or {}
    for bucket in ('unused_hard', 'unused_transitive', 'webhook_verify'):
        for row in back.get(bucket) or []:
            if row.get('inner_id') and row.get('wf_name'):
                names[row['inner_id']] = row['wf_name']
    for node in ((index or {}).get('nodes') or {}).values():
        if node['scope'] == 'backend' and node.get('name'):
            names.setdefault(node['id'], node['name'])
    return names


# ------------------------------------------------------------------ server logs
def row_time(row):
    """ISO time of a log row. Jetstream mixes units — seconds, milliseconds or microseconds since
    the epoch, as numbers or digit strings — so the magnitude decides."""
    for key in ('timestamp', 'created', 'created_at', 'time'):
        value = row.get(key) if isinstance(row, dict) else None
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            seconds = value / 1e6 if value > 1e14 else value / 1e3 if value > 1e11 else value
            try:
                stamp = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=0)
            except (OverflowError, OSError, ValueError):
                continue
            return stamp.isoformat().replace('+00:00', 'Z')
        if isinstance(value, str) and value:
            return value
    return None


def tally(rows, name):
    # whole-identifier match: page `home` must not count rows about `homepage`
    needle = re.compile(r'(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])' % re.escape(str(name)))
    hits, times = 0, []
    for row in rows:
        blob = json.dumps(row, ensure_ascii=False, default=str) if not isinstance(row, str) else row
        if needle.search(blob):
            hits += 1
            stamp = row_time(row)
            if stamp:
                times.append(stamp)
    times.sort()
    return {'hits': hits, 'first_seen': times[0] if times else None, 'last_seen': times[-1] if times else None}


def fetch(profile, app_version, start, end, contains=None, max_pages=25, limit=250000):
    """One logs pull. Returns (rows, info); rows is None when Bubble returned nothing usable
    (expired session, HTTP error, failed pagination) — never an empty list that would read as
    "not seen". info['complete'] is False when the pull stopped early or more rows exist than were
    read: then only the hits it found prove anything. An empty, complete answer still proves
    nothing until the positive control passes."""
    args = ['metrics', 'logs', '--profile', profile, '--app-version', app_version, '--start', start, '--end', end,
            '--paginate', '--max-pages', str(max_pages), '--limit', str(limit)]
    if contains:
        args += ['--contains', contains]
    code, result, stderr = _mcp.run_cli(args, timeout=1800)
    if code != 0 or not isinstance(result, dict):
        return None, {'complete': False, 'error': stderr[-300:] or 'logs request failed'}
    rows = result.get('items') or []
    row_count = result.get('row_count')
    complete = (result.get('ok') is not False and not result.get('truncated')
                and not (isinstance(row_count, int) and row_count > len(rows)))
    info = {'ok': result.get('ok'), 'row_count': row_count, 'rows_read': len(rows),
            'truncated': result.get('truncated'), 'stop_reason': result.get('stop_reason'),
            'covered_until': result.get('covered_until'), 'complete': complete}
    if result.get('ok') is False and not rows:
        info['error'] = _mcp.redact(result.get('error') or result.get('reason') or 'logs request failed')[:300]
        return None, info
    return rows, info


def ask_per_candidate(item, pull):
    """A server-side `contains` query for one candidate; zero hits count only when complete."""
    rows, info = pull(contains=item['name'], max_pages=2, limit=20000)
    if rows is None:
        return {'hits': None, 'first_seen': None, 'last_seen': None, 'coverage': 'failed',
                'error': info.get('error')}
    found = tally(rows, item['name'])
    if not info['complete'] and found['hits'] == 0:
        found['hits'] = None
    found['coverage'] = 'complete' if info['complete'] else 'partial'
    return found


CONTROL_FAMILIES = ('schedule_api_event', 'run_data_trigger_workflow', 'recurring_event')
BLIND_LOGS = 'logs endpoint returned no rows for a known-active workflow'
NO_CONTROL = ('no positive control: nothing known to run could be checked in the logs, so a zero cannot be '
              'told from a blind endpoint (pass --export or --control)')


def control_from_workload(profile, window, names):
    """The positive control for the logs: the backend workflow with the most runs in the window, per
    the workload metrics, that the audit JSON or the export can name."""
    tried = []
    for family in CONTROL_FAMILIES:
        fam = workload_family(profile, window, family)
        if not fam['ok']:
            tried.append('%s: %s' % (family, fam['error']))
            continue
        for tag, row in sorted(fam['rows'].items(), key=lambda pair: -pair[1]['runs']):
            if row['runs'] > 0 and names.get(tag):
                return {'name': names[tag], 'id': tag, 'source': 'workload:' + family,
                        'runs_in_window': row['runs']}
        tried.append('%s: no workflow with runs that the audit JSON or the export can name' % family)
    return {'name': None, 'source': 'workload', 'status': 'unavailable', 'reason': '; '.join(tried)}


def check_control(control, pull):
    """Ask the logs for the control the way candidates are asked: if a workflow known to run comes
    back empty, so would every candidate."""
    rows, info = pull(contains=control['name'], max_pages=1, limit=2000)
    control['checked_in'] = 'query'
    if rows is None:
        control.update(status='error', rows_read=0, hits=0,
                       reason='the logs query for the control failed: %s' % (info.get('error') or 'no answer'))
        return control
    hits = tally(rows, control['name'])['hits']
    control.update(rows_read=len(rows), hits=hits, status='passed' if hits else 'failed')
    if not hits:
        control['reason'] = BLIND_LOGS if not rows else 'rows came back, but none mention the known-active workflow'
    return control


def logs_evidence(args, audit, index, candidates, window):
    """Server-log evidence behind a positive control. Returns (report, exit code, printed summary)."""
    stats = {'queries': 0, 'failed': 0}

    def pull(contains=None, max_pages=25, limit=250000):
        rows, info = fetch(args.profile, args.app_version, window['start'], window['end'], contains=contains,
                           max_pages=max_pages, limit=limit)
        stats['queries'] += 1
        stats['failed'] += rows is None
        return rows, info

    names = workflow_names(audit, index)
    control = {'name': args.control, 'source': '--control'} if args.control else None

    def get_control():
        nonlocal control
        if control is None:
            control = control_from_workload(args.profile, window, names)
        return control

    cap = max(0, args.max_candidates)
    rows, info = pull()
    pending = []
    if rows:
        method = 'window'
        results = [dict(item, coverage='complete' if info['complete'] else 'partial', **tally(rows, item['name']))
                   for item in candidates]
        zeros = [entry for entry in results if entry['hits'] == 0]
        if zeros and info['complete'] and get_control().get('name'):
            control['window_hits'] = tally(rows, control['name'])['hits']
            if control['window_hits']:
                control.update(status='passed', checked_in='window')
            else:
                # a complete pull that misses a workflow known to run is not the whole story: its
                # zeros are asked again one by one, like the zeros of a partial pull
                info['complete'] = False
        if zeros and not info['complete']:
            method = 'window (partial) + per-candidate'
            pending = zeros
    else:
        method = 'per-candidate'  # Bubble answers an empty window on busy apps, or the pull failed
        results = [dict(item, hits=None, first_seen=None, last_seen=None) for item in candidates]
        pending = list(results)
    if pending:
        ctl = get_control()
        if ctl.get('name') and not ctl.get('status'):
            check_control(ctl, pull)
        if ctl.get('status') in ('failed', 'error'):
            # the logs show nothing for what is known to run (or could not be asked): no candidate
            # query could prove a zero
            downgrade(pending, 'blind' if ctl['status'] == 'failed' else 'unverified', ctl.get('reason'))
            pending = []
        for entry in pending[:cap]:
            entry.update(ask_per_candidate(entry, pull))
        for entry in pending[cap:]:
            entry.update(hits=None, first_seen=None, last_seen=None,
                         skipped='over --max-candidates' if method == 'per-candidate'
                         else 'partial window, over --max-candidates')

    zeros = [entry for entry in results if entry.get('hits') == 0]
    if control is None:
        control = {'status': 'not needed'}  # nothing came back as "not seen"
    elif zeros and control.get('status') != 'passed':
        seen = [entry for entry in results if entry.get('hits')]
        if seen:  # the logs did return rows for a candidate: they can see this app
            best = max(seen, key=lambda entry: entry['hits'])
            control.update(name=best['name'], source='candidate', status='passed', hits=best['hits'],
                           reason='no workload control (%s); a candidate came back with hits'
                                  % (control.get('reason') or 'none named'))
        else:
            downgrade(zeros, 'unverified', NO_CONTROL)

    attempted = [r for r in results if r.get('coverage') in ('complete', 'partial', 'failed')]
    errors = sum(1 for r in attempted if r['coverage'] == 'failed')
    # every query failed: an expired session, most likely
    if (attempted and errors == len(attempted)) or stats['failed'] == stats['queries']:
        code = 1
    elif any(r.get('coverage') in ('blind', 'unverified') for r in results):
        code = EXIT_BLIND
    else:
        code = 0
    report = {
        'app': audit.get('app'),
        'app_version': args.app_version,
        'window': window,
        'method': method,
        'source': dict(info, kind='logs', positive_control=control),
        'note': 'Counts only. "Not seen" covers this window and the plan\'s log retention, nothing more, and '
                'only after the positive control (source.positive_control) passed.',
        'candidates': results,
        'summary': summarize(results),
    }
    printed = {'source': 'logs', 'method': method, 'window_days': window['days'], **report['summary'],
               'failed_queries': errors,
               'positive_control': {key: control[key] for key in ('status', 'name', 'source', 'checked_in', 'hits',
                                                                  'runs_in_window', 'reason') if key in control}}
    if rows is None and info.get('error'):
        printed['error'] = info['error']
    if code == EXIT_BLIND:
        printed['hint'] = ('zeros are unknown: the logs cannot tell "not seen" from blind here. Do not feed this '
                           'file to bubble_audit.py; for workflows run --source workload --export <the round '
                           'export>.')
    return report, code, printed


# ------------------------------------------------------------------ workload metrics
WORKLOAD_HISTORY_DAYS = 31  # Bubble answers wider windows with the same ~31 days
WORKLOAD_ROW_LIMIT = 100000  # the CLI keeps 50 rows by default; every workflow of a family is needed
# what the rows of each family are keyed by: inner ids, except `api` (Workflow API endpoint names as
# the caller typed them, plus Data API calls keyed by data-type name)
WORKLOAD_FAMILIES = ('schedule_api_event', 'run_data_trigger_workflow', 'recurring_event', 'workflow', 'api')
BACKEND_FAMILY = {'APIEvent': 'schedule_api_event', 'DatabaseTriggerEvent': 'run_data_trigger_workflow',
                  'RecurringEvent': 'recurring_event'}
PAGE_WORKFLOW = 'page and reusable workflows are metered only when they run server-side actions'
NO_CALLER = ('custom events are metered inside the workflow that triggers them, and no workflow in the export '
             'leads to this one')
NOT_METERED = {
    'page': 'pages are not metered as workflow runs: use the logs, once their positive control passes',
    'api_call': 'API Connector calls are not joined to the workload metrics: use the logs, once their positive '
                'control passes',
}
COVERAGE_ORDER = ('failed', 'blind', 'unjoined', 'unverified', 'partial', 'not_metered')
NOT_TRUSTED = ('failed', 'blind', 'unjoined')  # a family in one of these states proves no zero at all
STATUS_REASON = {
    'failed': 'the %s metrics could not be read',
    'blind': 'the %s metrics came back without rows while Bubble reports activity for that family',
    'unjoined': 'the %s rows do not match the workflows of this export',
    'unverified': 'the %s rows could not be checked against the family total',
    'partial': 'the %s rows are incomplete (cut, or short of the family total)',
}
MIN_JOINED = 0.5  # share of a family's runs that must belong to workflows of the export


def joins_export(family, node):
    """Whether a workflow of the export is the kind a family's rows are keyed by (page and reusable
    custom events included: those running server-side actions have rows of their own)."""
    if family == 'workflow':
        return node['scope'] != 'backend'
    return node['scope'] == 'backend' and BACKEND_FAMILY.get(node.get('type')) == family


def joined_share(family, fam, index):
    """Share of a family's runs whose tag is a workflow of the export of the matching kind (or, for
    `api`, an endpoint name or a data type). Near 1 when the export is the app's and the tags are inner
    ids; near 0 with another export, or if Bubble changed what it tags runs with."""
    runs = sum(row['runs'] for row in fam['rows'].values())
    if not runs:
        return None
    if family == 'api':
        names = {str(node.get('name') or '').strip().lower() for node in index['nodes'].values()
                 if node.get('type') == 'APIEvent'} | index['data_types']
        joined = sum(row['runs'] for tag, row in fam['rows'].items() if tag in names)
    else:
        joined = sum(row['runs'] for tag, row in fam['rows'].items()
                     if tag in index['nodes'] and joins_export(family, index['nodes'][tag]))
    return round(joined / float(runs), 4)


def workload_call(args):
    code, result, stderr = _mcp.run_cli(args, timeout=600)
    if code != 0 or not isinstance(result, dict) or result.get('ok') is False:
        error = (result.get('error') or result.get('reason')) if isinstance(result, dict) else None
        return None, _mcp.redact(error or stderr[-300:] or 'workload request failed')[:300]
    return result, None


def workload_family(profile, window, family=None):
    """One workload-breakdown answer as {tag: {'runs', 'wu'}}: one row per family at the top level,
    one per workflow inside a family. Workflow API tags are folded to lower case: callers type the
    endpoint name as they please."""
    args = ['metrics', 'workload-breakdown', '--profile', profile, '--start', window['start'],
            '--end', window['end'], '--limit', str(WORKLOAD_ROW_LIMIT)]
    if family:
        args += ['--tag1', family]
    result, error = workload_call(args)
    if result is None:
        return {'ok': False, 'rows': {}, 'error': error}
    items = [item for item in result.get('items') or [] if isinstance(item, dict)]
    rows = {}
    for item in items:
        tag = str(item.get('tag') or '').strip()
        row = rows.setdefault(tag.lower() if family == 'api' else tag, {'runs': 0, 'wu': 0.0})
        row['runs'] += int(round(number(item.get('activity_count'))))
        row['wu'] += number(item.get('workload_used'))
    count = result.get('count')  # how many rows Bubble sent before the CLI cut them to --limit
    return {'ok': True, 'rows': rows, 'returned': len(items),
            'truncated': bool(items) and isinstance(count, int) and count > len(items)}


def day_of(value):
    """'YYYY-MM-DD' of a by-date bucket: ISO text, or seconds/ms/µs since the epoch."""
    if isinstance(value, str):
        text = value.strip()
        if re.match(r'^\d{4}-\d{2}-\d{2}', text):
            return text[:10]
        if not text.isdigit():
            return None
        value = int(text)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        seconds = value / 1e6 if value > 1e14 else value / 1e3 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime('%Y-%m-%d')
        except (OverflowError, OSError, ValueError):
            return None
    return None


def workload_days(profile, window):
    """The days of the window that have workload data (`metrics workload-by-date`)."""
    result, error = workload_call(['metrics', 'workload-by-date', '--profile', profile, '--start', window['start'],
                                   '--end', window['end'], '--granularity', 'day'])
    if result is None:
        return {'ok': False, 'error': error}
    per_day = defaultdict(float)
    for item in result.get('items') or []:
        if not isinstance(item, dict):
            continue
        day = day_of(item.get('date'))
        used = number(item.get('total_workload_used') or item.get('workload_used'))
        if not used:
            used = number(item.get('live_workload_used')) + number(item.get('test_workload_used'))
        if day:
            per_day[day] += used
    days = sorted(day for day, used in per_day.items() if used > 0)
    return {'ok': True, 'days_with_data': len(days), 'first_day': days[0] if days else None,
            'last_day': days[-1] if days else None, 'workload_used': round(sum(per_day.values()), 3)}


def effective_window(window, by_date):
    """Bubble keeps about 31 days of workload history and answers wider windows with the same data:
    the counts cover the days from the first one with data."""
    window['requested_days'] = window['days']
    if not by_date.get('ok'):
        window['days'] = min(window['days'], WORKLOAD_HISTORY_DAYS)
        window['note'] = ('workload-by-date failed: the effective window is unknown (Bubble keeps about %d days)'
                          % WORKLOAD_HISTORY_DAYS)
        return window
    first = by_date.get('first_day')
    if not first:
        return window
    window['data_from'] = first
    first_day = datetime.strptime(first, '%Y-%m-%d')
    if first_day > datetime.strptime(window['start'][:10], '%Y-%m-%d'):
        end = datetime.strptime(window['end'][:19], '%Y-%m-%dT%H:%M:%S')
        window['days'] = max(1, int(round((end - first_day).total_seconds() / 86400.0)))
    if window['requested_days'] > WORKLOAD_HISTORY_DAYS:
        window['note'] = ('Bubble keeps about %d days of workload history: wider windows answer the same data'
                          % WORKLOAD_HISTORY_DAYS)
    return window


def family_status(family, fam, top):
    """complete: a workflow missing from the rows did not run. Otherwise only the runs found count:
    the rows were cut (partial), cannot be checked against the family total (unverified), are
    missing while Bubble reports activity for the family (blind), or the call failed."""
    if not fam['ok']:
        return 'failed'
    fam['runs'] = sum(row['runs'] for row in fam['rows'].values())
    if fam['truncated']:
        return 'partial'
    if not top.get('ok') or top.get('blind'):
        return 'unverified'
    fam['family_total'] = total = (top['rows'].get(family) or {}).get('runs', 0)
    if total and not fam['runs']:
        return 'blind'
    if fam['runs'] < total * 0.98:  # rows missing (a cap on Bubble's side?): a zero may be a missing row
        return 'partial'
    return 'complete'


def combine(channels):
    """channels: (family, runs or None, workload used, coverage, reason). A positive count proves use;
    a zero needs every channel known."""
    if not channels:
        return {'runs': None, 'workload_used': None, 'coverage': 'not_metered', 'reason': 'not metered'}
    known = [ch for ch in channels if ch[1] is not None]
    unknown = [ch for ch in channels if ch[1] is None]
    out = {'runs': sum(ch[1] for ch in known), 'workload_used': round(sum(ch[2] for ch in known), 3)}
    if unknown and not out['runs']:
        codes = [ch[3] for ch in unknown]
        out.update(runs=None, coverage=next((code for code in COVERAGE_ORDER if code in codes), 'partial'),
                   reason='; '.join(sorted(set(ch[4] for ch in unknown if ch[4]))))
    else:
        out['coverage'] = 'partial' if unknown else 'complete'
    return out


def metered_on_its_own(node):
    """Backend custom events run inside the workflow that triggers them and never get a row of their
    own; page and reusable custom events that run server-side actions do, like page workflows."""
    return node.get('type') != 'CustomEvent' or node['scope'] != 'backend'


def triggering_roots(event_id, index):
    """The metered workflows a custom event runs inside: its callers, through chains of custom events
    (a page or reusable custom event on the way counts with its own row, and its callers too)."""
    roots, seen, stack = [], {event_id}, [event_id]
    while stack:
        for caller in sorted(index['callers'].get(stack.pop(), ())):
            node = index['nodes'].get(caller)
            if caller in seen or node is None:
                continue
            seen.add(caller)
            if metered_on_its_own(node):
                roots.append(node)
            if node.get('type') == 'CustomEvent':
                stack.append(caller)
    return roots


def node_label(node):
    if node['scope'] == 'backend':
        return node.get('name') or node['id']
    return '%s › %s' % (node.get('container') or '?', node.get('name') or node.get('type') or node['id'])


class WorkloadRuns:
    """Runs per workflow of the export, from the workload families (memoized by inner id)."""

    def __init__(self, index, families):
        self.index, self.families, self.memo = index, families, {}

    def channel(self, family, tag, zero_proves=True, reason=None):
        fam = self.families.get(family) or {'status': 'failed'}
        row = (fam.get('rows') or {}).get(tag)
        if row:
            return (family, row['runs'], row['wu'], None, None)
        if zero_proves and fam.get('status') == 'complete':
            return (family, 0, 0.0, None, None)
        if not zero_proves:
            return (family, None, 0.0, 'not_metered', reason)
        status = fam.get('status')
        return (family, None, 0.0, status, STATUS_REASON.get(status, 'the %s metrics are ' + str(status)) % family)

    def direct(self, node):
        """Runs of a workflow the metrics keep under its own tag, with the runs per family."""
        if node['id'] in self.memo:
            return self.memo[node['id']]
        channels = []
        if node['scope'] != 'backend':
            channels.append(self.channel('workflow', node['id'], zero_proves=False, reason=PAGE_WORKFLOW))
        elif node.get('type') in BACKEND_FAMILY:
            channels.append(self.channel(BACKEND_FAMILY[node['type']], node['id']))
            name = str(node.get('name') or '').strip().lower()
            exposed = node.get('exposed', True)
            if node['type'] == 'APIEvent' and name:
                if name in self.index['data_types']:
                    if exposed:  # Data API calls share the family, keyed by data-type name
                        channels.append(('api', None, 0.0, 'not_metered', 'its endpoint name is also a data type '
                                         'name: Workflow API and Data API calls share that tag'))
                elif exposed or name in ((self.families.get('api') or {}).get('rows') or {}):
                    # an unexposed workflow cannot run through the Workflow API, but calls to its name
                    # still say that something outside expects it
                    channels.append(self.channel('api', name))
        else:
            channels.append((None, None, 0.0, 'not_metered',
                             'a backend %s is not metered on its own' % node.get('type')))
        result = combine(channels)
        result['runs_by_family'] = {ch[0]: ch[1] for ch in channels if ch[0]}
        self.memo[node['id']] = result
        return result

    def custom_event(self, event_id):
        """A backend custom event runs inside the workflow that triggers it and is metered there: it counts
        the runs of the metered workflows that reach it, through chains of custom events — an upper bound,
        as the trigger action may be conditional. A page or reusable custom event adds its own row."""
        node = self.index['nodes'].get(event_id)
        if node is None:
            return {'runs': None, 'coverage': 'not_metered', 'reason': 'not found in the export'}
        roots = ([node] if metered_on_its_own(node) else []) + triggering_roots(event_id, self.index)
        if not roots:
            return {'runs': None, 'coverage': 'not_metered', 'reason': NO_CALLER}
        channels, via = [], []
        for node in roots:
            res = self.direct(node)
            channels.append((None, res['runs'], res['workload_used'] or 0.0, res.get('coverage'), res.get('reason')))
            via.append({'id': node['id'], 'name': node_label(node), 'scope': node['scope'],
                        'type': node.get('type'), 'runs': res['runs']})
        out = combine(channels)
        out.pop('workload_used', None)  # the callers' workload includes their own actions, not only this event's
        out['via'] = sorted(via, key=lambda caller: -(caller['runs'] or 0))[:10]
        return out


def workload_candidate(item, runs):
    kind = item['kind']
    if kind in ('backend_workflow', 'backend_custom_event') and not item.get('id'):
        res = {'runs': None, 'coverage': 'not_metered', 'reason': 'no inner id in the audit JSON'}
    elif kind == 'backend_workflow':
        # a workflow missing from this export is still joined by the id and name the audit knows
        node = runs.index['nodes'].get(item['id']) or {'id': item['id'], 'type': 'APIEvent', 'scope': 'backend',
                                                         'name': item.get('name'), 'exposed': False}
        res = dict(runs.direct(node), basis='direct')
    elif kind == 'backend_custom_event':
        res = dict(runs.custom_event(item['id']), basis='triggerer')
    else:
        res = {'runs': None, 'coverage': 'not_metered', 'reason': NOT_METERED.get(kind, 'not metered')}
    hits = res.pop('runs')
    return dict(item, hits=hits, first_seen=None, last_seen=None, **res)


def workload_evidence(args, audit, index, candidates, window):
    """Run counts from the workload metrics. Returns (report, exit code, printed summary)."""
    by_date = workload_days(args.profile, window)
    effective_window(window, by_date)
    top = workload_family(args.profile, window)
    # no family with any activity: an idle app or a blind endpoint, and either way no zero to trust
    top['blind'] = top['ok'] and not any(row['runs'] for row in top['rows'].values())
    families = {}
    for family in WORKLOAD_FAMILIES:
        fam = workload_family(args.profile, window, family)
        fam['status'] = family_status(family, fam, top)
        if fam['ok']:
            fam['joined_share'] = joined_share(family, fam, index)
            # rows that are not this export's workflows prove nothing about them: another export, or tags
            # that are not inner ids. Workflow API tags are typed by callers, so they are only reported.
            if (family != 'api' and fam['joined_share'] is not None and fam['joined_share'] < MIN_JOINED
                    and fam['status'] not in NOT_TRUSTED):
                fam['status'] = 'unjoined'
        families[family] = fam
    runs = WorkloadRuns(index, families)
    results = [workload_candidate(item, runs) for item in candidates]

    calls = [by_date, top] + list(families.values())
    idle = by_date.get('ok') and not by_date.get('first_day')
    active = [fam for name, fam in families.items() if name != 'api' and fam.get('runs')]
    mismatch = bool(active) and all(fam['status'] == 'unjoined' for fam in active)
    if not any(call.get('ok') for call in calls):
        code = 1  # every call failed: an expired session, most likely
        control = {'status': 'failed', 'reason': by_date.get('error') or top.get('error')}
    elif idle or top['blind'] or mismatch or all(fam['status'] in NOT_TRUSTED for fam in families.values()):
        coverage, reason = (
            ('blind', 'the workload metrics returned no data for the window') if idle else
            ('blind', 'the workload breakdown came back empty: an idle app or a blind endpoint') if top['blind'] else
            ('unjoined', 'the workload rows do not match the workflows of this export: pass the export this round '
                         'ran on') if mismatch else
            ('blind', 'no workload family can be trusted: they failed, came back empty while Bubble reports '
                      'activity, or do not match the workflows of this export'))
        downgrade([entry for entry in results if not entry.get('hits')], coverage, reason)
        code, control = EXIT_BLIND, {'status': 'failed', 'reason': reason}
    else:
        unchecked = sorted(name for name, fam in families.items() if fam['status'] != 'complete')
        code, control = 0, {'status': 'partial' if unchecked else 'passed'}
        if unchecked:
            control['reason'] = 'only the runs found count in: %s' % ', '.join(unchecked)
    control['check'] = ("the window has workload data; each family's rows add up to the total Bubble reports for "
                        "it, and most of its runs belong to workflows of the export")

    report = {
        'app': audit.get('app'),
        'app_version': 'all',  # the workload metrics count every version, live and test
        'window': window,
        'method': 'workload',
        'source': {
            'kind': 'workload',
            'by_date': by_date,
            'top_level': ({tag: row['runs'] for tag, row in sorted(top['rows'].items())} if top['ok']
                          else {'error': top.get('error')}),
            'families': {name: {key: fam[key] for key in ('status', 'returned', 'runs', 'family_total',
                                                          'joined_share', 'truncated', 'error') if key in fam}
                         for name, fam in families.items()},
            'positive_control': control,
        },
        'note': 'Run counts only, every version. Custom events count through the workflows that trigger them (an '
                'upper bound); pages and API Connector calls are not metered. "Did not run" covers this window, '
                'nothing more.',
        'candidates': results,
        'summary': summarize(results),
    }
    printed = {'source': 'workload', 'method': 'workload', 'window_days': window['days'],
               'requested_days': window['requested_days'], 'data_from': window.get('data_from'),
               **report['summary'], 'families': {name: fam['status'] for name, fam in families.items()},
               'positive_control': control['status']}
    if code == 1:
        printed['error'] = control.get('reason') or 'workload requests failed'
    elif code == EXIT_BLIND:
        printed['hint'] = 'zeros are unknown: ' + control['reason'] + '. Do not feed this file to bubble_audit.py.'
    return report, code, printed


# ------------------------------------------------------------------ main
def default_out(audit_json, source):
    stem = Path(audit_json).name.replace('_audit.json', '')
    return Path(audit_json).with_name('runtime-evidence__%s%s' % (stem, '.workload.json' if source == 'workload'
                                                                    else '.json'))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Runtime evidence for audit candidates (counts only).')
    ap.add_argument('audit_json')
    ap.add_argument('--profile', required=True)
    ap.add_argument('--source', choices=('logs', 'workload'), default='logs',
                    help='logs: server logs behind a positive control (default); workload: runs per workflow '
                         'from the workload metrics')
    ap.add_argument('--export', help='the .bubble this audit round ran on: required by workload (joins), names the '
                                     "logs' positive control (default: found through the audit's provenance)")
    ap.add_argument('--app-version', default='live',
                    help='logs only: logs are read-only, live is where real use happens (workload counts every '
                         'version)')
    ap.add_argument('--days', type=int,
                    help='window in days (default: 14 for logs, 30 for workload; Bubble keeps about 31 days of '
                         'workload)')
    ap.add_argument('--max-candidates', type=int, default=40, help='logs: cap for per-candidate queries')
    ap.add_argument('--control',
                    help='logs: a workflow name known to run in the window, used as the positive control')
    ap.add_argument('--out')
    args = ap.parse_args(argv)
    _mcp.check_id(args.profile, 'profile')
    audit = _mcp.load_json(args.audit_json)
    if not isinstance(audit, dict) or audit.get('summary_version', 1) < 2:
        raise SystemExit('need an audit JSON with tracker keys (bubble_audit.py --json, summary_version 2)')
    days = args.days if args.days is not None else (30 if args.source == 'workload' else 14)
    if days < 1:
        raise SystemExit('--days must be at least 1')
    export = args.export or find_export(audit)
    if args.source == 'workload' and not export:
        raise SystemExit('--source workload joins the metrics to the export: pass the .bubble this audit round '
                         'ran on (--export)')
    index = export_index(load_export(export, audit.get('app'))) if export else None
    candidates = candidates_from(audit, named_only=args.source == 'logs')
    end = datetime.now(timezone.utc).replace(microsecond=0)
    window = {'start': iso_z(end - timedelta(days=days)), 'end': iso_z(end), 'days': days}

    evidence = workload_evidence if args.source == 'workload' else logs_evidence
    report, code, printed = evidence(args, audit, index, candidates, window)
    out = Path(args.out) if args.out else default_out(args.audit_json, args.source)
    _mcp.write_private_json(out, report)
    print(json.dumps(dict({'ok': code == 0, 'evidence': str(out)}, **printed), indent=1, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
