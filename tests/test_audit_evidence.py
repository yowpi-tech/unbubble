"""Runtime evidence in the audit report (skills/audit/scripts/bubble_audit.py --evidence) and in the
cleanup plan (skills/connect/scripts/cleanup_plan.py): every label follows the evidence file's source,
so workflow runs from the workload metrics are never presented as server logs, and several files
merge without an unknown hiding a result. Run from the repository root:

    python3 -m unittest discover -s tests

Runs on the fictional demo export in examples/demo-app. stdlib only.
"""
import contextlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from evidence_fixtures import AUDIT_SCRIPTS, DEMO_EXPORT

import bubble_audit
import cleanup_plan

DEMO_APP = 'tidewater-rentals'

WORKLOAD = {
    'app': DEMO_APP, 'app_version': 'all', 'method': 'workload',
    'window': {'start': '2026-08-15T12:00:00Z', 'end': '2026-10-14T12:00:00Z', 'days': 31, 'requested_days': 60,
               'data_from': '2026-09-13'},
    'candidates': [
        {'key': 'workflow:aSync01', 'hits': 125000, 'basis': 'direct', 'coverage': 'complete'},
        {'key': 'workflow:aArch01', 'hits': 0, 'basis': 'direct', 'coverage': 'complete'},
        {'key': 'customevent:aCe01', 'hits': 1200, 'basis': 'triggerer', 'coverage': 'complete'},
        {'key': 'page:pAdm01', 'hits': None, 'coverage': 'not_metered'},
    ],
}
LOGS = {
    'app': DEMO_APP, 'app_version': 'live', 'method': 'per-candidate',
    'window': {'start': '2026-09-30T12:00:00Z', 'end': '2026-10-14T12:00:00Z', 'days': 14},
    'candidates': [
        {'key': 'page:pAdm01', 'hits': 4, 'first_seen': '2026-10-01T08:00:00Z', 'last_seen': '2026-10-13T09:12:00Z',
         'coverage': 'complete'},
        {'key': 'workflow:aSync01', 'hits': 0, 'coverage': 'complete'},
        {'key': 'page:pPromo23', 'hits': None, 'coverage': 'blind'},
    ],
}


def badge(report, key):
    """(text, tooltip) of the evidence badge in the deletion checkbox cell of a tracker key."""
    match = re.search(r'data-key="%s"[^>]*>(?:<span class=\'vbadge evtag [^\']*\' title="([^"]*)">([^<]*)</span>)?'
                      % re.escape(key), report)
    if not match or match.group(2) is None:
        return None
    return match.group(2), html.unescape(match.group(1))


class ReportLabels(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='unbubble-audit-evidence-')
        self.addCleanup(shutil.rmtree, self.tmp)

    def evidence(self, name, payload):
        path = os.path.join(self.tmp, name)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        return path

    def audit(self, *evidence, lang='en'):
        out, summary = os.path.join(self.tmp, 'report.html'), os.path.join(self.tmp, 'audit.json')
        args = [sys.executable, os.path.join(AUDIT_SCRIPTS, 'bubble_audit.py'), DEMO_EXPORT, '--out', out,
                '--json', summary, '--lang', lang, '--date', '2026-10-14']
        for path in evidence:
            args += ['--evidence', path]
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
        with open(out, encoding='utf-8') as handle:
            report = handle.read()
        with open(summary, encoding='utf-8') as handle:
            return report, json.load(handle), proc.stdout

    def test_workload_file_is_labelled_as_runs_never_as_logs(self):
        report, summary, stdout = self.audit(self.evidence('workload.json', WORKLOAD))

        self.assertEqual(badge(report, 'workflow:aSync01')[0], 'runs: 125,000×')
        self.assertEqual(badge(report, 'workflow:aArch01')[0], 'runs: 0')
        self.assertEqual(badge(report, 'page:pAdm01')[0], 'runs: ?')
        text, tooltip = badge(report, 'customevent:aCe01')
        self.assertEqual(text, 'runs: 1,200×')
        self.assertIn('upper bound', tooltip)  # counted through its caller
        self.assertNotIn('">logs:', report)  # no badge reads as server logs
        self.assertNotIn('Server logs of', report)
        self.assertIn("Workflow runs in Bubble's workload metrics (all versions), 31 days up to 2026-10-14 "
                      '(data from 2026-09-13)', html.unescape(report))
        self.assertIn('2 ran per the workload metrics', stdout)
        self.assertNotIn('logs (review before deleting)', stdout)
        self.assertEqual(summary['runtime_evidence']['by_key']['workflow:aSync01']['kind'], 'runs')

    def test_workload_file_in_portuguese(self):
        report, _, _ = self.audit(self.evidence('workload.json', WORKLOAD), lang='pt')

        self.assertEqual(badge(report, 'workflow:aSync01')[0], 'execuções: 125.000×')
        self.assertEqual(badge(report, 'workflow:aArch01')[0], 'execuções: 0')
        self.assertEqual(badge(report, 'page:pAdm01')[0], 'execuções: ?')
        self.assertIn('Execuções de workflows nas métricas de workload', report)
        self.assertNotIn('Logs do servidor', report)

    def test_logs_file_keeps_logs_labels(self):
        report, summary, stdout = self.audit(self.evidence('logs.json', LOGS))

        text, tooltip = badge(report, 'page:pAdm01')
        self.assertEqual(text, 'logs: 4×')
        self.assertIn('2026-10-13T09:12', tooltip)
        self.assertEqual(badge(report, 'workflow:aSync01')[0], 'logs: 0')
        self.assertEqual(badge(report, 'page:pPromo23')[0], 'logs: ?')
        self.assertIn('Server logs of <span class="mono">live</span>, 14 days', report)
        self.assertIn('1 seen in the live logs', stdout)

    def test_files_merge_without_an_unknown_hiding_a_result(self):
        files = [self.evidence('logs.json', LOGS), self.evidence('workload.json', WORKLOAD)]
        for order in (files, files[::-1]):
            report, summary, stdout = self.audit(*order)
            # the workload cannot see pages: the logs' hit stays, with the logs' label
            self.assertEqual(badge(report, 'page:pAdm01')[0], 'logs: 4×')
            # seen in one source beats not seen in another
            self.assertEqual(badge(report, 'workflow:aSync01')[0], 'runs: 125,000×')
            self.assertEqual(badge(report, 'page:pPromo23')[0], 'logs: ?')
            evidence = summary['runtime_evidence']
            self.assertEqual([src['kind'] for src in evidence['sources']], ['logs', 'runs'])
            self.assertEqual(evidence['by_key']['page:pAdm01']['kind'], 'logs')
            self.assertIn('Server logs of', report)
            self.assertIn("Workflow runs in Bubble's workload metrics", html.unescape(report))
            self.assertIn('seen in the live logs', stdout)
            self.assertIn('ran per the workload metrics', stdout)


