"""Synthetic fixtures for the runtime-evidence tests: an invented app, Acme Billing, and a stand-in for
the connected-mode CLI. Nothing here comes from a real app — every name, id and number is made up.

The fake CLI answers in the shapes the vendored befree-bubble-mcp CLI prints (parsed JSON), including
its quirks: an empty answer carries no `items` and a `count` of the response's keys, and workload
breakdown rows are {tag, workload_used, activity_count_label, activity_count}.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONNECT_SCRIPTS = os.path.join(REPO, 'skills', 'connect', 'scripts')
AUDIT_SCRIPTS = os.path.join(REPO, 'skills', 'audit', 'scripts')
DEMO_EXPORT = os.path.join(REPO, 'examples', 'demo-app', 'tidewater-rentals.bubble')
for folder in (CONNECT_SCRIPTS, AUDIT_SCRIPTS):
    if folder not in sys.path:
        sys.path.insert(0, folder)

APP = 'acme-billing'
PII = 'jane.doe@example.com'  # sits in every fake log row: it must never reach an output


def trigger(event_id, action='TriggerCustomEvent'):
    return {'0': {'type': action, 'properties': {'custom_event': event_id}}}


def acme_export():
    """Every caller kind a custom event can sit behind, and a scheduled workflow busy enough to be
    the logs' positive control (send_invoice)."""
    api = {
        'b1': {'id': 'aSend01', 'type': 'APIEvent', 'properties': {'wf_name': 'send_invoice', 'expose': False}},
        'b2': {'id': 'aSync01', 'type': 'APIEvent', 'properties': {'wf_name': 'sync_ledger_v1', 'expose': False}},
        'b3': {'id': 'aArch01', 'type': 'APIEvent', 'properties': {'wf_name': 'archive_invoices', 'expose': False}},
        'b4': {'id': 'aHook01', 'type': 'APIEvent',
               'properties': {'wf_name': 'payment_webhook', 'expose': False, 'parameter_def': 'auto'}},
        # no `expose` key: exposed. Its name is also a data type's, so Data API calls share its tag
        'b5': {'id': 'aInv01', 'type': 'APIEvent', 'properties': {'wf_name': 'invoice'}},
        'b6': {'id': 'aQuote01', 'type': 'APIEvent', 'properties': {'wf_name': 'public_quote'}},
        'b7': {'id': 'aTrig01', 'type': 'DatabaseTriggerEvent', 'properties': {'wf_name': 'on_invoice_change'},
               'actions': trigger('aCeBal01')},
        'b8': {'id': 'aNight01', 'type': 'RecurringEvent', 'properties': {'wf_name': 'nightly_rollup'},
               'actions': trigger('aCeRoll01')},
        'b9': {'id': 'aTrigQuiet01', 'type': 'DatabaseTriggerEvent', 'properties': {'wf_name': 'on_refund'},
               'actions': trigger('aCeRefund01')},
        'c1': {'id': 'aCeBal01', 'type': 'CustomEvent', 'properties': {'event_name': 'recalc_balance'}},
        'c2': {'id': 'aCeRoll01', 'type': 'CustomEvent', 'properties': {'event_name': 'rollup_step'},
               'actions': trigger('aCeDeep01')},
        'c3': {'id': 'aCeDeep01', 'type': 'CustomEvent', 'properties': {'event_name': 'rollup_detail'}},
        'c4': {'id': 'aCeOld01', 'type': 'CustomEvent', 'properties': {'event_name': 'legacy_hook'}},
        'c5': {'id': 'aCePage01', 'type': 'CustomEvent', 'properties': {'event_name': 'refresh_totals'}},
        'c6': {'id': 'aCeChain01', 'type': 'CustomEvent', 'properties': {'event_name': 'post_payment'}},
        'c7': {'id': 'aCeIdle01', 'type': 'CustomEvent', 'properties': {'event_name': 'idle_cleanup'}},
        'c8': {'id': 'aCeRefund01', 'type': 'CustomEvent', 'properties': {'event_name': 'refund_note'}},
        # two custom events that only trigger each other: no metered workflow ever reaches them
        'c9': {'id': 'aCeLoopA', 'type': 'CustomEvent', 'properties': {'event_name': 'loop_a'},
               'actions': trigger('aCeLoopB')},
        'c10': {'id': 'aCeLoopB', 'type': 'CustomEvent', 'properties': {'event_name': 'loop_b'},
                'actions': trigger('aCeLoopA')},
    }
    pages = {
        'p1': {'id': 'pBill01', 'name': 'billing', 'type': 'Page', 'elements': {}, 'workflows': {
            'w1': {'id': 'wBill01', 'type': 'ButtonClicked', 'properties': {'element_id': 'eBtn01'},
                   'actions': trigger('aCePage01', 'TriggerBackendCustomEvent')},
            'w2': {'id': 'wBill02', 'type': 'ButtonClicked', 'properties': {'element_id': 'eBtn02'},
                   'actions': trigger('wCe01')},
            'w3': {'id': 'wCe01', 'type': 'CustomEvent', 'properties': {'event_name': 'confirm_payment'},
                   'actions': trigger('aCeChain01', 'TriggerBackendCustomEvent')},
            'w4': {'id': 'wBill03', 'type': 'PageLoaded', 'properties': {},
                   'actions': trigger('aCeIdle01', 'TriggerBackendCustomEvent')},
        }},
        'p2': {'id': 'pPromo01', 'name': 'old_promo', 'type': 'Page', 'elements': {}, 'workflows': {}},
    }
    return {'_id': APP, 'api': api, 'pages': pages, 'element_definitions': {}, 'mobile_views': {},
            'user_types': {'invoice': {'display': 'Invoice'}, 'customer': {'display': 'Customer'}},
            'settings': {'client_safe': {'exposes_wf_api': True}}}


