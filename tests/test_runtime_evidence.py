"""skills/connect/scripts/runtime_evidence.py on synthetic data: the logs' positive control and the
workload source. Run from the repository root:

    python3 -m unittest discover -s tests

stdlib only. The connected-mode CLI is replaced by evidence_fixtures.FakeCLI; nothing is sent anywhere.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from evidence_fixtures import (ACME_FAMILIES, APP, PII, FakeCLI, acme_audit, acme_export, log_row, recent_days,
                               row)

import runtime_evidence as rev

CANDIDATES = 13  # what acme_audit() yields: 1 page, 3 backend workflows, 1 API call, 8 custom events


class EvidenceCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='unbubble-evidence-')
        self.addCleanup(shutil.rmtree, self.tmp)
        self.audit_path = self.write('acme-billing-v1_audit.json', acme_audit())
        self.export_path = self.write('acme-billing-test.bubble', acme_export())
        self.cli = FakeCLI()

    def write(self, name, payload):
        path = os.path.join(self.tmp, name)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        return path

    def run_script(self, *extra):
        out = os.path.join(self.tmp, 'evidence.json')
        stdout = io.StringIO()
        with mock.patch.object(rev._mcp, 'run_cli', self.cli), contextlib.redirect_stdout(stdout):
            code = rev.main([self.audit_path, '--profile', APP, '--out', out] + list(extra))
        with open(out, encoding='utf-8') as handle:
            written = handle.read()
        self.assertEqual(os.stat(out).st_mode & 0o777, 0o600, 'evidence files are owner-only')
        self.assertNotIn(PII, written + stdout.getvalue(), 'a log row leaked into the output')
        return code, json.loads(stdout.getvalue()), json.loads(written)

    @staticmethod
    def by_key(report):
        return {entry['key']: entry for entry in report['candidates']}


class LogsPositiveControl(EvidenceCase):
    """A logs answer of "ok, 0 rows, not truncated" proves nothing until a known-active workflow comes
    back with rows."""

    def test_blind_endpoint_makes_every_zero_unknown_and_exits_nonzero(self):
        # Every logs query answers ok / 0 rows / complete, while the workload metrics show
        # send_invoice running 250,000 times in the same window.
        self.cli = FakeCLI(families={'schedule_api_event': [row('aSend01', 250000, 9000.0)]})
        code, printed, report = self.run_script('--export', self.export_path)

        self.assertEqual(code, rev.EXIT_BLIND)
        self.assertFalse(printed['ok'])
        self.assertIn('hint', printed)
        self.assertEqual(report['summary'], {'candidates': CANDIDATES, 'seen': 0, 'not_seen': 0,
                                             'unknown': CANDIDATES})
        for entry in report['candidates']:
            self.assertIsNone(entry['hits'], entry['key'])
            self.assertEqual(entry['coverage'], 'blind')
            self.assertEqual(entry['reason'], rev.BLIND_LOGS)
        control = report['source']['positive_control']
        self.assertEqual(control['status'], 'failed')
        self.assertEqual(control['name'], 'send_invoice')  # named through the export
        self.assertEqual(control['source'], 'workload:schedule_api_event')
        self.assertEqual(control['runs_in_window'], 250000)
        self.assertEqual(printed['positive_control']['status'], 'failed')
        self.assertEqual(printed['positive_control']['name'], 'send_invoice')
        # the window pull and the control query, then nothing: a blind endpoint answers no candidate
        self.assertEqual(self.cli.logs_asked(), [None, 'send_invoice'])

    def test_control_with_rows_keeps_zeros_as_not_seen(self):
        self.cli = FakeCLI(logs={'send_invoice': [log_row('send_invoice')]},
                           families={'schedule_api_event': [row('aSend01', 250000, 9000.0)]})
        code, printed, report = self.run_script('--export', self.export_path)

        self.assertEqual(code, 0)
        self.assertTrue(printed['ok'])
        self.assertEqual(report['method'], 'per-candidate')
        self.assertEqual(report['summary']['not_seen'], CANDIDATES)
        for entry in report['candidates']:
            self.assertEqual((entry['hits'], entry['coverage']), (0, 'complete'), entry['key'])
        control = report['source']['positive_control']
        self.assertEqual((control['status'], control['checked_in'], control['hits']), ('passed', 'query', 1))
        self.assertEqual(len(self.cli.logs_asked()), 2 + CANDIDATES)  # window, control, one per candidate

    def test_complete_window_proves_its_zeros_when_the_control_is_in_it(self):
        self.cli = FakeCLI(logs={None: [log_row('send_invoice'), log_row('old_promo'), log_row('homepage')]},
                           families={'schedule_api_event': [row('aSend01', 250000)]})
        code, printed, report = self.run_script('--export', self.export_path)

        self.assertEqual(code, 0)
        self.assertEqual(report['method'], 'window')
        entries = self.by_key(report)
        self.assertEqual(entries['page:pPromo01']['hits'], 1)
        self.assertEqual(entries['workflow:aSync01']['hits'], 0)
        control = report['source']['positive_control']
        self.assertEqual((control['status'], control['checked_in'], control['window_hits']), ('passed', 'window', 1))
        self.assertEqual(self.cli.logs_asked(), [None])  # nothing asked again

    def test_window_missing_the_control_asks_its_zeros_again(self):
        self.cli = FakeCLI(logs={None: [log_row('old_promo')], 'send_invoice': [log_row('send_invoice')]},
                           families={'schedule_api_event': [row('aSend01', 250000)]})
        code, printed, report = self.run_script('--export', self.export_path)

        self.assertEqual(code, 0)
        self.assertEqual(report['method'], 'window (partial) + per-candidate')
        entries = self.by_key(report)
        self.assertEqual(entries['page:pPromo01']['hits'], 1)  # found in the window, kept
        self.assertEqual((entries['workflow:aSync01']['hits'], entries['workflow:aSync01']['coverage']),
                         (0, 'complete'))
        self.assertEqual(report['source']['positive_control']['window_hits'], 0)
        self.assertEqual(report['source']['positive_control']['checked_in'], 'query')
        asked = self.cli.logs_asked()
        self.assertEqual(asked[:2], [None, 'send_invoice'])
        self.assertNotIn('old_promo', asked)  # its hit came from the window
        self.assertIn('sync_ledger_v1', asked)

    def test_audit_json_names_the_control_without_the_export(self):
        # the busiest workflow has no name without the export; the next one is a candidate the audit names
        self.cli = FakeCLI(logs={'sync_ledger_v1': [log_row('sync_ledger_v1')]},
                           families={'schedule_api_event': [row('aSend01', 250000), row('aSync01', 120)]})
        code, printed, report = self.run_script()

        self.assertEqual(code, 0)
        control = report['source']['positive_control']
        self.assertEqual((control['name'], control['id'], control['status']), ('sync_ledger_v1', 'aSync01', 'passed'))
        self.assertEqual(self.by_key(report)['workflow:aSync01']['hits'], 1)

    def test_without_any_control_zeros_are_unverified(self):
        # no export, and the workload metrics only show a workflow nothing can name
        self.cli = FakeCLI(families={'schedule_api_event': [row('aSend01', 250000)]})
        code, printed, report = self.run_script()

        self.assertEqual(code, rev.EXIT_BLIND)
        self.assertEqual(report['summary']['unknown'], CANDIDATES)
        for entry in report['candidates']:
            self.assertEqual((entry['hits'], entry['coverage']), (None, 'unverified'), entry['key'])
            self.assertEqual(entry['reason'], rev.NO_CONTROL)
        control = report['source']['positive_control']
        self.assertEqual(control['status'], 'unavailable')
        self.assertIn('schedule_api_event', control['reason'])

    def test_candidate_with_hits_is_the_fallback_control(self):
        self.cli = FakeCLI(logs={'archive_invoices': [log_row('archive_invoices'), log_row('archive_invoices', 5)]},
                           families={'schedule_api_event': [row('aSend01', 250000)]})
        code, printed, report = self.run_script()

        self.assertEqual(code, 0)
        control = report['source']['positive_control']
        self.assertEqual((control['status'], control['source'], control['name'], control['hits']),
                         ('passed', 'candidate', 'archive_invoices', 2))
        self.assertEqual(report['summary']['seen'], 1)
        self.assertEqual(report['summary']['not_seen'], CANDIDATES - 1)

    def test_control_argument_skips_the_workload_lookup(self):
        self.cli = FakeCLI(logs={'nightly_rollup': [log_row('nightly_rollup')]})
        code, printed, report = self.run_script('--control', 'nightly_rollup')

        self.assertEqual(code, 0)
        self.assertEqual(self.cli.made('workload-breakdown'), [])
        control = report['source']['positive_control']
        self.assertEqual((control['source'], control['status']), ('--control', 'passed'))

    def test_every_query_failing_exits_1(self):
        self.cli = FakeCLI(families={'schedule_api_event': [row('aSend01', 250000)]}, fail={'logs'})
        code, printed, report = self.run_script('--export', self.export_path)

        self.assertEqual(code, 1)
        self.assertIn('error', printed)
        self.assertEqual(report['summary']['not_seen'], 0)

    def test_nothing_to_prove_needs_no_control(self):
        names = ['old_promo', 'sync_ledger_v1', 'archive_invoices', 'payment_webhook', 'Send digest',
                 'recalc_balance', 'rollup_detail', 'refresh_totals', 'post_payment', 'idle_cleanup',
                 'refund_note', 'legacy_hook', 'loop_a']
        self.cli = FakeCLI(logs={None: [log_row(name) for name in names]})
        code, printed, report = self.run_script()

        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['seen'], CANDIDATES)
        self.assertEqual(report['source']['positive_control'], {'status': 'not needed'})
        self.assertEqual(self.cli.made('workload-breakdown'), [])


class WorkloadSource(EvidenceCase):
    """Runs per workflow from `metrics workload-breakdown`, joined to the export family by family."""

    def setUp(self):
        super().setUp()
        self.cli = FakeCLI(families=ACME_FAMILIES)

    def test_joins_every_family(self):
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(code, 0)
        self.assertEqual((report['method'], report['app_version']), ('workload', 'all'))
        self.assertEqual(report['source']['positive_control']['status'], 'passed')
        self.assertEqual(set(printed['families'].values()), {'complete'})
        hits = {key: entry['hits'] for key, entry in self.by_key(report).items()}
        self.assertEqual(hits, {
            'workflow:aSync01': 120,         # schedule_api_event, by inner id
            'workflow:aArch01': 0,           # missing from a complete family: did not run
            'workflow:aHook01': 5,           # api, by endpoint name, case folded (3 + 2)
            'customevent:aCeBal01': 300,     # run_data_trigger_workflow: its database trigger
            'customevent:aCeDeep01': 30,     # recurring_event, through a chain of custom events
            'customevent:aCePage01': 75,     # workflow: the page workflow that triggers it
            'customevent:aCeChain01': 12,    # workflow, through a page custom event
            'customevent:aCeRefund01': 0,    # its only caller, a database trigger, never ran
            'customevent:aCeIdle01': None,   # its caller is a page workflow without runs: no proof
            'customevent:aCeOld01': None,    # nothing leads to it: not metered on its own
            'customevent:aCeLoopA': None,    # only a loop of custom events leads to it
            'page:pPromo01': None,           # pages are not metered
            'apicall:apiMail.cDig01': None,  # nor API Connector calls
        })
        entries = self.by_key(report)
        self.assertEqual(entries['workflow:aHook01']['runs_by_family'], {'schedule_api_event': 0, 'api': 5})
        self.assertEqual(entries['workflow:aSync01']['basis'], 'direct')
        self.assertEqual(entries['workflow:aSync01']['workload_used'], 3.5)
        self.assertEqual(entries['customevent:aCeBal01']['basis'], 'triggerer')
        self.assertEqual(entries['customevent:aCeBal01']['via'],
                         [{'id': 'aTrig01', 'name': 'on_invoice_change', 'scope': 'backend',
                           'type': 'DatabaseTriggerEvent', 'runs': 300}])
        self.assertEqual(entries['customevent:aCeChain01']['via'][0]['name'], 'billing › ButtonClicked')
        self.assertEqual(entries['customevent:aCeRefund01']['coverage'], 'complete')
        idle = entries['customevent:aCeIdle01']
        self.assertEqual(idle['coverage'], 'not_metered')
        self.assertIn('server-side', idle['reason'])
        self.assertIn('no workflow in the export leads', entries['customevent:aCeOld01']['reason'])
        self.assertEqual(entries['page:pPromo01']['coverage'], 'not_metered')
        for entry in report['candidates']:
            self.assertIsNone(entry['first_seen'])  # the breakdown has no timestamps
        # no logs at all, one call per family plus the totals and the days
        self.assertEqual(self.cli.made('logs'), [])
        self.assertEqual(len(self.cli.made('workload-breakdown')), 1 + len(rev.WORKLOAD_FAMILIES))
        for call in self.cli.made('workload-breakdown'):
            self.assertEqual(call[call.index('--limit') + 1], str(rev.WORKLOAD_ROW_LIMIT))

    def test_rows_missing_while_the_family_total_shows_activity_are_blind(self):
        top = FakeCLI(families=ACME_FAMILIES).totals()
        self.cli = FakeCLI(families=dict(ACME_FAMILIES, schedule_api_event=[]), top=top)
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(code, 0)  # the other families still answer
        self.assertEqual(printed['families']['schedule_api_event'], 'blind')
        self.assertEqual(printed['positive_control'], 'partial')
        entries = self.by_key(report)
        self.assertEqual((entries['workflow:aArch01']['hits'], entries['workflow:aArch01']['coverage']),
                         (None, 'blind'))
        self.assertEqual(entries['workflow:aHook01']['hits'], 5)  # its api calls still count
        self.assertEqual(entries['customevent:aCeBal01']['hits'], 300)

    def test_rows_short_of_the_family_total_keep_positives_only(self):
        top = [dict(entry, activity_count=1000000) if entry['tag'] == 'schedule_api_event' else entry
               for entry in FakeCLI(families=ACME_FAMILIES).totals()]
        self.cli = FakeCLI(families=ACME_FAMILIES, top=top)
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(printed['families']['schedule_api_event'], 'partial')
        entries = self.by_key(report)
        self.assertEqual((entries['workflow:aSync01']['hits'], entries['workflow:aSync01']['coverage']),
                         (120, 'complete'))
        self.assertEqual((entries['workflow:aArch01']['hits'], entries['workflow:aArch01']['coverage']),
                         (None, 'partial'))
        self.assertEqual(report['source']['families']['schedule_api_event']['family_total'], 1000000)

    def test_unnamed_backend_workflow_still_joins_by_id(self):
        export = acme_export()
        export['api']['b0'] = {'id': 'aAnon01', 'type': 'APIEvent', 'properties': {'expose': False}}
        audit = acme_audit()
        audit['backend']['unused_hard'].append({'wf_name': None, 'inner_id': 'aAnon01', 'folder': '(no folder)',
                                                'key': 'workflow:aAnon01'})
        self.audit_path = self.write('acme-billing-v1_audit.json', audit)
        path = self.write('acme-anon.bubble', export)
        scheduled = ACME_FAMILIES['schedule_api_event'] + [row('aAnon01', 7)]
        self.cli = FakeCLI(families=dict(ACME_FAMILIES, schedule_api_event=scheduled))
        code, printed, report = self.run_script('--source', 'workload', '--export', path)

        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['candidates'], CANDIDATES + 1)
        self.assertEqual(self.by_key(report)['workflow:aAnon01']['hits'], 7)
        # the logs are searched by name: an unnamed workflow is not their candidate
        self.assertNotIn('workflow:aAnon01', [item['key'] for item in rev.candidates_from(audit)])

    def test_rows_that_do_not_join_the_export_prove_nothing(self):
        # Bubble reports runs for workflows this export does not have: a missing row says nothing
        families = dict(ACME_FAMILIES, schedule_api_event=[row('aGone01', 900), row('aGone02', 100)])
        self.cli = FakeCLI(families=families)
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(code, 0)  # the other families still join
        self.assertEqual(printed['families']['schedule_api_event'], 'unjoined')
        shares = {name: fam['joined_share'] for name, fam in report['source']['families'].items()}
        self.assertEqual(shares['schedule_api_event'], 0.0)
        self.assertEqual(shares['run_data_trigger_workflow'], 1.0)
        self.assertEqual(shares['api'], 1.0)
        archive = self.by_key(report)['workflow:aArch01']
        self.assertEqual((archive['hits'], archive['coverage']), (None, 'unjoined'))
        self.assertIn('do not match the workflows of this export', archive['reason'])
        self.assertEqual(self.by_key(report)['customevent:aCeBal01']['hits'], 300)

    def test_export_of_the_wrong_round_makes_every_zero_unknown(self):
        # same app id, but none of the workflows the metrics count are in it
        stranger = dict(acme_export(), pages={},
                        api={'b1': {'id': 'aOther01', 'type': 'APIEvent', 'properties': {'wf_name': 'other'}}})
        path = self.write('stranger.bubble', stranger)
        code, printed, report = self.run_script('--source', 'workload', '--export', path)

        self.assertEqual(code, rev.EXIT_BLIND)
        self.assertIn('pass the export this round ran on', printed['hint'])
        self.assertEqual(report['summary']['not_seen'], 0)
        entries = self.by_key(report)
        self.assertEqual(entries['workflow:aArch01']['coverage'], 'unjoined')
        self.assertEqual(entries['workflow:aSync01']['hits'], 120)  # the audit's own id still has its runs

    def test_rows_cut_by_the_limit_are_partial(self):
        self.cli = FakeCLI(families=ACME_FAMILIES, counts={'run_data_trigger_workflow': 250000})
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(printed['families']['run_data_trigger_workflow'], 'partial')
        entries = self.by_key(report)
        self.assertEqual(entries['customevent:aCeBal01']['hits'], 300)  # a run found still counts
        self.assertIsNone(entries['customevent:aCeRefund01']['hits'])  # its caller may be a missing row

    def test_effective_window_starts_at_the_first_day_with_data(self):
        self.cli = FakeCLI(families=ACME_FAMILIES, days=recent_days(31, quiet_before=59))
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path, '--days', '90')

        window = report['window']
        first = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
        self.assertEqual(window['requested_days'], 90)
        self.assertEqual(window['data_from'], first)
        self.assertIn(window['days'], (30, 31))
        self.assertIn('31 days', window['note'])
        self.assertEqual((printed['data_from'], printed['requested_days']), (first, 90))
        self.assertEqual(report['source']['by_date']['days_with_data'], 31)

    def test_no_workload_data_makes_zeros_unknown_and_exits_nonzero(self):
        self.cli = FakeCLI(days=recent_days(0, quiet_before=31))
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(code, rev.EXIT_BLIND)
        self.assertFalse(printed['ok'])
        self.assertEqual(report['summary']['not_seen'], 0)
        self.assertEqual(self.by_key(report)['workflow:aArch01']['coverage'], 'blind')
        self.assertEqual(report['source']['positive_control']['status'], 'failed')

    def test_every_call_failing_exits_1(self):
        self.cli = FakeCLI(families=ACME_FAMILIES, fail={'workload-breakdown', 'workload-by-date'})
        code, printed, report = self.run_script('--source', 'workload', '--export', self.export_path)

        self.assertEqual(code, 1)
        self.assertIn('session expired', printed['error'])
        self.assertEqual(report['summary']['seen'] + report['summary']['not_seen'], 0)

    def test_workload_needs_the_export(self):
        with mock.patch.object(rev._mcp, 'run_cli', self.cli), self.assertRaises(SystemExit) as stop:
            rev.main([self.audit_path, '--profile', APP, '--source', 'workload'])
        self.assertIn('--export', str(stop.exception))
        self.assertEqual(self.cli.calls, [])

    def test_export_of_another_app_is_refused(self):
        other = self.write('other.bubble', dict(acme_export(), _id='another-app'))
        with mock.patch.object(rev._mcp, 'run_cli', self.cli), self.assertRaises(SystemExit) as stop:
            rev.main([self.audit_path, '--profile', APP, '--source', 'workload', '--export', other])
        self.assertIn('another-app', str(stop.exception))

    def test_default_output_names_keep_the_sources_apart(self):
        audit = os.path.join('audit', 'acme-billing-v3_audit.json')
        self.assertEqual(str(rev.default_out(audit, 'logs')),
                         os.path.join('audit', 'runtime-evidence__acme-billing-v3.json'))
        self.assertEqual(str(rev.default_out(audit, 'workload')),
                         os.path.join('audit', 'runtime-evidence__acme-billing-v3.workload.json'))


class WorkloadJoins(unittest.TestCase):
    """The joins on their own, without the CLI."""

    def runs(self, **overrides):
        families = {}
        for family in rev.WORKLOAD_FAMILIES:
            rows = {}
            for item in overrides.get(family, ACME_FAMILIES[family]):
                tag = item['tag'].lower() if family == 'api' else item['tag']
                entry = rows.setdefault(tag, {'runs': 0, 'wu': 0.0})
                entry['runs'] += item['activity_count']
                entry['wu'] += item['workload_used']
            status = overrides.get('status', {}).get(family, 'complete')
            families[family] = {'ok': True, 'rows': rows, 'status': status}
        return rev.WorkloadRuns(rev.export_index(acme_export()), families)

    def test_endpoint_named_like_a_data_type_is_unknown_without_other_runs(self):
        runs = self.runs()
        node = runs.index['nodes']['aInv01']
        self.assertTrue(node['exposed'])
        result = runs.direct(node)
        self.assertIsNone(result['runs'])  # the 50 calls tagged "invoice" may be the Data API's
        self.assertIn('data type', result['reason'])
        busy = self.runs(schedule_api_event=[row('aInv01', 4)]).direct(node)
        self.assertEqual((busy['runs'], busy['coverage']), (4, 'partial'))

    def test_exposed_endpoint_zero_needs_a_complete_api_family(self):
        node = self.runs().index['nodes']['aQuote01']
        self.assertEqual(self.runs().direct(node)['runs'], 0)
        self.assertEqual(self.runs(api=[row('PUBLIC_QUOTE', 9)]).direct(node)['runs'], 9)
        partial = self.runs(status={'api': 'partial'}).direct(node)
        self.assertEqual((partial['runs'], partial['coverage']), (None, 'partial'))

    def test_unexposed_workflow_ignores_an_incomplete_api_family(self):
        node = self.runs().index['nodes']['aArch01']
        result = self.runs(status={'api': 'failed'}).direct(node)
        self.assertEqual((result['runs'], result['runs_by_family']), (0, {'schedule_api_event': 0}))

    def test_custom_event_callers_and_chains(self):
        index = rev.export_index(acme_export())
        self.assertEqual(index['callers']['aCePage01'], {'wBill01'})
        self.assertEqual(index['callers']['wCe01'], {'wBill02'})
        # a page custom event on the way counts with its own row, and so do its callers
        roots = rev.triggering_roots('aCeChain01', index)
        self.assertEqual([node['id'] for node in roots], ['wCe01', 'wBill02'])
        # backend custom events never have rows of their own: a loop of them leads nowhere
        self.assertEqual(rev.triggering_roots('aCeLoopA', index), [])
        self.assertTrue({'invoice', 'customer'} <= index['data_types'])

    def test_page_custom_event_with_a_row_of_its_own_counts(self):
        runs = self.runs(workflow=[row('wBill02', 12), row('wCe01', 9)])
        chain = runs.custom_event('aCeChain01')
        self.assertEqual((chain['runs'], chain['coverage']), (21, 'complete'))  # an upper bound
        self.assertEqual([(caller['name'], caller['runs']) for caller in chain['via']],
                         [('billing › ButtonClicked', 12), ('billing › confirm_payment', 9)])
        own = runs.custom_event('wCe01')  # the page custom event itself
        self.assertEqual(own['runs'], 21)
        silent = self.runs(workflow=[]).custom_event('wCe01')
        self.assertEqual((silent['runs'], silent['coverage']), (None, 'not_metered'))

    def test_any_action_pointing_at_a_custom_event_is_a_caller(self):
        # an action type the audit does not list still runs the event: the export decides by target
        export = acme_export()
        export['api']['b3']['actions'] = {'0': {'type': 'SomeNewTriggerAction',
                                                'properties': {'custom_event': 'aCeOld01'}}}
        runs = rev.WorkloadRuns(rev.export_index(export), {
            'schedule_api_event': {'ok': True, 'status': 'complete', 'rows': {'aArch01': {'runs': 8, 'wu': 0.4}}}})
        result = runs.custom_event('aCeOld01')
        self.assertEqual((result['runs'], result['via'][0]['name']), (8, 'archive_invoices'))


if __name__ == '__main__':
    unittest.main()
