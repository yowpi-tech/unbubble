#!/usr/bin/env python3
"""Runtime evidence for audit candidates: are they seen in the app's server logs?

    python3 runtime_evidence.py <app>-vN_audit.json --profile <app> [--days 14] [--app-version live]
        [--max-candidates 40] [--out audit/runtime-evidence__<app>-vN.json]

Static analysis of an export cannot see who calls an exposed backend workflow from outside, which
API Connector calls really run, or whether a page is opened by direct link. Bubble's server logs
can, within the plan's retention window. This script fetches the window ONCE (paginated) and
matches every candidate locally; when Bubble answers an empty window (busy apps need a search
term) it falls back to one `contains` query per candidate, capped by --max-candidates.

Only counts and first/last timestamps are written — never log rows, which carry user data.
"Not seen" only means not seen in the window: say so, and never treat it as proof of death.

stdlib only, Python 3.8+.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mcp  # noqa: E402


def candidates_from(audit):
    out = []
    pages = audit.get('pages') or {}
    for row in (pages.get('unused') or []) + (pages.get('referenced_by_url') or []):
        out.append({'key': row['key'], 'kind': 'page', 'name': row.get('name')})
    back = audit.get('backend') or {}
    for bucket in ('unused_hard', 'unused_transitive', 'webhook_verify'):
        for row in back.get(bucket) or []:
            out.append({'key': row['key'], 'kind': 'backend_workflow', 'name': row.get('wf_name'), 'bucket': bucket})
    for row in (audit.get('api_connector') or {}).get('unused') or []:
        out.append({'key': row['key'], 'kind': 'api_call', 'name': row.get('call'), 'provider': row.get('provider')})
    for row in (audit.get('workflow_audit') or {}).get('backend_custom_events_uncalled') or []:
        out.append({'key': row['key'], 'kind': 'backend_custom_event', 'name': row.get('name')})
    seen, unique = set(), []
    for item in out:
        if item.get('name') and item['key'] not in seen:
            seen.add(item['key'])
            unique.append(item)
    return unique


def row_time(row):
    for key in ('timestamp', 'created', 'created_at', 'time'):
        value = row.get(key) if isinstance(row, dict) else None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
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
    read: then only the hits it found prove anything."""
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


def ask_per_candidate(item, profile, app_version, window):
    """A server-side `contains` query for one candidate; zero hits count only when complete."""
    rows, info = fetch(profile, app_version, window['start'], window['end'], contains=item['name'],
                       max_pages=2, limit=20000)
    if rows is None:
        return {'hits': None, 'first_seen': None, 'last_seen': None, 'coverage': 'failed',
                'error': info.get('error')}
    found = tally(rows, item['name'])
    if not info['complete'] and found['hits'] == 0:
        found['hits'] = None
    found['coverage'] = 'complete' if info['complete'] else 'partial'
    return found


def main():
    ap = argparse.ArgumentParser(description='Server-log evidence for audit candidates (counts only).')
    ap.add_argument('audit_json')
    ap.add_argument('--profile', required=True)
    ap.add_argument('--app-version', default='live', help='logs are read-only; live is where real use happens')
    ap.add_argument('--days', type=int, default=14)
    ap.add_argument('--max-candidates', type=int, default=40, help='cap for per-candidate queries')
    ap.add_argument('--out')
    args = ap.parse_args()
    _mcp.check_id(args.profile, 'profile')
    audit = _mcp.load_json(args.audit_json)
    if not isinstance(audit, dict) or audit.get('summary_version', 1) < 2:
        raise SystemExit('need an audit JSON with tracker keys (bubble_audit.py --json, summary_version 2)')
    candidates = candidates_from(audit)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=args.days)
    window = {'start': start.isoformat().replace('+00:00', 'Z'), 'end': end.isoformat().replace('+00:00', 'Z'),
              'days': args.days}
    cap = max(0, args.max_candidates)

    rows, info = fetch(args.profile, args.app_version, window['start'], window['end'])
    results = []
    if rows:
        method = 'window' if info['complete'] else 'window (partial) + per-candidate'
        for item in candidates:
            results.append(dict(item, coverage='complete' if info['complete'] else 'partial',
                                **tally(rows, item['name'])))
        if not info['complete']:
            # a partial pull proves what it found; its zeros are asked again, one candidate at a time
            zeros = [entry for entry in results if entry['hits'] == 0]
            for entry in zeros[:cap]:
                entry.update(ask_per_candidate(entry, args.profile, args.app_version, window))
            for entry in zeros[cap:]:
                entry.update(hits=None, skipped='partial window, over --max-candidates')
    else:
        method = 'per-candidate'  # Bubble answers an empty window on busy apps, or the pull failed
        for item in candidates[:cap]:
            results.append(dict(item, **ask_per_candidate(item, args.profile, args.app_version, window)))
        for item in candidates[cap:]:
            results.append(dict(item, hits=None, first_seen=None, last_seen=None, skipped='over --max-candidates'))

    report = {
        'app': audit.get('app'),
        'app_version': args.app_version,
        'window': window,
        'method': method,
        'source': info,
        'note': 'Counts only. "Not seen" covers this window and the plan\'s log retention, nothing more.',
        'candidates': results,
        'summary': {
            'candidates': len(results),
            'seen': sum(1 for r in results if r.get('hits')),
            'not_seen': sum(1 for r in results if r.get('hits') == 0),
            'unknown': sum(1 for r in results if r.get('hits') is None),
        },
    }
    out = Path(args.out) if args.out else Path(args.audit_json).with_name(
        'runtime-evidence__%s.json' % Path(args.audit_json).name.replace('_audit.json', ''))
    _mcp.write_private_json(out, report)
    attempted = [r for r in results if r.get('coverage') in ('complete', 'partial', 'failed')]
    errors = sum(1 for r in attempted if r['coverage'] == 'failed')
    ok = not attempted or errors < len(attempted)  # every query failed: an expired session, most likely
    print(json.dumps({'ok': ok, 'evidence': str(out), 'method': method, 'window_days': args.days,
                      **report['summary'], 'failed_queries': errors,
                      **({'error': info.get('error')} if rows is None and info.get('error') else {})}, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