def acme_audit():
    """An audit JSON (summary_version 2) written by hand. A real audit lists only custom events
    nothing triggers; these list one behind every caller kind, to exercise the resolver."""
    events = [('aCeBal01', 'recalc_balance'), ('aCeDeep01', 'rollup_detail'), ('aCePage01', 'refresh_totals'),
              ('aCeChain01', 'post_payment'), ('aCeIdle01', 'idle_cleanup'), ('aCeRefund01', 'refund_note'),
              ('aCeOld01', 'legacy_hook'), ('aCeLoopA', 'loop_a')]
    return {
        'app': APP,
        'summary_version': 2,
        'pages': {'unused': [{'name': 'old_promo', 'inner_id': 'pPromo01', 'key': 'page:pPromo01'}],
                  'referenced_by_url': []},
        'backend': {
            'unused_hard': [{'wf_name': 'sync_ledger_v1', 'inner_id': 'aSync01', 'folder': '(no folder)',
                             'key': 'workflow:aSync01'}],
            'unused_transitive': [{'wf_name': 'archive_invoices', 'inner_id': 'aArch01', 'folder': '(no folder)',
                                   'key': 'workflow:aArch01'}],
            'webhook_verify': [{'wf_name': 'payment_webhook', 'inner_id': 'aHook01', 'folder': '(no folder)',
                                'key': 'workflow:aHook01', 'expose': False, 'initialized': False}],
        },
        'api_connector': {'unused': [{'provider': 'Mail Service (demo)', 'call': 'Send digest',
                                      'ref': 'apiMail.cDig01', 'key': 'apicall:apiMail.cDig01'}]},
        'workflow_audit': {'backend_custom_events_uncalled': [
            {'id': event_id, 'name': name, 'folder': None, 'key': 'customevent:' + event_id, 'scope': 'backend'}
            for event_id, name in events]},
    }


def row(tag, runs, workload=1.0):
    """One workload-breakdown row."""
    return {'tag': tag, 'workload_used': workload, 'activity_count_label': 'Run', 'activity_count': runs}