class LoadEvidence(unittest.TestCase):

    def test_kind_follows_the_method(self):
        self.assertEqual(bubble_audit.evidence_kind('workload'), 'runs')
        for method in ('window', 'window (partial) + per-candidate', 'per-candidate', None):
            self.assertEqual(bubble_audit.evidence_kind(method), 'logs')

    def test_counts_per_source_after_the_merge(self):
        tmp = tempfile.mkdtemp(prefix='unbubble-load-evidence-')
        self.addCleanup(shutil.rmtree, tmp)
        paths = []
        for name, payload in (('logs.json', LOGS), ('workload.json', WORKLOAD)):
            paths.append(os.path.join(tmp, name))
            with open(paths[-1], 'w', encoding='utf-8') as handle:
                json.dump(payload, handle)
        evidence = bubble_audit.load_evidence(paths, DEMO_APP)
        counts = {src['kind']: src['counts'] for src in evidence['sources']}
        self.assertEqual(counts['logs'], {'seen': 1, 'not_seen': 0, 'unknown': 1})   # pAdm01, pPromo23
        self.assertEqual(counts['runs'], {'seen': 2, 'not_seen': 1, 'unknown': 0})   # aSync01, aCe01, aArch01
        self.assertEqual(evidence['counts'], {'seen': 3, 'not_seen': 1, 'unknown': 1})
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertIsNone(bubble_audit.load_evidence(paths, 'another-app'))
        self.assertIn('ignored', stderr.getvalue())


class CleanupPlanSeenAtRuntime(unittest.TestCase):

    def test_items_that_run_stay_out_of_the_plan_with_their_source(self):
        rows = [('sync_ledger_v1', 'aSync01'), ('archive_invoices', 'aArch01'), ('export_csv', 'aCsv01')]
        audit = {
            'app': 'acme-billing', 'summary_version': 2,
            'backend': {'unused_hard': [{'wf_name': name, 'inner_id': iid, 'folder': 'Ops', 'key': 'workflow:' + iid}
                                        for name, iid in rows]},
            'runtime_evidence': {'by_key': {
                'workflow:aSync01': {'hits': 125000, 'kind': 'runs'},
                'workflow:aArch01': {'hits': 0, 'kind': 'runs'},
                'workflow:aCsv01': {'hits': 3, 'kind': 'logs', 'last_seen': '2026-10-13T09:12:00Z'},
            }},
        }
        plan = cleanup_plan.build_plan(audit, profile='acme-billing--cleanup', app_version='cleanup', deleted=set(),
                                       kept=set(), applied=set(), include_review=False, include_destructive=False)
        self.assertEqual({item['key']: item['source'] for item in plan['seen_at_runtime']},
                         {'workflow:aSync01': 'runs', 'workflow:aCsv01': 'logs'})
        self.assertEqual([item['key'] for item in plan['manual']], ['workflow:aArch01'])
        self.assertEqual(plan['skipped'], {'seen at runtime (runtime evidence)': 2})
        markdown = cleanup_plan.to_markdown(plan)
        self.assertIn('## Seen at runtime — not planned (2)', markdown)
        self.assertIn('sync_ledger_v1: ran 125000× (workload metrics)', markdown)
        self.assertIn('export_csv: 3× in the server logs (last 2026-10-13T09:12:00Z)', markdown)


if __name__ == '__main__':
    unittest.main()