ACME_FAMILIES = {
    'schedule_api_event': [row('aSend01', 250000, 9000.0), row('aSync01', 120, 3.5)],
    'run_data_trigger_workflow': [row('aTrig01', 300, 12.0)],
    'recurring_event': [row('aNight01', 30, 1.0)],
    'workflow': [row('wBill01', 75, 2.0), row('wBill02', 12, 0.5)],
    # endpoint names as callers typed them, and Data API calls keyed by data type
    'api': [row('Payment_Webhook', 3, 0.3), row('payment_webhook', 2, 0.2), row('invoice', 50, 5.0),
            row('customer', 7, 0.7)],
}


def log_row(name, minutes_ago=60):
    """A Jetstream-like log row; it carries user data, which must never leave the script."""
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {'created': int(created.timestamp() * 1000), 'message': 'running event', 'display': name,
            'user': PII, 'body': 'Invoice paid by Jane Doe'}


def recent_days(count, workload=100.0, quiet_before=0):
    """workload-by-date rows from today back `count` days with workload, then `quiet_before` older
    days without any."""
    today = datetime.now(timezone.utc).date()
    rows = []
    for offset in range(count + quiet_before):
        used = workload if offset < count else 0.0
        rows.append({'date': (today - timedelta(days=offset)).isoformat() + 'T00:00:00.000Z', 'platform': 'web',
                     'total_workload_used': used, 'live_workload_used': used * 0.9,
                     'test_workload_used': used * 0.1})
    return rows


def answer(items, logs=False, count=None):
    """The CLI's JSON: `items` only when Bubble sent rows, otherwise a `data` stub whose key count
    becomes `count` (the CLI's own compaction); plus the logs' pagination fields."""
    out = {'ok': True, 'profile': APP, 'app_id': APP, 'status': 200}
    if items:
        out.update(count=len(items) if count is None else count, items=list(items))
    else:
        out.update(count=1, data={'rows': []})
    if logs:
        out.update(row_count=len(items), paginated=True, pages_fetched=1, max_pages=1, truncated=False,
                   stop_reason='reached_end_of_window', app_version='live')
    return out


class FakeCLI:
    """Stands in for _mcp.run_cli(args, timeout): canned answers per command; every call is kept."""

    def __init__(self, logs=None, families=None, top=None, days=None, counts=None, fail=()):
        self.logs = logs or {}          # --contains value (None: the window pull) -> log rows
        self.families = families or {}  # --tag1 -> breakdown rows
        self.top = top                  # top-level rows; None: totals of the families
        self.days = recent_days(31) if days is None else days
        self.counts = counts or {}      # --tag1 -> the `count` Bubble reports (rows cut by --limit)
        self.fail = set(fail)           # subcommands that answer like an expired session
        self.calls = []

    def __call__(self, args, timeout=1800):
        args = [str(arg) for arg in args]
        self.calls.append(args)
        command = args[1]
        if command in self.fail:
            return 1, None, 'RuntimeError: Bubble session expired: received HTML instead of JSON.'

        def option(name):
            return args[args.index(name) + 1] if name in args else None

        if command == 'logs':
            return 0, answer(self.logs.get(option('--contains'), []), logs=True), ''
        if command == 'workload-breakdown':
            family = option('--tag1')
            if family:
                return 0, answer(self.families.get(family, []), count=self.counts.get(family)), ''
            return 0, answer(self.totals() if self.top is None else self.top), ''
        if command == 'workload-by-date':
            return 0, answer(self.days), ''
        raise AssertionError('unexpected CLI call: %r' % args)

    def totals(self):
        return [{'tag': family, 'workload_used': sum(r['workload_used'] for r in rows),
                 'activity_count_label': 'Run', 'activity_count': sum(r['activity_count'] for r in rows)}
                for family, rows in self.families.items() if rows]

    def logs_asked(self):
        """The --contains of every logs query, in order (None: the window pull)."""
        return [call[call.index('--contains') + 1] if '--contains' in call else None
                for call in self.calls if call[1] == 'logs']

    def made(self, command):
        return [call for call in self.calls if call[1] == command]
