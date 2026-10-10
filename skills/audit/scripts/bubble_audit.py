#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bubble_audit.py — static "unused entities" audit for a Bubble.io app export (.bubble).

Finds, with confidence levels:
  1. Pages         never navigated to / referenced internally
  2. Reusables     element definitions never placed anywhere
  3. Backend WFs   API workflows neither exposed as an endpoint nor scheduled/triggered
  4. Option Sets   not referenced by any expression, field, element or workflow
  5. Plugins       installed but with no element/action/API-call/config usage
  6. Styles        not referenced by any element's `style` property

A .bubble export is one giant single-line JSON. Every cross-reference between
entities is stored as the target's id inside a quoted string (dict key or value),
and ids are globally unique — so counting quoted-token occurrences (minus an
entity's own definition) is a collision-safe "is it referenced?" test. Where a
first-class reference field exists (custom_id, api_event, option.<name>, style),
we use it directly and add the quoted-token count as a safety net.

Usage:
  python3 bubble_audit.py path/to/export.bubble
  python3 bubble_audit.py export.bubble --out report.html --json results.json
  python3 bubble_audit.py export.bubble --pages-csv page_audit.csv --lang pt

The script is dependency-free (Python 3.8+ standard library only).
"""
import argparse, csv, html, json, os, re, sys
from collections import Counter, defaultdict

# ------------------------------------------------------------------ helpers
def log(*a):
    print(*a, file=sys.stderr)

# Sections that represent real, live app content (used for usage scanning).
# Excluded on purpose: _index (editor metadata: id_to_path / issues_list),
# comments (editor notes), holding_pen (the deleted-elements bin — referencing
# something from the trash must NOT count as "used"), screenshot, snapshots.
CONTENT_KEYS = ['pages', 'element_definitions', 'api', 'option_sets', 'styles',
                'settings', 'user_types', 'mobile_views']

def build_index(data):
    """Return (content_raw, quoted_counter) for usage scanning."""
    content = {k: data.get(k) for k in CONTENT_KEYS}
    content_raw = json.dumps(content, separators=(',', ':'))
    quoted = Counter(re.findall(r'"([A-Za-z0-9_]+)"', content_raw))
    return content_raw, quoted

def refs_elsewhere(idstr, own_obj, quoted):
    """Quoted occurrences of idstr across content MINUS those inside its own object."""
    if not idstr:
        return 0
    total = quoted.get(idstr, 0)
    own = json.dumps(own_obj, separators=(',', ':'))
    return total - own.count('"' + idstr + '"')

def walk(o, fn):
    """Depth-first walk calling fn(node) on every dict."""
    if isinstance(o, dict):
        fn(o)
        for v in o.values():
            walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            walk(v, fn)

def build_def_names(data):
    """Reusable-definition inner `id` -> its CURRENT name. Used to label reusable
    instances (CustomElement) by the live definition rather than a stale snapshot."""
    out = {}
    for dv in (data.get('element_definitions') or {}).values():
        if isinstance(dv, dict) and dv.get('id'):
            out[dv['id']] = dv.get('name')
    return out

_INSTANCE_LETTER = re.compile(r'\s+([A-Z]{1,6})$')
_BBCODE = re.compile(r'\[/?[a-zA-Z][^\]]*\]')  # Bubble rich-text markup: [ul] [li] [color=…] …

def _element_content(el):
    """The static caption / text / placeholder the Bubble editor shows for a
    content-bearing element (Button caption, Text content, Input placeholder), or
    None. These live in `properties`, never in default_name. Rich-text markup is
    stripped and whitespace collapsed; purely-dynamic content returns None."""
    props = el.get('properties') if isinstance(el.get('properties'), dict) else {}
    for key in ('text', 'caption', 'placeholder'):
        v = props.get(key)
        s = None
        if isinstance(v, str):
            s = v
        elif isinstance(v, dict) and isinstance(v.get('entries'), dict):
            z = v['entries'].get('0')  # entries.0 = the leading static run of a TextExpression
            s = z if isinstance(z, str) else None
        if s and s.strip():
            s = ' '.join(_BBCODE.sub('', s).split())
            if s:
                return s
    return None

def _type_word(el):
    """Human element-type word ("Button", "Text", "MultiDropdown") — the default_name
    with its trailing instance letters stripped; falls back to the raw `type`."""
    dn = el.get('default_name')
    if isinstance(dn, str) and dn:
        return _INSTANCE_LETTER.sub('', dn).strip() or dn
    t = el.get('type')
    return t if isinstance(t, str) else ''

def editor_name(el, fallback=None, def_names=None):
    """The element name AS SHOWN IN THE BUBBLE EDITOR's element tree.

    Resolution order (mirrors what the editor displays):
      1. Reusable-element INSTANCE (type CustomElement) -> the reusable's CURRENT
         name via `properties.custom_id` (+ the frozen instance letter). Its baked
         default_name/name/custom_definition_name all snapshot at placement and go
         STALE when the definition is renamed (a large share of instances carry a stale
         default_name; `name` is stale for most too), so the live definition is the
         only reliable label. Drops genuine per-instance renames (a small minority,
         string-indistinguishable from stale auto-names).
      2. An explicit user `name` (the custom label, e.g. "date Start", "g list").
      3. A content-bearing element with NO custom name -> "<Type> <caption/text/
         placeholder>" (e.g. a button captioned "Issue receipt" shows as "Button
         Issue receipt"). The editor derives this live from `properties`; it is NOT
         in default_name. Confirmed on real exports: stored names match "<Type> <caption>"
         far more often than the bare caption. Without this, an unnamed button reads as "Button H".
      4. `default_name` ("Button H", "Group A") for content-less unnamed elements.

    Empty strings are treated as absent. def_names (inner-id -> current reusable
    name) enables step 1; omit it to skip reusable resolution."""
    if not isinstance(el, dict):
        return fallback
    if def_names:
        props = el.get('properties') if isinstance(el.get('properties'), dict) else {}
        cid = props.get('custom_id')
        cur = def_names.get(cid) if cid else None
        if cur and cur.strip():
            cur = cur.rstrip()
            m = _INSTANCE_LETTER.search(el.get('default_name') or '')
            return cur + (' ' + m.group(1) if m else '')
    n = el.get('name')
    if n:
        return n
    content = _element_content(el)
    if content:
        tw = _type_word(el)
        label = (tw + ' ' + content).strip() if tw else content
        return label if len(label) <= 60 else label[:59].rstrip() + '…'
    return el.get('default_name') or el.get('custom_definition_name') or fallback

def app_domains(data):
    """The app's own web domains, used to recognize internal page URLs."""
    cs = data.get('settings', {}).get('client_safe', {}) or {}
    doms = []
    td = cs.get('app_topdomain')
    if isinstance(td, str) and '.' in td:
        doms.append(td)
    appid = data.get('_id')
    if isinstance(appid, str) and appid:
        doms.append(appid + '.bubbleapps.io')  # Bubble default domain
    return doms

# A string leaf is worth searching for page-URL references if it looks like a path/tag/script.
_URLISH = re.compile(r'/|<[a-zA-Z!/]|location\.|window\.|href|src=|\.io|\.com|\.app|http')

def build_url_corpus(data):
    """Concatenate every string leaf that looks like a URL/HTML/JS fragment.

    Pages can be linked by NAME (their URL slug) inside free text that the id-based
    navigation scan never sees: hardcoded Link/OpenURL URLs, Run-JavaScript action code,
    HTML embed elements, per-page html_header, and app custom headers. That content is
    stored inside nested expression structures, so we collect string leaves recursively.
    """
    parts = []
    def rec(o):
        if isinstance(o, str):
            if len(o) > 2 and _URLISH.search(o):
                parts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec({k: data.get(k) for k in CONTENT_KEYS})
    return '\n'.join(parts)

# A string leaf worth searching for data field/type references (JS/HTML/code blocks).
_CODEISH = re.compile(r'<[a-zA-Z/!]|function|=>|\.get\(|location\.|window\.|document\.|http|\bvar\b|\blet\b|\bconst\b|bubble|\$\(|;')

def build_script_corpus(data):
    """String leaves that look like JS/HTML/code — where a data field/type could be referenced
    by name outside Bubble's structured expressions (Run JavaScript, HTML embeds, headers)."""
    parts = []
    def rec(o):
        if isinstance(o, str):
            if len(o) > 12 and _CODEISH.search(o):
                parts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)
    rec({k: data.get(k) for k in ('pages', 'element_definitions', 'api', 'mobile_views')})
    return '\n'.join(parts)

# ------------------------------------------------------------------ analyses
def analyze_pages(data, quoted, url_corpus, domains):
    pages = data.get('pages', {})
    # entry points reachable by definition (system pages / URL roots)
    SYSTEM = {'index', '404', 'reset_pw', 'login'}
    OLD_RE = re.compile(r'(_old|_bkp|_backup|_copy|_test|_v\d|_deprecated|_delete|❌|old_|test_|copy_| copy|_bak|_legacy|_20\d{2})', re.I)
    # regex prefix that matches this app's page-URL form: (www.)?<domain>/[version-xxx/]
    dom_alt = '|'.join(re.escape(d) for d in domains) if domains else r'(?!x)x'
    APP_URL = r'(?:www\.)?(?:' + dom_alt + r')/(?:version-[A-Za-z0-9_-]+/)?'
    rows = []
    for wk, pv in pages.items():
        if not isinstance(pv, dict):
            continue
        iid = pv.get('id')
        name = pv.get('name')
        r = refs_elsewhere(iid, pv, quoted)
        is_system = name in SYSTEM
        no_id_nav = (r <= 0 and not is_system)
        # For no-id-nav pages, also look for the NAME as an internal page URL in scripts/links/HTML.
        url_hits, snippet = 0, ''
        if no_id_nav and name:
            pat = APP_URL + re.escape(name) + r'(?![A-Za-z0-9_-])'
            m = re.search(pat, url_corpus)
            if m:
                url_hits = len(re.findall(pat, url_corpus))
                i = m.start()
                snippet = re.sub(r'\s+', ' ', url_corpus[max(0, i - 45):i + len(name) + 45]).replace('\\', '')
        rows.append({'wrapper': wk, 'inner_id': iid, 'name': name, 'refs': r,
                     'is_system': is_system, 'name_flag_old': bool(OLD_RE.search(name or '')),
                     'name_url_hits': url_hits, 'name_url_snippet': snippet,
                     'referenced_by_url': (no_id_nav and url_hits > 0),
                     'unused': (no_id_nav and url_hits == 0)})
    # dynamic-navigation caveat counters
    dyn = {'dynamic_page_name': 0, 'ListGoToPage': 0}
    def cnt(n):
        t = n.get('type')
        p = n.get('properties', {})
        if t == 'ChangePage' and isinstance(p, dict) and 'dynamic_page_name' in p:
            dyn['dynamic_page_name'] += 1
        if t == 'ListGoToPage':
            dyn['ListGoToPage'] += 1
    walk({k: data.get(k) for k in ('pages', 'element_definitions', 'mobile_views')}, cnt)
    return rows, dyn

def analyze_mobile_views(data):
    """Native-app mobile views (`mobile_views`, type=Page + is_mobile_view).

    A view is reachable ONLY via: settings.client_safe.initial_mobile_view, a built-in system
    role (settings.client_safe.built_in_mobile_views: update_app, reset_password, ...) or a
    MobileNavigate action whose properties.element_id is the view's inner id. There is no public
    URL for a view, so this is closed-world — but deep links / push notifications may open views
    directly, hence "verify" phrasing in the report. NB: do NOT count quoted-id occurrences here:
    elements of views created by cloning keep `current_parent` pointing at the source view's id,
    which massively inflates naive counts (a cloned view can carry many such refs).
    Also detects BROKEN navigations: MobileNavigate whose target id matches no existing view
    (the view was deleted; the action silently fails at runtime).
    """
    views = {k: v for k, v in (data.get('mobile_views') or {}).items() if isinstance(v, dict)}
    cs = (data.get('settings', {}) or {}).get('client_safe', {}) or {}
    roles = {}
    if isinstance(cs.get('initial_mobile_view'), str):
        roles[cs['initial_mobile_view']] = 'initial'
    for bname, vid in (cs.get('built_in_mobile_views') or {}).items():
        if isinstance(vid, str):
            roles.setdefault(vid, bname)
    # Two reference forms: MobileNavigate (properties.element_id) and DeepLink
    # (properties.destination_view — push notifications / magic links landing on a view).
    # DeepLink lives in BACKEND workflows too, so the api section must be scanned as well.
    targets, nav_edges = Counter(), []
    def collect_navs(actions, cname, kind, disabled):
        navs = []
        walk(actions, lambda n: navs.append(n) if n.get('type') in ('MobileNavigate', 'DeepLink') else None)
        for n in navs:
            p = n.get('properties') or {}
            tid = p.get('element_id') if n.get('type') == 'MobileNavigate' else p.get('destination_view')
            if isinstance(tid, str):
                targets[tid] += 1
                nav_edges.append({'target': tid, 'container': cname, 'kind': kind,
                                  'action': n.get('type'), 'disabled': disabled})
    for kind, coll in (('mobile', data.get('mobile_views', {})), ('page', data.get('pages', {})),
                       ('reusable', data.get('element_definitions', {}))):
        if not isinstance(coll, dict):
            continue
        for v in coll.values():
            if not isinstance(v, dict) or not isinstance(v.get('workflows'), dict):
                continue
            cname = v.get('name') or ''
            for wf in v['workflows'].values():
                if not isinstance(wf, dict):
                    continue
                collect_navs(wf.get('actions'), cname, kind,
                             bool((wf.get('properties') or {}).get('workflow_disabled')))
    for v in (data.get('api') or {}).values():
        if isinstance(v, dict):
            collect_navs(v.get('actions'), (v.get('properties') or {}).get('wf_name') or v.get('id') or '',
                         'backend', False)
    ids = {v.get('id') for v in views.values()}
    oldish = re.compile(r'(_old|_bkp|_backup|_copy|_test|_v\d|_deprecated|_delete|❌|old_|test_'
                        r'|copy_| copy|_bak|_legacy|clone|\bbkp\b)', re.I)
    rows = []
    for wk, v in views.items():
        iid, name = v.get('id'), v.get('name')
        rows.append({'wrapper': wk, 'inner_id': iid, 'name': name,
                     'nav_refs': targets.get(iid, 0), 'role': roles.get(iid),
                     'name_flag_old': bool(oldish.search(name or '')),
                     'workflows': len(v.get('workflows') or {}),
                     'elements': len(v.get('elements') or {}),
                     'unused': (targets.get(iid, 0) == 0 and roles.get(iid) is None)})
    rows.sort(key=lambda r: ((r['name'] or '').lower(), r['inner_id'] or ''))
    # Same-name twin guard (mirrors the reusables rule): Bubble's App Search Tool matches
    # "Go to view ..." by display NAME, so a live twin's navigations make a dead same-named
    # view look used in the editor — never present it as a clean delete; route to a verify
    # bucket showing which twin is actually in use.
    by_name = defaultdict(list)
    for r in rows:
        by_name[r['name'] or ''].append(r)
    for r in rows:
        if r['unused']:
            twin = next((t for t in by_name[r['name'] or ''] if t is not r and not t['unused']), None)
            if twin:
                r['unused'] = False
                r['dup_name_conflict'] = True
                r['twin_used_id'] = twin['inner_id']
    broken = [e for e in nav_edges if e['target'] not in ids]
    return {'total': len(rows), 'rows': rows, 'unused': [r for r in rows if r['unused']],
            'duplicate_name': [r for r in rows if r.get('dup_name_conflict')],
            'roles': {vid: rname for vid, rname in roles.items()}, 'broken': broken}

def analyze_reusables(data, quoted):
    defs = data.get('element_definitions', {})
    # Exclude already-deleted definitions entirely (like option sets / fields / tables). Bubble
    # usually drops deleted reusables from the export or moves them to holding_pen rather than
    # flagging them, but if an export DOES carry deleted:true, a deleted reusable must not be
    # considered "unused" — it's already gone.
    meta = {wk: {'inner_id': v.get('id'), 'name': v.get('name')}
            for wk, v in defs.items() if isinstance(v, dict) and not v.get('deleted')}
    iid2wrapper = {m['inner_id']: wk for wk, m in meta.items()}
    # collect placements: container -> set(placed definition inner_ids)
    edges = defaultdict(set)
    def collect(elements, container):
        if not isinstance(elements, dict):
            return
        for el in elements.values():
            if isinstance(el, dict):
                if el.get('type') == 'CustomElement':
                    cid = (el.get('properties') or {}).get('custom_id')
                    if cid:
                        edges[container].add(cid)
                collect(el.get('elements'), container)
    for wk, pv in data.get('pages', {}).items():
        if isinstance(pv, dict):
            collect(pv.get('elements'), 'PAGE:' + wk)
    for wk, dv in defs.items():
        if isinstance(dv, dict) and not dv.get('deleted'):
            collect(dv.get('elements'), 'DEF:' + wk)
    for mk, mv in data.get('mobile_views', {}).items():
        if isinstance(mv, dict):
            collect(mv.get('elements'), 'MOBILE:' + mk)
    all_placed = set().union(*edges.values()) if edges else set()
    # reachability from pages/mobile (catch definitions only nested in dead defs)
    roots = set()
    for c, cids in edges.items():
        if c.startswith('PAGE') or c.startswith('MOBILE'):
            roots |= cids
    # settings-pinned mobile reusables (built_in_mobile_reusables, e.g. offline_banner) are shown
    # by the NATIVE RUNTIME itself — roots even if never placed as a CustomElement anywhere.
    cs_mob = (data.get('settings', {}).get('client_safe', {}) or {}).get('built_in_mobile_reusables') or {}
    builtin_reuse = {vid for vid in cs_mob.values() if isinstance(vid, str)}
    roots |= (builtin_reuse & set(iid2wrapper))
    reachable, frontier = set(), set(roots)
    while frontier:
        nxt = set()
        for iid in frontier:
            if iid in reachable:
                continue
            reachable.add(iid)
            wk = iid2wrapper.get(iid)
            if wk:
                nxt |= edges.get('DEF:' + wk, set())
        frontier = nxt - reachable
    # Same-name detection. Bubble's reusable search matches by NAME, and the editor can end up
    # with two reusables sharing an exact name (e.g. a leftover duplicate). If an unplaced
    # reusable has a same-named twin that IS live, it *looks* used in Bubble (the twin's usages
    # show under it) and deleting the wrong one is easy — so never present it as a clean delete.
    name_to_iids = defaultdict(list)
    for m in meta.values():
        name_to_iids[m['name']].append(m['inner_id'])
    rows = []
    for wk, m in meta.items():
        iid = m['inner_id']
        r = refs_elsewhere(iid, defs[wk], quoted)
        placed = iid in all_placed
        hard = (not placed and r <= 0 and iid not in builtin_reuse)
        trans = (placed and iid not in reachable)
        twins = [t for t in name_to_iids.get(m['name'], []) if t != iid]
        twin_used_id = next((t for t in twins if t in reachable), None)
        dup_conflict = bool((hard or trans) and twin_used_id)
        rows.append({'name': m['name'], 'inner_id': iid,
                     'unused_hard': (hard and not dup_conflict),
                     'unused_transitive': (trans and not dup_conflict),
                     'reachable': iid in reachable,
                     'dup_name_conflict': dup_conflict, 'twin_used_id': twin_used_id})
    return rows

def analyze_backend(data, quoted, selfapi_used=None):
    """`selfapi_used` = wf_names targeted by USED API Connector self-calls (app calling its own
    Workflow API) — these count as references even though no ScheduleAPIEvent points at them."""
    api = data.get('api', {})
    selfapi_used = selfapi_used or set()
    client_safe = data.get('settings', {}).get('client_safe', {}) or {}
    folders = client_safe.get('api_wf_folder_list', {}) or {}
    # Bubble's per-workflow "Expose as a public API workflow" checkbox is serialized only when it
    # differs from the default: a MISSING `expose` key means EXPOSED (verified empirically — the
    # absent-key workflows are exactly the ones the app itself calls via API Connector self-calls).
    # Gated on the app-level Workflow API switch: with the API off nothing is reachable externally.
    wf_api_on = bool(client_safe.get('exposes_wf_api', True))
    # scheduled/triggered targets from ANYWHERE, and specifically from page/def (client) contexts.
    # Covers both target kinds: api_event (Schedule API workflow) and custom_event (Trigger a
    # custom event — incl. TriggerBackendCustomEvent, how pages call backend custom events).
    sched_all, sched_client = set(), set()
    def grab(node, into):
        t = node.get('type')
        if t in ('ScheduleAPIEvent', 'ScheduleAPIEventOnList'):
            tv = (node.get('properties') or {}).get('api_event')
            if isinstance(tv, str):
                into.add(tv)
        elif t in ('TriggerCustomEvent', 'ScheduleCustom', 'TriggerCustomEventFromReusable',
                   'TriggerBackendCustomEvent'):
            tv = (node.get('properties') or {}).get('custom_event')
            if isinstance(tv, str):
                into.add(tv)
    walk(data, lambda n: grab(n, sched_all))
    for pv in data.get('pages', {}).values():
        if isinstance(pv, dict):
            walk(pv.get('elements'), lambda n: grab(n, sched_client))
            walk(pv.get('workflows'), lambda n: grab(n, sched_client))
    for dv in data.get('element_definitions', {}).values():
        if isinstance(dv, dict):
            walk(dv.get('elements'), lambda n: grab(n, sched_client))
            walk(dv.get('workflows'), lambda n: grab(n, sched_client))
    # native mobile views schedule/trigger backend work too — without this, a WF scheduled ONLY
    # from a mobile view is missing from the reachability ROOTS and gets falsely flagged transitive
    for mvv in data.get('mobile_views', {}).values():
        if isinstance(mvv, dict):
            walk(mvv.get('elements'), lambda n: grab(n, sched_client))
            walk(mvv.get('workflows'), lambda n: grab(n, sched_client))
    # per-workflow scheduling/trigger edges over ALL backend nodes (for transitive reachability).
    # The graph must include every `api` entry — APIEvent, CustomEvent, DatabaseTriggerEvent,
    # RecurringEvent — because chains like "DB trigger schedules an APIEvent" or "page triggers a
    # backend CustomEvent whose actions schedule an APIEvent" keep those APIEvents alive. DB
    # triggers and recurring events fire on their own, so they are always-live roots.
    edges = defaultdict(set)
    apievent_ids, node_ids, auto_roots = set(), set(), set()
    rows = []
    for wk, v in api.items():
        if not isinstance(v, dict):
            continue
        iid = v.get('id')
        if not iid:
            continue
        vtype = v.get('type')
        node_ids.add(iid)
        walk(v.get('actions'), lambda n, s=iid: grab(n, edges[s]))
        if vtype in ('DatabaseTriggerEvent', 'RecurringEvent'):
            auto_roots.add(iid)
        if vtype != 'APIEvent':
            continue
        apievent_ids.add(iid)
        p = v.get('properties', {}) or {}
        rows.append({'inner_id': iid, 'wf_name': p.get('wf_name'),
                     'folder': folders.get(p.get('wf_folder'), '(no folder)'),
                     'expose': bool(p.get('expose', wf_api_on)),
                     'expose_explicit': 'expose' in p,
                     # webhook signature: "Parameter definition = Detect request data" is stored as
                     # parameter_def == 'auto'; raw_data is the sample payload captured when the
                     # endpoint was initialized by a real external call (e.g. a payment-provider webhook)
                     'webhook': p.get('parameter_def') == 'auto',
                     'webhook_initialized': bool(p.get('raw_data')),
                     'self_api': p.get('wf_name') in selfapi_used,
                     'scheduled': iid in sched_all,
                     'refs': refs_elsewhere(iid, v, quoted)})
    # roots = exposed endpoints + self-API-called workflows + anything scheduled/triggered from the
    # client side + self-firing backend events (DB triggers, recurring)
    roots = ({r['inner_id'] for r in rows if r['expose'] or r['self_api']}
             | (sched_client & node_ids) | auto_roots)
    reach, frontier = set(), set(roots)
    while frontier:
        nxt = set()
        for iid in frontier:
            if iid in reach:
                continue
            reach.add(iid)
            nxt |= (edges.get(iid, set()) & node_ids)
        frontier = nxt - reach
    exposed = 0
    for r in rows:
        if r['expose']:
            exposed += 1
        r['unused_hard'] = (not r['expose'] and not r['self_api'] and not r['scheduled'] and r['refs'] <= 0)
        r['unused_transitive'] = (not r['expose'] and not r['self_api']
                                  and r['inner_id'] not in reach and not r['unused_hard'])
        # A webhook-shaped WF (Detect request data) that looks unreachable is NOT a safe delete:
        # its caller is an external service, invisible to static analysis. Route to a verify bucket.
        r['webhook_verify'] = r['webhook'] and (r['unused_hard'] or r['unused_transitive'])
        if r['webhook_verify']:
            r['unused_hard'] = r['unused_transitive'] = False
    return rows, exposed

def analyze_optionsets(data, content_raw):
    opt = data.get('option_sets', {})
    rows = []
    for name, ov in opt.items():
        if not isinstance(ov, dict):
            continue
        deleted = bool(ov.get('deleted'))
        n = content_raw.count('option.' + name)
        rows.append({'name': name, 'display': ov.get('display'), 'deleted': deleted,
                     'ref_count': n, 'unused': (n == 0 and not deleted)})
    return rows

def analyze_styles(data, content_raw):
    styles = data.get('styles', {})
    cs = data.get('settings', {}).get('client_safe', {}) or {}
    default_ids = set((cs.get('default_styles') or {}).values())
    used = set()
    def collect(elements):
        if not isinstance(elements, dict):
            return
        for el in elements.values():
            if isinstance(el, dict):
                s = el.get('style')
                if isinstance(s, str):
                    used.add(s)
                collect(el.get('elements'))
    for pv in data.get('pages', {}).values():
        if isinstance(pv, dict):
            collect(pv.get('elements'))
    for dv in data.get('element_definitions', {}).values():
        if isinstance(dv, dict):
            collect(dv.get('elements'))
    for mv in data.get('mobile_views', {}).values():
        if isinstance(mv, dict):
            collect(mv.get('elements'))
    rows = []
    for sid, sv in styles.items():
        if not isinstance(sv, dict):
            continue
        is_default = sid in default_ids
        # authoritative pattern: an element referencing a style stores "style":"<id>"
        occ = content_raw.count('"style":"' + sid + '"')
        rows.append({'id': sid, 'display': sv.get('display'), 'stype': sv.get('type'),
                     'unused': (sid not in used and not is_default and occ == 0)})
    return rows

def analyze_datatypes(data, quoted, content_raw, script_corpus):
    """Unused data types (tables) and fields.

    A field is referenced by its (mangled) key in the app-logic sections; a type by
    "custom.<key>". A field/type is 'used' if referenced beyond its own declaration, or
    exposed in the native Data API (`exposed_api`), or named in a JS/HTML script. We keep
    the Data-API-exposed ones in a separate bucket because they may have external consumers.
    """
    ut = data.get('user_types', {})
    custom = {k: v for k, v in ut.items() if isinstance(v, dict) and 'display' in v}
    # type references: "custom.<key>"
    custom_quoted = Counter(re.findall(r'"(custom\.[A-Za-z0-9_]+)"', content_raw))
    # how many types declare each field key (to subtract declarations from the ref count)
    decls = Counter()
    for tv in custom.values():
        for fk, fv in (tv.get('fields') or {}).items():
            if isinstance(fv, dict):
                decls[fk] += 1
    def field_used(fk):
        return (quoted.get(fk, 0) - decls.get(fk, 0)) > 0

    # ---- fields ----
    fld_candidates, fld_exposed, fld_script = [], [], []
    deleted_fields = 0
    for tk, tv in custom.items():
        if tv.get('deleted'):
            continue  # its table is already trashed
        exposed = bool(tv.get('exposed_api'))
        tdisp = tv.get('display') or tk
        for fk, fv in (tv.get('fields') or {}).items():
            if not isinstance(fv, dict):
                continue
            if fv.get('deleted'):
                deleted_fields += 1
                continue
            if field_used(fk):
                continue
            row = {'type_key': tk, 'type_display': tdisp, 'field_key': fk,
                   'display': fv.get('display'), 'ftype': fv.get('value'),
                   'exposed': exposed, 'shared': decls.get(fk, 0) > 1}
            if fk in script_corpus:            # referenced by name in a JS/HTML script -> keep
                fld_script.append(row)
            elif exposed:                      # only reachable via the Data API -> verify
                fld_exposed.append(row)
            else:                              # unreferenced anywhere -> candidate
                fld_candidates.append(row)

    # ---- types (tables) ----
    unused_types, exposed_only_types, deleted_types = [], [], 0
    for tk, tv in custom.items():
        if tv.get('deleted'):
            deleted_types += 1
            continue
        exposed = bool(tv.get('exposed_api'))
        cu = custom_quoted.get('custom.' + tk, 0)
        active_f = [fk for fk, fv in (tv.get('fields') or {}).items()
                    if isinstance(fv, dict) and not fv.get('deleted')]
        anyfield = any(field_used(fk) for fk in active_f)
        in_script = ('custom.' + tk) in script_corpus
        used_internally = cu > 0 or anyfield or tk == 'user' or in_script
        entry = {'type_key': tk, 'display': tv.get('display') or tk, 'active_fields': len(active_f),
                 'ref': cu, 'exposed': exposed}
        if not used_internally and not exposed:
            unused_types.append(entry)
        elif not used_internally and exposed:
            exposed_only_types.append(entry)

    def sort_by_type(rows):
        return sorted(rows, key=lambda r: ((r['type_display'] or '').lower(), r['display'] or ''))
    return {
        'types': {'active': len(custom) - deleted_types, 'deleted': deleted_types,
                  'exposed': sum(1 for v in custom.values() if v.get('exposed_api') and not v.get('deleted')),
                  'unused': sorted(unused_types, key=lambda r: (r['display'] or '').lower()),
                  'exposed_only': exposed_only_types},
        'fields': {'candidates': sort_by_type(fld_candidates), 'exposed': sort_by_type(fld_exposed),
                   'script': fld_script, 'deleted': deleted_fields,
                   'active': len(fld_candidates) + len(fld_exposed) + len(fld_script)
                             + sum(len([1 for fk, fv in (tv.get('fields') or {}).items()
                                        if isinstance(fv, dict) and not fv.get('deleted') and field_used(fk)])
                                   for tv in custom.values() if not tv.get('deleted'))},
    }

def analyze_ghost_plugins(data, registry=None):
    """Plugins REMOVED from the project but still referenced. A plugin element/action carries the
    type `<pluginId>-<suffix>`. If that plugin id is NOT in `settings.client_safe.plugins` (the
    installed list), the plugin was uninstalled while its elements/actions remained — a broken /
    ghost reference. Report each occurrence with the plugin name, the page/reusable, and the
    element or workflow where it lives."""
    registry = registry or {}
    installed = set((data.get('settings', {}).get('client_safe', {}) or {}).get('plugins', {}) or {})
    def_names = build_def_names(data)
    PID = re.compile(r'^(\d{13}x\d+)-')
    def ghost(t):
        if not isinstance(t, str):
            return None
        m = PID.match(t)
        return m.group(1) if (m and m.group(1) not in installed) else None
    refs = []
    for kind, coll in (('page', data.get('pages', {})), ('reusable', data.get('element_definitions', {}))):
        for v in coll.values():
            if not isinstance(v, dict):
                continue
            cname = v.get('name') or ''
            id2name = {}
            def mapn(e):
                if isinstance(e, dict):
                    for el in e.values():
                        if isinstance(el, dict):
                            if el.get('id'):
                                id2name[el['id']] = editor_name(el, el['id'], def_names)
                            mapn(el.get('elements'))
            mapn(v.get('elements'))
            def walkel(e):
                if isinstance(e, dict):
                    for el in e.values():
                        if isinstance(el, dict):
                            g = ghost(el.get('type'))
                            if g:
                                refs.append({'plugin_id': g, 'container': cname, 'kind': kind,
                                             'where': 'element', 'location': editor_name(el, el.get('id'), def_names)})
                            walkel(el.get('elements'))
            walkel(v.get('elements'))
            wfs = v.get('workflows')
            if isinstance(wfs, dict):
                for wf in wfs.values():
                    if not isinstance(wf, dict):
                        continue
                    p = wf.get('properties', {}) if isinstance(wf.get('properties'), dict) else {}
                    eid = p.get('element_id')
                    lbl = p.get('event_name') or p.get('wf_name') or \
                        ((id2name.get(eid, eid) + ' ' if eid else '') + '(' + (wf.get('type') or '?') + ')')
                    if ghost(wf.get('type')):
                        refs.append({'plugin_id': ghost(wf.get('type')), 'container': cname, 'kind': kind,
                                     'where': 'trigger', 'location': lbl})
                    seen_here = set()
                    def deepact(o):
                        if isinstance(o, dict):
                            g = ghost(o.get('type'))
                            if g and (g, lbl) not in seen_here:
                                seen_here.add((g, lbl))
                                refs.append({'plugin_id': g, 'container': cname, 'kind': kind,
                                             'where': 'action', 'location': lbl})
                            for x in o.values():
                                deepact(x)
                        elif isinstance(o, list):
                            for x in o:
                                deepact(x)
                    deepact(wf.get('actions'))
    long = lambda pid: ('x' in pid) and pid[:4].isdigit()
    for r in refs:
        r['plugin_name'] = (registry.get(r['plugin_id']) or {}).get('name') or ''
        r['url'] = 'https://bubble.io/plugin/' + r['plugin_id'] if long(r['plugin_id']) else ''
    refs.sort(key=lambda r: ((r['plugin_name'] or r['plugin_id']).lower(), (r['container'] or '').lower(), r['where']))
    from collections import Counter as _C
    by_plugin = _C(r['plugin_id'] for r in refs)
    return {'refs': refs, 'plugin_count': len(by_plugin),
            'plugins': [{'id': pid, 'name': (registry.get(pid) or {}).get('name') or '', 'count': c,
                         'url': ('https://bubble.io/plugin/' + pid) if long(pid) else ''}
                        for pid, c in by_plugin.most_common()]}

def analyze_api_calls(data):
    """API Connector calls declared but never invoked.

    `settings.client_safe.apiconnector2` = {apiId: {human: <provider name>, calls: {callId: {name,
    url, method, ...}}, auth...}}. A call is invoked in TWO distinct serialized forms:
      - workflow ACTION: the action `type` is `apiconnector2-<apiId>.<callId>`   (HYPHEN)
      - DATA SOURCE:     the expression carries `"provider":"apiconnector2.<apiId>.<callId>"` (DOT)
    A call is unused only if NEITHER form appears in the app logic — checking just the hyphen form
    false-flags every call used purely as a data source. OAuth `token_call` / `oauth_user_data_call`
    calls are invoked automatically by the auth flow (not via those forms) — treat them as used.

    Also detects SELF-API calls — the app calling its own Workflow API (URL ending in
    `/wf/<wf_name>` or `<placeholder>]/<wf_name>` where <wf_name> is a backend APIEvent's name).
    Used self-calls are real references to those backend workflows (returned in `self_used`);
    unused ones are annotated with `self_wf` so the report can pair call and workflow.
    """
    ac = (data.get('settings', {}).get('client_safe', {}) or {}).get('apiconnector2', {}) or {}
    applogic = json.dumps({k: data.get(k) for k in ('pages', 'element_definitions', 'api')}, separators=(',', ':'))
    backend_wf_names = {(v.get('properties') or {}).get('wf_name')
                        for v in (data.get('api') or {}).values()
                        if isinstance(v, dict) and v.get('type') == 'APIEvent'} - {None}
    def selfapi_target(url):
        if not isinstance(url, str):
            return None
        m = re.search(r'/wf/([A-Za-z0-9_\-]+)\s*$', url) or re.search(r'\]/([A-Za-z0-9_\-]+)\s*$', url)
        name = m.group(1) if m else None
        return name if name in backend_wf_names else None
    total, unused, providers, self_used = 0, [], set(), {}
    for apiid, api in ac.items():
        if not isinstance(api, dict):
            continue
        calls = api.get('calls', {})
        if not isinstance(calls, dict):
            continue
        human = api.get('human') or apiid
        providers.add(apiid)
        auth_calls = set()
        if isinstance(api.get('oauth_user_data_call'), str):
            auth_calls.add(api['oauth_user_data_call'])
        for cid in calls:
            if 'token' in cid.lower():
                auth_calls.add(cid)
        for callid, call in calls.items():
            if not isinstance(call, dict):
                continue
            total += 1
            ref = apiid + '.' + callid
            invoked = ('apiconnector2-' + ref) in applogic or ('apiconnector2.' + ref) in applogic
            is_auth = callid in auth_calls or 'token' in (call.get('name') or '').lower()
            self_wf = selfapi_target(call.get('url'))
            if invoked or is_auth:
                if self_wf:
                    self_used.setdefault(self_wf, []).append(ref)
                continue
            unused.append({'provider': human, 'call': call.get('name') or callid, 'ref': ref,
                           'method': (call.get('method') or '').upper(), 'self_wf': self_wf})
    unused.sort(key=lambda r: ((r['provider'] or '').lower(), (r['call'] or '').lower()))
    return {'total': total, 'used': total - len(unused), 'providers': len(providers), 'unused': unused,
            'self_used': self_used}

def analyze_workflows(data):
    """Custom events never triggered, and page/reusable workflows whose trigger can't fire.

    - Custom events (backend `api` type=CustomEvent, and page/reusable workflows type=CustomEvent)
      are 'called' iff their id is the `custom_event` target of a Trigger/Schedule custom-event
      action anywhere.
    - Element-triggered workflows (ButtonClicked, InputChanged, Popup*, plugin element events, …)
      fire on interaction with `properties.element_id` (which points to an element's `id` FIELD,
      not its dict key). The container's own root id (container['id']) counts as an existing,
      always-displayable element — popup-rooted reusables trigger on it ("When popup closed").
      Two ways such a trigger can never fire:
        * ORPHAN: the element_id resolves to no element -> the element was deleted (high confidence).
        * NEVER RENDERED: the trigger element is never displayable. An element "can be visible" if
          its default `is_visible` is true, OR a Show/Toggle/Animate action targets it, OR a
          conditional (an entry in the element's `states`, i.e. the "Conditional" tab, whose
          `properties` sets `is_visible`) can reveal it. An element is never rendered if IT or ANY
          ANCESTOR can never be visible (a click target inside a group that never shows is dead too).
    """
    # custom_event trigger targets (the id a Trigger/Schedule custom-event action points to)
    targets = set()
    def collect_targets(o):
        if isinstance(o, dict):
            if o.get('type') in ('TriggerCustomEvent', 'ScheduleCustom', 'TriggerCustomEventFromReusable',
                                 'TriggerBackendCustomEvent'):
                tv = (o.get('properties') or {}).get('custom_event')
                if isinstance(tv, str):
                    targets.add(tv)
            for v in o.values():
                collect_targets(v)
        elif isinstance(o, list):
            for v in o:
                collect_targets(v)
    collect_targets(data)

    # elements revealed by an action anywhere (id FIELD of the target)
    shown = set()
    def collect_shown(o):
        if isinstance(o, dict):
            if o.get('type') in ('ShowElement', 'ToggleElement', 'AnimateElement', 'AlertShowMessage'):
                tid = (o.get('properties') or {}).get('element_id')
                if tid:
                    shown.add(tid)
            for v in o.values():
                collect_shown(v)
        elif isinstance(o, list):
            for v in o:
                collect_shown(v)
    collect_shown({k: data.get(k) for k in ('pages', 'element_definitions', 'mobile_views')})
    def_names = build_def_names(data)  # for editor labels of reusable instances

    def elem_maps(container):
        """Return (name, parent, can_visible, never_rendered) for a page/reusable's element tree."""
        name, parent, canvis = {}, {}, {}
        # The container's OWN root id (a reusable's popup/group root, a page's root) is a valid
        # trigger target: "When <this popup> is closed/opened" inside a popup-rooted reusable binds
        # to it. It lives at container['id'], NOT inside container['elements'] — without this seed
        # every such self-referencing trigger is falsely flagged as "element deleted". Visibility
        # of a reusable root is decided per placed instance, so it is never statically hidden.
        rid = container.get('id')
        if rid:
            name[rid] = container.get('name') or rid
            parent[rid] = None
            canvis[rid] = True
        def w(elements, par):
            if isinstance(elements, dict):
                for el in elements.values():
                    if isinstance(el, dict):
                        iid = el.get('id')
                        if iid:
                            p = el.get('properties', {}) if isinstance(el.get('properties'), dict) else {}
                            sts = el.get('states') if isinstance(el.get('states'), dict) else {}
                            # a conditional (state) that sets is_visible can reveal a hidden element
                            cond_shows = any(isinstance(s, dict) and isinstance(s.get('properties'), dict)
                                             and 'is_visible' in s['properties'] for s in sts.values())
                            name[iid] = editor_name(el, iid, def_names)
                            parent[iid] = par
                            canvis[iid] = (p.get('is_visible', True) is not False) or (iid in shown) or cond_shows
                        w(el.get('elements'), iid)
        w(container.get('elements'), None)
        memo = {}
        def never_rendered(iid, seen=None):
            if iid in memo:
                return memo[iid]
            seen = seen or set()
            if iid in seen:
                return False
            seen.add(iid)
            if iid not in canvis:      # unknown element -> don't over-flag
                return False
            if not canvis[iid]:
                memo[iid] = True
                return True
            par = parent.get(iid)
            r = never_rendered(par, seen) if par else False
            memo[iid] = r
            return r
        # for a never-rendered element, find the nearest ancestor (incl self) that can never be visible
        def blocking(iid):
            cur = iid
            while cur is not None:
                if not canvis.get(cur, True):
                    return cur
                cur = parent.get(cur)
            return iid
        return name, canvis, never_rendered, blocking

    # Global element-id -> home container index. A trigger element missing from ITS OWN container
    # may still exist elsewhere: Bubble's "convert group to reusable" moves the elements into a new
    # reusable definition but leaves container-level workflows behind, still bound to the old
    # element_id. Those leftovers can never fire (the id is not in the container's tree), but
    # reporting WHERE the element went makes the finding verifiable in the editor.
    elem_home = {}
    for hkind, hcoll in (('page', data.get('pages', {})), ('reusable', data.get('element_definitions', {})),
                         ('mobile', data.get('mobile_views', {}))):
        for hv in hcoll.values():
            if not isinstance(hv, dict):
                continue
            hname = hv.get('name') or ''
            stack = [hv.get('elements')]
            while stack:
                elements = stack.pop()
                if not isinstance(elements, dict):
                    continue
                for el in elements.values():
                    if isinstance(el, dict):
                        hid = el.get('id')
                        if hid and hid not in elem_home:
                            elem_home[hid] = (hname, hkind)
                        stack.append(el.get('elements'))

    backend_ce, page_ce, orphan, hidden = [], [], [], []
    # backend custom events
    for k, v in data.get('api', {}).items():
        if isinstance(v, dict) and v.get('type') == 'CustomEvent':
            iid = v.get('id')
            p = v.get('properties', {}) if isinstance(v.get('properties'), dict) else {}
            if iid and iid not in targets:
                backend_ce.append({'id': iid, 'name': p.get('event_name') or p.get('wf_name') or iid,
                                   'folder': p.get('wf_folder')})
    # page/reusable workflows
    for kind, coll in (('page', data.get('pages', {})), ('reusable', data.get('element_definitions', {})),
                       ('mobile', data.get('mobile_views', {}))):
        for v in coll.values():
            if not isinstance(v, dict):
                continue
            wfs = v.get('workflows')
            if not isinstance(wfs, dict):
                continue
            cname = v.get('name') or ''
            ename, canvis, never_rendered, blocking = elem_maps(v)
            for wf in wfs.values():
                if not isinstance(wf, dict):
                    continue
                t = wf.get('type') or ''
                wid = wf.get('id')
                p = wf.get('properties', {}) if isinstance(wf.get('properties'), dict) else {}
                if t == 'CustomEvent':
                    if wid and wid not in targets:
                        page_ce.append({'id': wid, 'name': p.get('event_name') or p.get('wf_name') or wid,
                                        'container': cname, 'kind': kind})
                    continue
                eid = p.get('element_id')
                if not eid:
                    continue  # lifecycle / non-element trigger (PageLoaded, LoggedIn, etc.) — can fire
                if eid not in canvis:
                    home = elem_home.get(eid)
                    orphan.append({'id': wid, 'trigger': t, 'container': cname, 'kind': kind, 'element_id': eid,
                                   'moved_to': home[0] if home else None,
                                   'moved_to_kind': home[1] if home else None})
                elif never_rendered(eid):
                    blk = blocking(eid)
                    hidden.append({'id': wid, 'trigger': t, 'container': cname, 'kind': kind,
                                   'element_id': eid, 'element': ename.get(eid, eid),
                                   'reason': 'self' if blk == eid else 'ancestor',
                                   'blocker': ename.get(blk, blk), 'blocker_id': blk})
    key = lambda r: ((r.get('container') or '').lower(), (r.get('name') or r.get('element') or '').lower())
    return {'backend_ce': sorted(backend_ce, key=lambda r: (r['name'] or '').lower()),
            'page_ce': sorted(page_ce, key=key), 'orphan': sorted(orphan, key=key),
            'hidden': sorted(hidden, key=key)}

def analyze_variables(data, content_raw):
    """Unused user-defined color and font VARIABLES (design tokens).

    Defined in settings.client_safe.color_tokens_user / font_tokens_user ({id: {name, deleted...}}).
    A variable is referenced as the CSS custom property `var(--color_<id>_<state>)` /
    `var(--font_<id>_<state>)`. We must NOT count the bare id: token ids live in a separate
    namespace and can collide with element ids, and the theme is snapshotted many times in the
    export — both inflate a bare-id count massively. The `var(--color_<id>` / `var(--font_<id>`
    form is collision- and snapshot-proof (definitions store rgba/font_family, not var() refs).
    """
    cs = data.get('settings', {}).get('client_safe', {}) or {}
    colors = (cs.get('color_tokens_user', {}) or {}).get('default', {}) or {}
    fonts = (cs.get('font_tokens_user', {}) or {}).get('default', {}) or {}

    def used(prefix, vid):
        return bool(re.search(r'var\(--' + prefix + '_' + re.escape(vid) + r'[_)]', content_raw))

    def rows(tokens, prefix, extra_key):
        out = []
        for vid, v in tokens.items():
            if not isinstance(v, dict) or v.get('deleted'):
                continue
            if used(prefix, vid):
                continue
            out.append({'id': vid, 'name': v.get('name') or vid, 'extra': v.get(extra_key)})
        return sorted(out, key=lambda r: (r['name'] or '').lower())

    def stats(tokens):
        active = sum(1 for v in tokens.values() if isinstance(v, dict) and not v.get('deleted'))
        deleted = sum(1 for v in tokens.values() if isinstance(v, dict) and v.get('deleted'))
        return active, deleted

    ca, cd = stats(colors)
    fa, fd = stats(fonts)
    return {'colors': {'active': ca, 'deleted': cd, 'unused': rows(colors, 'color', 'rgba')},
            'fonts': {'active': fa, 'deleted': fd, 'unused': rows(fonts, 'font', 'font_family')}}

# well-known short-name plugin labels (marketplace long-ids have no name in the export).
# Short-name plugins are Bubble's own built-in/core plugins — author is Bubble.
KNOWN_PLUGINS = {
    'ionic': 'Ionic elements', 'slack': 'Slack', 'google': 'Google (fonts/maps/OAuth)',
    'chartjs': 'Chart Element', 'select2': 'Select / multi-dropdown', 'addtoany': 'AddToAny share',
    'docusign': 'DocuSign', 'mailchimp': 'Mailchimp', 'selectPDF': 'SelectPDF', 'zapiernew': 'Zapier',
    'dbconnector': 'SQL Database Connector', 'draggableui': 'Draggable Elements', 'progressbar': 'Progress Bar',
    'appconnector': 'App Connector', 'fullcalendar': 'Full Calendar', 'apiconnector2': 'API Connector',
    'materialicons': 'Material Icons', 'slickcarousel': 'Slick Slider/Carousel', 'multifileupload': 'Multi-File Uploader',
}

# Plugins that are active PROJECT-WIDE the moment they're installed and place NO element or action
# in the app — so they have zero detectable footprint in the export yet are genuinely used. These
# must never be flagged as safe-to-remove. id -> short reason. (Marketplace-global, like names.)
HEADLESS_PLUGINS = {
    '1568299250417x684448291308175400': 'Classify — applies CSS/styles to elements globally via the element ID; active project-wide once installed, never placed on a page',
}

def load_plugin_registry(extra_path=None):
    """Marketplace plugin-id -> {'name', 'author', 'delisted'}. Loads the bundled
    references/plugin_names.json (IDs are marketplace-global, so it's reusable across projects)
    plus an optional override file. Accepted value forms in the JSON:
      "Name"                                  known, listed plugin
      null                                    looked up but unavailable (delisted, name unknown)
      {"name": ..., "author": ..., "delisted": true}   object form; author = seller display name
    Authors resolve via the PUBLIC Data API chain: /api/1.1/obj/plugin/<id> -> owner_user ->
    /obj/user/<id> -> organization -> /obj/organization/<id> name_text.
    """
    reg = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, '..', 'references', 'plugin_names.json'), extra_path):
        if p and os.path.exists(p):
            try:
                for k, v in json.load(open(p, encoding='utf-8')).items():
                    if k.startswith('_'):
                        continue
                    if isinstance(v, dict):
                        reg[k] = {'name': v.get('name'), 'author': v.get('author') or '',
                                  'delisted': bool(v.get('delisted'))}
                    else:
                        reg[k] = {'name': v, 'author': '', 'delisted': v is None}
            except Exception:
                pass
    return reg

def load_plugin_pricing(extra_path=None):
    """Marketplace plugin-id -> pricing {status: free|paid|unknown, model, price}. Bundled
    references/plugin_pricing.json (marketplace-global) + optional override. Pricing is NOT in the
    export — it's researched from the marketplace, so flag unused PAID plugins to alert the auditor
    (recurring/wasted cost)."""
    reg = {}
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, '..', 'references', 'plugin_pricing.json'), extra_path):
        if p and os.path.exists(p):
            try:
                for k, v in json.load(open(p, encoding='utf-8')).items():
                    if not k.startswith('_') and isinstance(v, dict):
                        reg[k] = v
            except Exception:
                pass
    return reg

def analyze_plugins(data, content_raw, registry=None, pricing=None):
    registry = registry or {}
    pricing = pricing or {}
    cs = data.get('settings', {}).get('client_safe', {}) or {}
    sec = data.get('settings', {}).get('secure', {}) or {}
    plugins = cs.get('plugins', {}) or {}
    setting_keys = [k for k in list(sec.keys()) + list(cs.keys()) if k != 'plugins']
    dbq = cs.get('dbconnector_queries')
    db_has_queries = isinstance(dbq, dict) and len(dbq) > 0
    # count type usages once
    types = Counter()
    walk({k: data.get(k) for k in CONTENT_KEYS},
         lambda n: types.update([n['type']]) if isinstance(n.get('type'), str) else None)
    orphaned, configured, used_list = [], [], []
    for pid, ver in plugins.items():
        tcount = sum(c for t, c in types.items()
                     if t == pid or t.startswith(pid + '-') or t.startswith(pid + '.'))
        is_long = ('x' in pid) and pid[:4].isdigit()
        rv = registry.get(pid) or {}
        name = KNOWN_PLUGINS.get(pid) or rv.get('name') or ''
        # short-name plugins are Bubble's own built-ins; marketplace authors come from the registry
        author = rv.get('author') or ('' if is_long else 'Bubble')
        pr = pricing.get(pid) or {}
        base = {'id': pid, 'version': str(ver), 'name': name, 'author': author,
                'url': ('https://bubble.io/plugin/' + pid) if is_long else '',
                'delisted': bool(is_long and rv.get('delisted')),
                'paid': pr.get('status') == 'paid',
                'price': pr.get('price') or '', 'pricing_model': pr.get('model') or ''}
        if tcount > 0:  # has an element/action/API call placed -> in use
            used_list.append({**base, 'type_usages': tcount})
            continue
        occ = content_raw.count(pid)
        cfg = [k for k in setting_keys if pid in k or k.startswith(pid + '_')]
        entry = {**base, 'occ': occ, 'config_keys': len(cfg), 'headless': pid in HEADLESS_PLUGINS}
        functional, reason = False, ''
        zaps = (cs.get('zapier') or {}).get('zaps') if isinstance(cs.get('zapier'), dict) else None
        if pid in HEADLESS_PLUGINS:
            functional, reason = True, HEADLESS_PLUGINS[pid]  # global/headless -> keep, verify
        elif pid in ('zapiernew', 'zapier') and zaps:
            functional, reason = True, 'has %d Zap(s) configured (settings.zapier)' % len(zaps)
        elif pid == 'dbconnector' and db_has_queries:
            functional, reason = True, 'has %d SQL queries' % len(dbq)
        elif pid == 'google' and occ > 100:
            functional, reason = True, 'referenced %dx (fonts/maps/OAuth)' % occ
        elif cfg:
            functional, reason = True, 'has %d configured setting(s)' % len(cfg)
        elif occ > 3:
            functional, reason = True, 'referenced %dx in config/headers' % occ
        entry['reason'] = reason or ('only in install registry (%d occ)' % occ)
        (configured if functional else orphaned).append(entry)
    # PAID first (most important to flag), then alphabetical; unnamed ones last by id
    pkey = lambda r: (not r.get('paid'), not r['name'], (r['name'] or r['id']).lower())
    orphaned.sort(key=pkey)
    configured.sort(key=pkey)
    used_list.sort(key=lambda r: (not r['name'], (r['name'] or r['id']).lower()))
    return orphaned, configured, used_list, len(plugins)

# ------------------------------------------------------------------ page CSV cross-reference
def load_page_audit(path, name_col, status_cols):
    """Return name -> {'row': {...}, 'verdict': confirmed-dead|candidate|in-use|None}."""
    rows = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    if not rows:
        return {}
    cols = list(rows[0].keys())
    ncol = name_col or cols[0]
    scols = status_cols or [c for c in cols if re.search(r'status|usage|action|state|deprecat', c, re.I)]
    DEAD = re.compile(r'deprecat|delete|unused|not used|remove|obsolet|morto|excluir|descontinu', re.I)
    MAYBE = re.compile(r'maybe|review|check|needed|revisar|talvez|verificar|see if', re.I)
    LIVE = re.compile(r'in use|active|keep|live|em uso|manter|ativo|produç', re.I)
    out = {}
    for r in rows:
        nm = (r.get(ncol) or '').strip()
        if not nm:
            continue
        blob = ' '.join((r.get(c) or '') for c in scols)
        # Precedence is chosen for safety and intent, not first-match:
        #  - LIVE wins first: never auto-mark a page the team calls "in use" as dead
        #    (these are the direct-URL / embed entry points with no internal nav).
        #  - MAYBE next: "maybe delete" / "see if needed" is uncertainty -> candidate,
        #    even though it contains the word "delete".
        #  - DEAD last: only when nothing signals live/uncertain.
        verdict = None
        if LIVE.search(blob):
            verdict = 'in-use'
        elif MAYBE.search(blob):
            verdict = 'candidate'
        elif DEAD.search(blob):
            verdict = 'confirmed-dead'
        out[nm] = {'row': r, 'verdict': verdict, 'status_text': blob.strip()}
    return out

# ------------------------------------------------------------------ deletion-tracker keys
# One stable "<category>:<id>" key per finding. The HTML report puts it on each row's checkbox,
# --json emits it on each finding, and the progress files / cleanup journal store it — so all of
# them must be built here, never inline.
TK = {
    'page': lambda r: 'page:' + str(r['inner_id']),
    'reusable': lambda r: 'reusable:' + str(r['inner_id']),
    'workflow': lambda r: 'workflow:' + str(r['inner_id']),
    'optionset': lambda r: 'optionset:' + str(r['name']),
    'style': lambda r: 'style:' + str(r['id']),
    'colorvar': lambda r: 'colorvar:' + str(r['id']),
    'fontvar': lambda r: 'fontvar:' + str(r['id']),
    'plugin': lambda r: 'plugin:' + str(r['id']),
    'datatype': lambda r: 'datatype:' + str(r['type_key']),
    'field': lambda r: 'field:' + r['type_key'] + '.' + r['field_key'],
    'customevent': lambda r: 'customevent:' + str(r['id']),
    'pagewf': lambda r: 'pagewf:' + str(r['id']),
    'hiddenwf': lambda r: 'hiddenwf:' + str(r['id']),
    'mobileview': lambda r: 'mobileview:' + str(r['inner_id']),
    'mobilenav': lambda r: 'mobilenav:' + str(r['target']) + ':' + str(r['container']),
    'apicall': lambda r: 'apicall:' + str(r['ref']),
    'ghostref': lambda r: 'ghostref:' + r['plugin_id'] + ':' + (r['container'] or '') + ':' + (r['location'] or ''),
}

def keyed(rows, kind, **extra):
    """Copies of finding rows with their tracker key (plus fixed extra fields) for --json."""
    return [dict(r, key=TK[kind](r), **extra) for r in rows]

# ------------------------------------------------------------------ export integrity
def analyze_export_integrity(data):
    """Reusable definitions the editor index knows about but whose payload is missing from the
    export. Bubble stopped inlining reusable definitions in the export of some large apps; when
    that happens every reference made from INSIDE those reusables (navigation, option sets,
    styles, plugin elements, scheduled backend workflows…) is invisible, so findings in every
    section can be false positives. Same signal as befree-bubble-mcp's
    context/export_inspect.py (MIT), reimplemented here so the audit stays stdlib-only."""
    defs = data.get('element_definitions') or {}
    material = {k for k, v in defs.items() if k != 'length' and isinstance(v, dict)}
    id_to_path = (data.get('_index') or {}).get('id_to_path') or {}
    roots, deep = set(), set()
    for path in id_to_path.values():
        parts = [x for x in str(path or '').split('.') if x]
        if len(parts) < 2 or parts[0] not in ('%ed', 'element_definitions') or parts[1] == 'length':
            continue
        (roots if len(parts) == 2 else deep).add(parts[1])
    names = {}
    for nm, raw in ((data.get('_index') or {}).get('custom_name_to_id') or {}).items():
        rid = (raw.get('custom_id') or raw.get('id')) if isinstance(raw, dict) else raw
        if rid:
            names.setdefault(str(rid), str(nm))
    missing = sorted(roots - material)
    # present but hollow: the index has nodes under the definition, the export has no tree for it
    hollow = sorted(k for k in (material & deep)
                    if not (defs[k].get('elements') or defs[k].get('workflows')))
    sample = [{'id': k, 'name': names.get(k)} for k in (missing + hollow)[:30]]
    return {'reusable_definitions': len(material), 'indexed_definitions': len(roots),
            'missing_payload': len(missing), 'hollow_payload': len(hollow),
            'incomplete': bool(missing or hollow), 'sample': sample}

def load_provenance(export_path):
    """Optional provenance sidecar written next to an export downloaded through the connected mode
    (`<export>.meta.json`: app version, fetched_at, sha256). Absent for manual exports."""
    p = export_path + '.meta.json'
    try:
        with open(p, encoding='utf-8') as f:
            j = json.load(f)
        return j if isinstance(j, dict) else None
    except (OSError, ValueError):
        return None

# ------------------------------------------------------------------ progress state (round-trips with the report's Export)
def load_evidence(paths, app_name):
    """Runtime evidence written by the connected mode (unbubble:connect runtime_evidence.py):
    per tracker key, how often the candidate shows up in the app's server logs in a window.
    Repeatable; later files win for the same key. A file for another app is ignored."""
    if isinstance(paths, str):
        paths = [paths]
    by_key, meta, used = {}, {}, 0
    for path in paths or []:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            log('evidence: cannot read', path, '-', exc)
            continue
        if not isinstance(data, dict) or not isinstance(data.get('candidates'), list):
            log('evidence: not a runtime-evidence file, ignored:', path)
            continue
        if data.get('app') and data.get('app') != app_name:
            log('evidence: file is for app %r, not %r - ignored: %s' % (data.get('app'), app_name, path))
            continue
        used += 1
        meta = {'window': data.get('window') or {}, 'app_version': data.get('app_version'),
                'method': data.get('method')}
        for row in data['candidates']:
            if isinstance(row, dict) and row.get('key'):
                by_key[row['key']] = {'hits': row.get('hits'), 'first_seen': row.get('first_seen'),
                                      'last_seen': row.get('last_seen'), 'coverage': row.get('coverage')}
    if not used:
        return None
    counts = {'seen': sum(1 for v in by_key.values() if v['hits']),
              'not_seen': sum(1 for v in by_key.values() if v['hits'] == 0),
              'unknown': sum(1 for v in by_key.values() if v['hits'] is None)}
    return dict(meta, by_key=by_key, counts=counts, files=used)

def journal_counts(entry):
    """A cleanup-journal entry counts as deleted in the app when the call succeeded and it was
    applied to the development version itself, or to a branch that was later merged into it."""
    if not entry.get('ok', True):
        return False
    return bool(entry.get('merged')) or str(entry.get('app_version') or '').lower() in ('test', 'version-test')

def load_state(paths):
    """Parse progress files into a set of '<category>:<id>' keys. Accepts one path or a list:
    a .md or .json exported from the report (v1 list, v2 object with sections_done), or the
    cleanup journal written by the connected mode (entries applied to test or merged count)."""
    if isinstance(paths, str):
        paths = [paths]
    keys = set()
    for path in paths or []:
        if not path or not os.path.exists(path):
            continue
        txt = open(path, encoding='utf-8').read()
        if path.lower().endswith('.json'):
            try:
                j = json.loads(txt)
            except ValueError:
                continue
            if isinstance(j, list):
                keys.update(j)
                continue
            if isinstance(j.get('entries'), list):  # cleanup journal
                keys.update(e['key'] for e in j['entries']
                            if isinstance(e, dict) and e.get('key') and journal_counts(e))
                continue
            keys.update(j.get('deleted', []))
            # v2 files: section sign-offs travel as 'section:<id>' keys so the report re-checks them
            keys.update('section:' + str(k) for k in j.get('sections_done', []))
            continue
        keys.update(re.findall(r'-\s*\[[xX]\]\s*`([^`]+)`', txt))  # only checked (- [x]) lines
    return keys

# ------------------------------------------------------------------ HTML report
STR = {
 'pt': {
  'title': 'Relatório de elementos não utilizados', 'sub_src': 'Análise estática do export Bubble',
  'generated': 'gerado em', 'how_title': 'Como ler este relatório',
  'integ_t': 'Export incompleto — revise antes de apagar qualquer coisa',
  'integ_b': '{m} de {n} definições de reutilizáveis aparecem no índice do editor sem o conteúdo no export ({h} vazias). Tudo o que existe dentro delas — navegação, option sets, estilos, elementos de plugin, workflows agendados — ficou invisível para esta análise, então achados de qualquer seção podem ser falsos positivos. Reexporte o app ou baixe o export pelo modo conectado (unbubble:connect), que reidrata as definições, e rode o audit de novo.',
  'integ_sample': 'Exemplos',
  'prov_label': 'export baixado pelo modo conectado', 'prov_version': 'versão',
  'ev_t': 'Evidência de runtime (logs do servidor)',
  'ev_b': 'logs de <span class="mono">{ver}</span>, {d} dias até {end}: <strong>{seen}</strong> candidato(s) vistos, {none} não vistos, {unk} sem evidência. Cada item avaliado ganha um selo “logs:”. “Não visto” cobre só essa janela e a retenção de logs do plano: reforça o “sem uso”, não prova.',
  'ev_seen': 'logs: {n}×', 'ev_seen_t': 'Visto {n}× nos logs de {ver} em {d} dias (última vez {last}): provável uso real — revise antes de apagar.',
  'ev_none': 'logs: 0', 'ev_none_t': 'Não visto nos logs de {ver} em {d} dias (só essa janela e a retenção do plano).',
  'ev_unk': 'logs: ?', 'ev_unk_t': 'Sem evidência: a consulta falhou, foi parcial ou passou do limite de candidatos.',
  'how_body': 'Cada item tem um grau de confiança. Em Bubble, “não referenciado” nem sempre significa “seguro para excluir”: páginas têm URL pública própria (podem ser abertas por link direto, e-mail ou iframe/embed) e plugins podem rodar no servidor sem elemento visível. Backend workflows, option sets, reutilizáveis e estilos têm sinais determinísticos e alta confiança.',
  'c_pages': 'Páginas sem navegação interna', 'c_reuse': 'Reutilizáveis não usados',
  'c_back': 'Backend workflows inalcançáveis', 'c_opt': 'Option Sets sem uso',
  'c_plug': 'Plugins órfãos', 'c_sty': 'Estilos não usados', 'of': 'de',
  's_pages': '1 · Páginas que podem ser excluídas',
  'q_pages': 'Quais páginas podem ser excluídas por não estarem sendo utilizadas?',
  's_reuse': '2 · Elementos reutilizáveis que podem ser excluídos',
  'q_reuse': 'Quais elementos reutilizáveis podem ser excluídos por não serem utilizados?',
  's_back': '3 · Backend workflows não usados e não expostos como API',
  'q_back': 'Quais backend workflows não são utilizados e não estão expostos como endpoint API?',
  's_opt': '4 · Option Sets sem uso', 'q_opt': 'Quais Option Sets não são utilizados em nenhuma parte do sistema?',
  's_plug': '5 · Plugins instalados sem uso', 'q_plug': 'Quais plugins instalados não estão sendo usados em nenhuma parte do sistema?',
  's_sty': '6 · Estilos não usados', 'q_sty': 'Quais estilos não estão sendo usados em nenhum elemento?',
  's_var': '6b · Variáveis de cor e fonte sem uso',
  'var_body': 'Variáveis (design tokens) definidas pelo usuário que não são referenciadas por nenhum elemento nem estilo (nenhum <code>var(--color_&lt;id&gt;)</code> / <code>var(--font_&lt;id&gt;)</code>). Ids de token colidem com ids de elemento e o tema é duplicado no export, então a contagem crua do id é enganosa — por isso usamos a forma <code>var()</code>. Onde excluir no editor: aba <b>Styles</b> → seções <b>Color variables</b> / <b>Font variables</b> (o App Search Tool não indexa variáveis — procure na própria lista). Entradas <b>“Pasted Color #&lt;id&gt;”</b> são criadas automaticamente pelo Bubble quando elementos copiados de outro app são colados; ficam no fim da lista, com nomes quase iguais e muitas vezes a mesma cor.',
  'th_var': 'Variável', 'th_rgba': 'Cor (rgba)', 'th_family': 'Fonte (família)',
  'var_colors_h': 'Cores', 'var_fonts_h': 'Fontes',
  'var_none_c': 'Todas as variáveis de cor estão em uso.', 'var_none_f': 'Todas as variáveis de fonte estão em uso.',
  'var_stat': '%d ativas, %d deletadas',
  'confirmed': 'Confirmado morto', 'candidate': 'Candidato a excluir',
  'inuse': 'Em uso (acesso direto/embed)', 'nostatus': 'Sem status na planilha',
  'th_page': 'Página', 'th_class': 'Classificação', 'th_id': 'ID interno', 'th_reuse': 'Elemento reutilizável',
  'th_wf': 'Workflow (wf_name)', 'th_folder': 'Pasta', 'th_sit': 'Situação',
  'th_os': 'Nome (chave)', 'th_osd': 'Rótulo', 'th_sty': 'Estilo', 'th_styt': 'Tipo', 'th_styid': 'ID',
  'th_plug': 'Plugin', 'th_author': 'Autor', 'th_ver': 'Versão', 'th_obs': 'Observação',
  'nav_never': 'nunca disparado', 'nav_trans': 'só chamado por WF morto', 'legacy': 'nome-legado',
  'filter_page': 'filtrar por nome da página…', 'filter_wf': 'filtrar por nome do workflow…',
  'all': 'Todas', 'noname': '(nome só visível no editor)',
  'reuse_body': 'nunca são inseridos em nenhuma página, view mobile ou outro reutilizável (nenhum <code>CustomElement.custom_id</code> aponta para eles). Confiança alta.',
  'th_twin': 'Gêmeo em uso (ID)', 'twin_in_use': 'em uso',
  'dup_reuse_t': '2b · Nome duplicado — VERIFICAR antes de excluir',
  'dup_reuse_b': '<strong>Não exclua às cegas.</strong> Estes reutilizáveis não são inseridos em lugar nenhum, MAS existe outro reutilizável com o <strong>nome idêntico</strong> que está em uso (coluna “Gêmeo em uso”). A busca do Bubble é por NOME, então ela mostra os usos do gêmeo sob este elemento — fazendo-o parecer usado. Confirme pelo <strong>ID</strong> qual você vai excluir; provavelmente este aqui é uma cópia órfã, mas verifique.',
  'back_body': 'API workflows (tipo <code>APIEvent</code>). Um <code>APIEvent</code> não exposto só roda se for agendado internamente (<code>Schedule API workflow</code>). Os “diretos” não estão expostos e o ID não aparece em nenhum agendamento — não há como executá-los hoje. <strong>Exposição:</strong> workflows sem a chave <code>expose</code> no export são tratados como <strong>expostos</strong> (default do Bubble; o export só grava <code>expose: false</code> quando a caixa é desmarcada). Workflows chamados pelo próprio app via <strong>API Connector</strong> (self-call para <code>/wf/&lt;nome&gt;</code>) também contam como usados.',
  'exposed': 'expostos como endpoint público', 'direct': 'Inalcançáveis (diretos)', 'trans': 'Mortos transitivos',
  'opt_body': 'A expressão canônica <code>option.&lt;nome&gt;</code> não aparece em nenhum elemento, campo, workflow ou condição.',
  'plug_used': 'têm elementos, ações ou chamadas de API em uso.',
  'plug_used_t': '5c · Plugins em uso (referência)',
  'plug_used_b': 'Plugins com elementos, ações ou chamadas em uso — mantidos. Listados aqui só para referência: nome + link do marketplace.',
  'plug_open': 'abrir no marketplace', 'plug_delisted': 'página indisponível — provavelmente removido',
  'plug_orphan_t': '5a · Órfãos — candidatos à remoção (revisar)',
  'plug_orphan_b': 'Instalados mas sem nenhum elemento, ação, chamada de API ou configuração no export. <strong>Atenção:</strong> alguns plugins agem <strong>globalmente só por estarem instalados</strong> (CSS por ID de elemento como o <em>Classify</em>, SEO, headers, analytics) e não deixam rastro no export — se reconhecer um plugin global nesta lista, verifique antes de remover.',
  'plug_cfg_t': '5b · Sem elemento visível, mas ativos de outra forma — verificar',
  'plug_cfg_b': 'Sem elemento na tela, mas ativos: com chaves de API/headers/credenciais (login, DocuSign, Mailchimp), ou <strong>globais só por estarem instalados</strong> (ex.: <em>Classify</em> aplica CSS por ID). Podem rodar no servidor ou no projeto todo — não remover sem confirmar.',
  'plug_global': 'global', 'plug_paid': '💲 pago',
  'c_plug_paid': 'Plugins pagos sem uso',
  'plug_paid_alert': 'plugins PAGOS instalados mas sem uso — custo recorrente/desperdiçado. Priorize a revisão. (Preço pesquisado no marketplace; confirme antes de cancelar a assinatura/licença.)',
  'sty_body': 'Nenhum elemento tem <code>"style":"&lt;id&gt;"</code> apontando para eles e não são estilo padrão de nenhum tipo.',
  'caveat_pages': 'Atenção — falsos positivos esperados. Páginas Bubble têm URL pública; muitas “sem navegação interna” são portais de acesso direto ou embed. Há {L} ações <code>ListGoToPage</code> e {D} navegações dinâmicas cujo destino não é resolvível estaticamente. Não exclua nada só por aparecer aqui.',
  'refurl_t': 'Referenciadas por URL/nome (invisível ao scan de navegação) — MANTER',
  'refurl_b': 'Estas páginas não têm navegação interna por ID, mas o NOME (slug) aparece como URL real do app em um link, Run JavaScript, HTML embed ou script — tipicamente callbacks OAuth e links em e-mails/mensagens. <strong>Não são candidatas a exclusão</strong> e já foram removidas da lista acima.',
  'th_ev': 'Evidência (onde o nome aparece)', 'th_hits': 'URLs',
  'th_del': 'Excluído?', 'trk_hint': 'marcados como já excluídos no Bubble',
  'trk_export_md': '⬇ Exportar .md', 'trk_export_md_t': 'Baixa um checklist .md (versionável, reimportável, aceito por --state)',
  'trk_export_json': '⬇ .json', 'trk_import': '⬆ Importar', 'trk_clear': 'Limpar',
  'md_hint': 'As chaves entre crases sao de maquina — edite os checkboxes, nao as chaves. Reimporte este arquivo ou passe-o em bubble_audit.py --state.',
  'clear_confirm': 'Limpar todas as marcacoes de exclusao?',
  'sec_done': 'Auditoria desta seção concluída',
  'sec_done_t': 'Marque quando a seção estiver revisada. Itens não excluídos ficam registrados como mantidos de propósito, e a etapa de clone vai perguntar se entram na paridade.',
  'sec_done_pill': '✓ seção concluída', 'kept_tag': 'mantido', 'trk_sections': 'seções concluídas',
  'sync_saved': '● salvo no console', 'sync_saving': '● salvando…', 'sync_err': '● falha ao salvar no console', 'sync_ready': '● console conectado',
  'md_kept': 'mantido de propósito',
  'nv_p': 'Páginas', 'nv_r': 'Reutilizáveis', 'nv_b': 'Backend WF', 'nv_o': 'Option Sets',
  'nv_ap': 'APIs',
  's_api': '9 · API Connector — endpoints declarados sem uso',
  'q_api': 'Quais chamadas de API declaradas no API Connector nunca são usadas (nem como data source nem como action)?',
  'api_body': 'Chamadas declaradas no API Connector que não aparecem em nenhuma das duas formas de uso: ação de workflow (type <code>apiconnector2-&lt;api&gt;.&lt;call&gt;</code>) nem fonte de dados (<code>provider: apiconnector2.&lt;api&gt;.&lt;call&gt;</code>). Chamadas de OAuth/<em>token</em> (disparadas automaticamente pela autenticação) são tratadas como usadas. Resíduo a verificar: chamadas montadas dinamicamente.',
  'c_api': 'Endpoints de API sem uso',
  'th_provider': 'API (provider)', 'th_endpoint': 'Endpoint (call)', 'th_method': 'Método',
  'api_none': 'Todas as chamadas de API declaradas são usadas.', 'filter_api': 'filtrar por API / endpoint…',
  'api_self': '→ workflow interno:',
  'nv_g': 'Removidos', 'c_ghost': 'Refs a plugins removidos',
  's_ghost': '10 · Plugins removidos ainda referenciados (referências quebradas)',
  'q_ghost': 'Quais plugins foram removidos do projeto mas ainda têm elementos/ações que os referenciam?',
  'ghost_body': 'Estes elementos/ações usam o tipo <code>&lt;pluginId&gt;-…</code> de um plugin que <strong>não está mais na lista de plugins instalados</strong> — o plugin foi desinstalado mas as referências ficaram, então provavelmente estão <strong>quebradas</strong>. Corrija: reinstale o plugin OU remova o elemento/ação. (Nome do plugin resolvido no marketplace.)',
  'ghost_none': 'Nenhuma referência a plugin removido.',
  'th_where': 'Onde', 'th_loc': 'Elemento / Workflow', 'filter_ghost': 'filtrar por plugin / página / elemento…',
  'gw_element': 'elemento', 'gw_action': 'ação de WF', 'gw_trigger': 'gatilho de WF',
  'nv_pl': 'Plugins', 'nv_s': 'Estilos', 'nv_d': 'Dados', 'nv_m': 'Metodologia',
  'c_dtF': 'Campos sem uso', 'c_dtT': 'Tabelas sem uso',
  's_dt': '7 · Campos e tabelas (dados) sem uso',
  'q_dt': 'Quais campos e tabelas nunca são usados, e o que está exposto na Data API?',
  'dt_tables_t': '7a · Tabelas (tipos de dados) sem nenhuma referência',
  'dt_tables_b': 'Tipo não referenciado como <code>custom.&lt;tipo&gt;</code> em lugar nenhum, sem nenhum campo usado, não exposto na Data API e não citado em script. Excluir um tipo apaga os dados dele — confirme que não há dados a preservar.',
  'dt_fields_t': '7b · Campos sem uso',
  'dt_fields_b': 'Campos cuja chave não aparece em nenhuma expressão, elemento, workflow, search ou script (JS/HTML). Já descontados os campos e tabelas na lixeira.',
  'dt_none_tables': 'Nenhuma tabela totalmente órfã — todas são referenciadas, têm campo usado ou estão expostas.',
  'th_table': 'Tabela', 'th_field': 'Campo', 'th_key': 'Chave (interna)', 'th_ftype': 'Tipo', 'th_api': 'Data API?',
  'st_unused': 'sem uso', 'st_api': 'exposto na Data API', 'api_yes': 'exposto', 'api_no': '—',
  'dt_exposed_note': 'campos sem uso interno mas cuja tabela está exposta na Data API — podem ter consumidores externos; verifique antes de excluir.',
  'dt_deleted_note': 'campos já deletados (lixeira) e', 'dt_tables_deleted': 'tabelas já deletadas;',
  'dt_exposed_tables': 'tabelas expostas na Data API.',
  'nv_w': 'Auditoria WF',
  's_wf': '8 · Auditoria de workflows (páginas & reusáveis)',
  'q_wf': 'Quais Custom Events nunca são chamados e quais workflows têm gatilho que nunca dispara?',
  'wf_bce_t': 'Custom Events do Backend nunca chamados',
  'wf_bce_b': 'Custom Events no backend cujo id não é alvo de nenhum Trigger/Schedule custom event em lugar nenhum.',
  'wf_ce_t': '8a · Custom Events (páginas/reusáveis) nunca chamados',
  'wf_ce_b': 'Custom Events definidos em páginas ou reusáveis que nenhum Trigger/Schedule custom event dispara. Confiança alta.',
  'wf_orphan_t': '8b · Workflows com gatilho em elemento inexistente no container',
  'wf_orphan_b': 'O evento está ligado a um <code>element_id</code> que não existe na árvore de elementos da própria página/reusável. Duas causas: o elemento foi <strong>deletado</strong>, ou foi <strong>movido para um reusável</strong> — o “convert to reusable” do Bubble move os elementos, mas deixa para trás o workflow do container original (o elemento ganha workflows novos dentro do reusável). Nos dois casos o workflow listado nunca dispara — a coluna “Onde está o elemento” mostra a evidência. Confiança alta.',
  'wf_orphan_moved': 'movido para', 'wf_orphan_del': 'não existe mais (deletado)',
  'th_elemwhere': 'Onde está o elemento',
  'wf_hidden_t': '8c · Workflows com gatilho em elemento que nunca é renderizado',
  'wf_hidden_b': 'Agora <strong>com as condicionais consideradas</strong> (aba <em>Conditional</em> = <code>states</code>). O gatilho está ligado a um elemento que <strong>nunca aparece na tela</strong>: nem ele nem nenhum grupo-pai pode ficar visível — <code>is_visible</code> padrão = não, nenhuma ação Show/Toggle/Animate e nenhuma condicional que o exiba. A coluna <em>Motivo</em> mostra se é o próprio elemento ou um grupo-pai oculto. Resíduo a verificar: condicionais cujo resultado nunca é verdadeiro, visibilidade via plugin/JS, ou regras de responsividade.',
  'th_trigger': 'Gatilho', 'th_container': 'Página/Reusável', 'th_event': 'Custom Event', 'th_elem': 'Elemento',
  'th_reason': 'Motivo', 'wf_h_self': 'elemento nunca exibido', 'wf_h_anc': 'grupo-pai oculto:',
  'wf_kp': 'página', 'wf_kr': 'reusável', 'wf_km': 'view mobile',
  'mob_t': '1b · Views do app nativo (mobile) nunca navegadas',
  'mob_b': 'O app nativo tem suas próprias views (<code>mobile_views</code>). Uma view só é alcançável por: ser a <strong>view inicial</strong>, ter papel de sistema (<code>built_in_mobile_views</code>, ex.: update_app, reset_password) ou ser destino de uma ação <strong>MobileNavigate</strong>. As views abaixo não têm navegação nem papel de sistema. Ressalva: deep links e push notifications podem abrir views diretamente — confirme antes de excluir.',
  'mob_roles': 'Views de sistema (sempre mantidas):', 'mob_initial': 'view inicial',
  'mob_none': 'Todas as views mobile são navegadas ou têm papel de sistema.',
  'mob_dup_t': 'Views sem navegação com gêmea de mesmo nome EM USO — verificar',
  'mob_dup_b': 'Nenhuma navegação aponta para estas views, mas existe OUTRA view com exatamente o mesmo nome que está em uso. O App Search Tool do Bubble busca “Go to view …” por nome (os usos da gêmea parecem desta) e o App Manager costuma exibir <strong>uma entrada só</strong> para nomes duplicados — a view morta fica invisível na lista. <strong>Como achar:</strong> abra a que aparece, confirme que é a viva (conteúdo completo), <strong>renomeie-a temporariamente</strong> — a gêmea oculta então aparece na lista; delete-a e desfaça o rename. Confira sempre pelo ID interno e pelo conteúdo antes de excluir.',
  'mob_broken_t': 'Navegações mobile quebradas (destino não existe)',
  'mob_broken_b': 'Ações <code>MobileNavigate</code> cujo destino não corresponde a nenhuma view existente — a view foi deletada e a ação falha silenciosamente em runtime. Remova a ação (ou o workflow que a contém).',
  'th_view': 'View', 'th_navs': 'Navegações para ela', 'th_wfs': 'Workflows', 'th_target': 'Destino (id)',
  'mob_disabled': 'workflow desativado', 'c_mob': 'Views mobile sem uso', 'mob_card_of': 'app nativo',
  'c_wf': 'Custom Events sem uso', 'c_wf_orphan': 'WF em elemento inexistente',
  'method': 'Metodologia & limites', 'already_deleted': 'já deletados',
  'pages_none': 'Todas as páginas são navegadas ou referenciadas — nenhuma candidata a exclusão.',
  'reuse_none': 'Todos os elementos reutilizáveis estão em uso.',
  'back_none': 'Todos os backend workflows estão alcançáveis — expostos como endpoint ou agendados internamente.',
  'opt_none': 'Todos os Option Sets estão em uso.',
  'plug_none_orphan': 'Nenhum plugin órfão — todos os plugins instalados têm uso identificado.',
  'plug_none_cfg': 'Nenhum plugin nesta situação.',
  'sty_none': 'Todos os estilos estão aplicados a pelo menos um elemento.',
  'dt_none_fields': 'Todos os campos estão em uso.',
  'wf_bce_none': 'Todos os Custom Events do backend são chamados.',
  'wf_ce_none': 'Todos os Custom Events de páginas/reusáveis são chamados.',
  'wf_orphan_none': 'Nenhum workflow com gatilho em elemento inexistente.',
  'back_wh_t': 'Possíveis webhooks — verificar antes de excluir',
  'back_wh_b': 'Workflows com <strong>Parameter definition = “Detect request data”</strong> (<code>parameter_def: auto</code>) — assinatura típica de <strong>webhook</strong> inicializado por um serviço externo (o export guarda o payload de exemplo capturado na inicialização). Quem chama é um serviço de fora (ex.: um gateway de pagamento), invisível à análise estática, então estes NÃO entram na lista de exclusão. Atenção: se “Expose as a public API workflow” estiver <strong>desmarcado</strong>, o Bubble não atende chamadas externas — confirme no ambiente live se o webhook ainda está ativo e, se estiver em uso, marque o expose.',
  'wh_exposed': 'Exposto?', 'wh_yes': 'sim', 'wh_no': 'NÃO — não atende chamada externa hoje',
  'wh_payload': 'payload de exemplo capturado',
  'wf_hidden_none': 'Nenhum workflow com gatilho em elemento que nunca é renderizado.',
 },
 'en': {
  'title': 'Unused-elements report', 'sub_src': 'Static analysis of a Bubble export',
  'generated': 'generated', 'how_title': 'How to read this report',
  'integ_t': 'Incomplete export — review before deleting anything',
  'integ_b': '{m} of {n} reusable definitions appear in the editor index without their content in the export ({h} hollow). Everything inside them — navigation, option sets, styles, plugin elements, scheduled workflows — is invisible to this analysis, so findings in any section may be false positives. Re-export the app or download the export through the connected mode (unbubble:connect), which re-hydrates the definitions, and run the audit again.',
  'integ_sample': 'Examples',
  'prov_label': 'export downloaded through the connected mode', 'prov_version': 'version',
  'ev_t': 'Runtime evidence (server logs)',
  'ev_b': 'logs of <span class="mono">{ver}</span>, {d} days up to {end}: <strong>{seen}</strong> candidate(s) seen, {none} not seen, {unk} without evidence. Every evaluated item carries a “logs:” badge. “Not seen” covers only this window and the plan\'s log retention: it strengthens “unused”, it does not prove it.',
  'ev_seen': 'logs: {n}×', 'ev_seen_t': 'Seen {n}× in the {ver} logs over {d} days (last {last}): likely in real use — review before deleting.',
  'ev_none': 'logs: 0', 'ev_none_t': 'Not seen in the {ver} logs over {d} days (this window and the plan\'s retention only).',
  'ev_unk': 'logs: ?', 'ev_unk_t': 'No evidence: the query failed, was partial or went over the candidate cap.',
  'how_body': 'Each item has a confidence level. In Bubble, “unreferenced” does not always mean “safe to delete”: pages have their own public URL (openable via direct link, email or iframe/embed) and plugins can run server-side with no visible element. Backend workflows, option sets, reusables and styles have deterministic signals and high confidence.',
  'c_pages': 'Pages with no internal navigation', 'c_reuse': 'Unused reusables',
  'c_back': 'Unreachable backend workflows', 'c_opt': 'Unused Option Sets',
  'c_plug': 'Orphaned plugins', 'c_sty': 'Unused styles', 'of': 'of',
  's_pages': '1 · Pages that can be deleted',
  'q_pages': 'Which pages can be deleted because they are not used?',
  's_reuse': '2 · Reusable elements that can be deleted',
  'q_reuse': 'Which reusable elements can be deleted because they are not used?',
  's_back': '3 · Backend workflows unused and not exposed as an API',
  'q_back': 'Which backend workflows are unused and not exposed as an API endpoint?',
  's_opt': '4 · Unused Option Sets', 'q_opt': 'Which Option Sets are not used anywhere?',
  's_plug': '5 · Installed but unused plugins', 'q_plug': 'Which installed plugins are not used anywhere?',
  's_sty': '6 · Unused styles', 'q_sty': 'Which styles are not used by any element?',
  's_var': '6b · Unused color & font variables',
  'var_body': 'User-defined variables (design tokens) referenced by no element or style (no <code>var(--color_&lt;id&gt;)</code> / <code>var(--font_&lt;id&gt;)</code>). Token ids collide with element ids and the theme is snapshotted many times in the export, so a bare-id count is misleading — we use the <code>var()</code> form instead. Where to delete them in the editor: <b>Styles</b> tab → <b>Color variables</b> / <b>Font variables</b> sections (the App Search Tool does not index variables — scan the list itself). <b>“Pasted Color #&lt;id&gt;”</b> entries are auto-created by Bubble when elements copied from another app are pasted; they sit at the end of the list, with near-identical names and often the same color.',
  'th_var': 'Variable', 'th_rgba': 'Color (rgba)', 'th_family': 'Font (family)',
  'var_colors_h': 'Colors', 'var_fonts_h': 'Fonts',
  'var_none_c': 'All color variables are in use.', 'var_none_f': 'All font variables are in use.',
  'var_stat': '%d active, %d deleted',
  'confirmed': 'Confirmed dead', 'candidate': 'Deletion candidate',
  'inuse': 'In use (direct/embed)', 'nostatus': 'No sheet status',
  'th_page': 'Page', 'th_class': 'Classification', 'th_id': 'Internal ID', 'th_reuse': 'Reusable element',
  'th_wf': 'Workflow (wf_name)', 'th_folder': 'Folder', 'th_sit': 'Status',
  'th_os': 'Name (key)', 'th_osd': 'Label', 'th_sty': 'Style', 'th_styt': 'Type', 'th_styid': 'ID',
  'th_plug': 'Plugin', 'th_author': 'Author', 'th_ver': 'Version', 'th_obs': 'Note',
  'nav_never': 'never triggered', 'nav_trans': 'only called by dead WF', 'legacy': 'legacy-name',
  'filter_page': 'filter by page name…', 'filter_wf': 'filter by workflow name…',
  'all': 'All', 'noname': '(name only visible in editor)',
  'reuse_body': 'are never placed on any page, mobile view or other reusable (no <code>CustomElement.custom_id</code> points to them). High confidence.',
  'th_twin': 'Used twin (ID)', 'twin_in_use': 'in use',
  'dup_reuse_t': '2b · Duplicate name — VERIFY before deleting',
  'dup_reuse_b': '<strong>Do not delete blindly.</strong> These reusables are placed nowhere, BUT another reusable with the <strong>exact same name</strong> IS in use (see “Used twin”). Bubble\'s search matches by NAME, so it shows the twin\'s usages under this element — making it look used. Confirm by <strong>ID</strong> which one you delete; this one is likely an orphaned copy, but verify.',
  'back_body': 'API workflows (type <code>APIEvent</code>). A non-exposed <code>APIEvent</code> can only run if scheduled internally (<code>Schedule API workflow</code>). The “direct” ones are not exposed and their id appears in no scheduling action — they cannot run today. <strong>Exposure:</strong> workflows with no <code>expose</code> key in the export are treated as <strong>exposed</strong> (Bubble default; the export only writes <code>expose: false</code> when the box is unchecked). Workflows the app calls on itself via the <strong>API Connector</strong> (self-call to <code>/wf/&lt;name&gt;</code>) also count as used.',
  'exposed': 'exposed as a public endpoint', 'direct': 'Unreachable (direct)', 'trans': 'Transitively dead',
  'opt_body': 'The canonical expression <code>option.&lt;name&gt;</code> appears in no element, field, workflow or condition.',
  'plug_used': 'have elements, actions or API calls in use.',
  'plug_used_t': '5c · Plugins in use (reference)',
  'plug_used_b': 'Plugins with elements, actions or calls in use — kept. Listed here for reference only: name + marketplace link.',
  'plug_open': 'open in marketplace', 'plug_delisted': 'page unavailable — likely delisted',
  'plug_orphan_t': '5a · Orphaned — removal candidates (review)',
  'plug_orphan_b': 'Installed but with no element, action, API call or configuration in the export. <strong>Heads up:</strong> some plugins act <strong>globally just by being installed</strong> (CSS-by-element-id like <em>Classify</em>, SEO, headers, analytics) and leave no trace in the export — if you recognize a global plugin here, verify before removing.',
  'plug_cfg_t': '5b · No visible element, but active another way — verify',
  'plug_cfg_b': 'No on-screen element, but active: API keys/headers/credentials (login, DocuSign, Mailchimp), or <strong>global just by being installed</strong> (e.g. <em>Classify</em> applies CSS by element id). May run server-side or project-wide — do not remove without confirming.',
  'plug_global': 'global', 'plug_paid': '💲 paid',
  'c_plug_paid': 'Unused paid plugins',
  'plug_paid_alert': 'PAID plugins installed but unused — recurring/wasted cost. Prioritize review. (Price researched from the marketplace; confirm before cancelling the subscription/licence.)',
  'sty_body': 'No element has <code>"style":"&lt;id&gt;"</code> pointing to them and they are not the default style of any type.',
  'caveat_pages': 'Heads up — expected false positives. Bubble pages have a public URL; many with “no internal navigation” are direct-access or embed portals. There are {L} <code>ListGoToPage</code> actions and {D} dynamic navigations whose target is not statically resolvable. Do not delete anything just because it appears here.',
  'refurl_t': 'Referenced by URL/name (invisible to the nav scan) — KEEP',
  'refurl_b': 'These pages have no internal id-navigation, but their NAME (slug) appears as a real app URL in a link, Run JavaScript, HTML embed or script — typically OAuth callbacks and links in emails/messages. <strong>They are not deletion candidates</strong> and were removed from the list above.',
  'th_ev': 'Evidence (where the name appears)', 'th_hits': 'URLs',
  'th_del': 'Deleted?', 'trk_hint': 'marked as already deleted in Bubble',
  'trk_export_md': '⬇ Export .md', 'trk_export_md_t': 'Downloads a .md checklist (git-friendly, re-importable, accepted by --state)',
  'trk_export_json': '⬇ .json', 'trk_import': '⬆ Import', 'trk_clear': 'Clear',
  'md_hint': 'Backticked keys are machine-readable — edit the checkboxes, not the keys. Re-import this file or pass it to bubble_audit.py --state.',
  'clear_confirm': 'Clear all deletion marks?',
  'sec_done': 'Audit of this section complete',
  'sec_done_t': 'Tick when the section is reviewed. Items not deleted are recorded as kept on purpose, and the clone step will ask whether they enter parity.',
  'sec_done_pill': '✓ section complete', 'kept_tag': 'kept', 'trk_sections': 'sections complete',
  'sync_saved': '● saved to console', 'sync_saving': '● saving…', 'sync_err': '● could not save to console', 'sync_ready': '● console connected',
  'md_kept': 'kept on purpose',
  'nv_p': 'Pages', 'nv_r': 'Reusables', 'nv_b': 'Backend WF', 'nv_o': 'Option Sets',
  'nv_ap': 'APIs',
  's_api': '9 · API Connector — declared endpoints never used',
  'q_api': 'Which API Connector calls are declared but never used (as a data source or an action)?',
  'api_body': 'Calls declared in the API Connector that appear in neither usage form: workflow action (type <code>apiconnector2-&lt;api&gt;.&lt;call&gt;</code>) nor data source (<code>provider: apiconnector2.&lt;api&gt;.&lt;call&gt;</code>). OAuth/<em>token</em> calls (fired automatically by authentication) are treated as used. Residual to verify: calls assembled dynamically.',
  'c_api': 'Unused API endpoints',
  'th_provider': 'API (provider)', 'th_endpoint': 'Endpoint (call)', 'th_method': 'Method',
  'api_none': 'All declared API calls are used.', 'filter_api': 'filter by API / endpoint…',
  'api_self': '→ internal workflow:',
  'nv_g': 'Removed', 'c_ghost': 'Refs to removed plugins',
  's_ghost': '10 · Removed plugins still referenced (broken references)',
  'q_ghost': 'Which plugins were removed from the project but still have elements/actions referencing them?',
  'ghost_body': 'These elements/actions use the type <code>&lt;pluginId&gt;-…</code> of a plugin that is <strong>no longer in the installed-plugins list</strong> — the plugin was uninstalled but the references remained, so they are probably <strong>broken</strong>. Fix: reinstall the plugin OR remove the element/action. (Plugin name resolved from the marketplace.)',
  'ghost_none': 'No references to removed plugins.',
  'th_where': 'Where', 'th_loc': 'Element / Workflow', 'filter_ghost': 'filter by plugin / page / element…',
  'gw_element': 'element', 'gw_action': 'WF action', 'gw_trigger': 'WF trigger',
  'nv_pl': 'Plugins', 'nv_s': 'Styles', 'nv_d': 'Data', 'nv_m': 'Methodology',
  'c_dtF': 'Unused fields', 'c_dtT': 'Unused tables',
  's_dt': '7 · Unused data fields and tables',
  'q_dt': 'Which fields and tables are never used, and what is exposed in the Data API?',
  'dt_tables_t': '7a · Tables (data types) with no reference at all',
  'dt_tables_b': 'Type not referenced as <code>custom.&lt;type&gt;</code> anywhere, with no field used, not exposed in the Data API and not named in any script. Deleting a type deletes its data — confirm there is nothing to keep.',
  'dt_fields_t': '7b · Unused fields',
  'dt_fields_b': 'Fields whose key appears in no expression, element, workflow, search or script (JS/HTML). Already-trashed fields and tables are excluded.',
  'dt_none_tables': 'No fully orphaned table — all are referenced, have a used field, or are exposed.',
  'th_table': 'Table', 'th_field': 'Field', 'th_key': 'Key (internal)', 'th_ftype': 'Type', 'th_api': 'Data API?',
  'st_unused': 'unused', 'st_api': 'exposed in Data API', 'api_yes': 'exposed', 'api_no': '—',
  'dt_exposed_note': 'fields with no internal use but whose table is exposed in the Data API — they may have external consumers; verify before deleting.',
  'dt_deleted_note': 'fields already deleted (trash) and', 'dt_tables_deleted': 'tables already deleted;',
  'dt_exposed_tables': 'tables exposed in the Data API.',
  'nv_w': 'WF audit',
  's_wf': '8 · Workflow audit (pages & reusables)',
  'q_wf': 'Which Custom Events are never called, and which workflows have a trigger that can never fire?',
  'wf_bce_t': 'Backend Custom Events never called',
  'wf_bce_b': 'Backend Custom Events whose id is the target of no Trigger/Schedule custom-event action anywhere.',
  'wf_ce_t': '8a · Custom Events (pages/reusables) never called',
  'wf_ce_b': 'Custom Events defined on pages or reusables that no Trigger/Schedule custom-event action fires. High confidence.',
  'wf_orphan_t': '8b · Workflows triggered by an element missing from the container',
  'wf_orphan_b': 'The event is bound to an <code>element_id</code> that does not exist in the page/reusable’s own element tree. Two causes: the element was <strong>deleted</strong>, or it was <strong>moved into a reusable</strong> — Bubble’s “convert to reusable” moves the elements but leaves the original container’s workflow behind (the element gets fresh workflows inside the reusable). Either way the listed workflow can never fire — the “Where is the element” column shows the evidence. High confidence.',
  'wf_orphan_moved': 'moved to', 'wf_orphan_del': 'no longer exists (deleted)',
  'th_elemwhere': 'Where is the element',
  'wf_hidden_t': '8c · Workflows triggered by an element that is never rendered',
  'wf_hidden_b': 'Now <strong>with conditionals accounted for</strong> (the <em>Conditional</em> tab = <code>states</code>). The trigger is bound to an element that <strong>never appears on screen</strong>: neither it nor any parent group can become visible — default <code>is_visible</code> = no, no Show/Toggle/Animate action, and no conditional reveals it. The <em>Reason</em> column shows whether it is the element itself or a hidden parent group. Residual to verify: conditionals that never evaluate true, plugin/JS-driven visibility, or responsive rules.',
  'th_trigger': 'Trigger', 'th_container': 'Page/Reusable', 'th_event': 'Custom Event', 'th_elem': 'Element',
  'th_reason': 'Reason', 'wf_h_self': 'element never shown', 'wf_h_anc': 'hidden parent group:',
  'wf_kp': 'page', 'wf_kr': 'reusable', 'wf_km': 'mobile view',
  'mob_t': '1b · Native mobile app views never navigated to',
  'mob_b': 'The native app has its own views (<code>mobile_views</code>). A view is reachable only by being the <strong>initial view</strong>, holding a system role (<code>built_in_mobile_views</code>, e.g. update_app, reset_password) or being the target of a <strong>MobileNavigate</strong> action. The views below have neither navigation nor a system role. Caveat: deep links and push notifications can open views directly — verify before deleting.',
  'mob_roles': 'System views (always kept):', 'mob_initial': 'initial view',
  'mob_none': 'Every mobile view is either navigated to or holds a system role.',
  'mob_dup_t': 'Views never navigated to, with a same-named twin IN USE — verify',
  'mob_dup_b': 'No navigation targets these views, but ANOTHER view with the exact same name is in use. Bubble’s App Search Tool matches “Go to view …” by name (the twin’s usages look like this one’s) and the App Manager tends to show <strong>a single entry</strong> for duplicated names — the dead view is invisible in the list. <strong>How to find it:</strong> open the one shown, confirm it is the live one (full content), <strong>rename it temporarily</strong> — the hidden twin then appears in the list; delete it and undo the rename. Always check the internal ID and the content before deleting.',
  'mob_broken_t': 'Broken mobile navigations (target does not exist)',
  'mob_broken_b': '<code>MobileNavigate</code> actions whose target matches no existing view — the view was deleted and the action silently fails at runtime. Remove the action (or its workflow).',
  'th_view': 'View', 'th_navs': 'Navigations to it', 'th_wfs': 'Workflows', 'th_target': 'Target (id)',
  'mob_disabled': 'workflow disabled', 'c_mob': 'Unused mobile views', 'mob_card_of': 'native app',
  'c_wf': 'Unused Custom Events', 'c_wf_orphan': 'WF on missing element',
  'method': 'Methodology & limits', 'already_deleted': 'already deleted',
  'pages_none': 'Every page is navigated to or referenced — no deletion candidates.',
  'reuse_none': 'All reusable elements are in use.',
  'back_none': 'All backend workflows are reachable — exposed as an endpoint or scheduled internally.',
  'opt_none': 'All Option Sets are in use.',
  'plug_none_orphan': 'No orphaned plugins — every installed plugin has identified usage.',
  'plug_none_cfg': 'No plugins in this situation.',
  'sty_none': 'All styles are applied to at least one element.',
  'dt_none_fields': 'All fields are in use.',
  'wf_bce_none': 'All backend Custom Events are called.',
  'wf_ce_none': 'All page/reusable Custom Events are called.',
  'wf_orphan_none': 'No workflow is triggered by a missing element.',
  'back_wh_t': 'Possible webhooks — verify before deleting',
  'back_wh_b': 'Workflows with <strong>Parameter definition = “Detect request data”</strong> (<code>parameter_def: auto</code>) — the typical signature of a <strong>webhook</strong> initialized by an external service (the export keeps the sample payload captured at initialization). The caller is an outside service (e.g. a payment gateway), invisible to static analysis, so these are NOT listed for deletion. Note: if “Expose as a public API workflow” is <strong>unchecked</strong>, Bubble rejects external calls — check in the live environment whether the webhook is still active and, if in use, tick expose.',
  'wh_exposed': 'Exposed?', 'wh_yes': 'yes', 'wh_no': 'NO — external calls are rejected today',
  'wh_payload': 'sample payload captured',
  'wf_hidden_none': 'No workflow is triggered by a never-rendered element.',
 },
}

def esc(s):
    return html.escape(str(s if s is not None else ''))

def render_html(app_name, date_str, lang, pages, dyn, page_audit, reuse, backend, exposed,
                opt, sty, plug_orphan, plug_cfg, plug_used, plug_total, dt,
                plug_used_list=None, variables=None, wfaudit=None, apicalls=None, ghosts=None,
                initial_deleted=None, mobile=None, integrity=None, provenance=None, evidence=None):
    T = STR[lang]
    initial_deleted = sorted(initial_deleted or [])
    integ = integrity or {}
    integ_block = ''
    if integ.get('incomplete'):
        ex = ', '.join(esc(x['name'] or x['id']) for x in integ.get('sample', [])[:12])
        integ_block = (f"<div class='note' style='border-left-color:var(--red);background:var(--redbg)'>"
                       f"<strong>{T['integ_t']}.</strong> "
                       + T['integ_b'].format(m=integ['missing_payload'] + integ['hollow_payload'],
                                             n=integ['indexed_definitions'], h=integ['hollow_payload'])
                       + (f"<br><span class='dim'>{T['integ_sample']}: <span class='mono'>{ex}</span></span>" if ex else '')
                       + "</div>")
    ev = evidence or {}
    ev_keys = ev.get('by_key') or {}
    ev_win = ev.get('window') or {}
    ev_ver, ev_days = esc(ev.get('app_version') or 'live'), esc(ev_win.get('days') or '?')
    ev_block = ''
    if ev:
        cnt = ev.get('counts') or {}
        ev_block = (f"<div class='note note-amber'><strong>{T['ev_t']}.</strong> "
                    + T['ev_b'].format(ver=ev_ver, d=ev_days, end=esc(str(ev_win.get('end') or '?')[:10]),
                                       seen=cnt.get('seen', 0), none=cnt.get('not_seen', 0),
                                       unk=cnt.get('unknown', 0))
                    + "</div>")

    def ev_tag(key):
        row = ev_keys.get(key)
        if not row:
            return ''
        hits = row.get('hits')
        if hits:
            cls, txt = 'v-orange', T['ev_seen'].format(n=hits)
            tip = T['ev_seen_t'].format(n=hits, ver=ev_ver, d=ev_days, last=esc(str(row.get('last_seen') or '?')[:16]))
        elif hits == 0:
            cls, txt, tip = 'v-green', T['ev_none'], T['ev_none_t'].format(ver=ev_ver, d=ev_days)
        else:
            cls, txt, tip = 'v-gray', T['ev_unk'], T['ev_unk_t']
        return f"<span class='vbadge evtag {cls}' title=\"{esc(tip)}\">{txt}</span>"
    prov = provenance or {}
    prov_sub = ''
    if prov:
        bits = [T['prov_label']]
        if prov.get('app_version') or prov.get('version'):
            bits.append(T['prov_version'] + ' ' + esc(prov.get('app_version') or prov.get('version')))
        if prov.get('fetched_at'):
            bits.append(esc(prov['fetched_at']))
        if prov.get('sha256'):
            bits.append('sha256 ' + esc(str(prov['sha256'])[:12]))
        prov_sub = ' · ' + ' · '.join(bits)
    EXPORT_TITLES = {'page': 'Pages', 'reusable': 'Reusable elements', 'workflow': 'Backend workflows',
                     'optionset': 'Option Sets', 'plugin': 'Plugins', 'style': 'Styles',
                     'colorvar': 'Color variables', 'fontvar': 'Font variables',
                     'customevent': 'Custom events (uncalled)', 'pagewf': 'Workflows on missing element',
                     'hiddenwf': 'Workflows on never-rendered element', 'apicall': 'API Connector calls (unused)',
                     'ghostref': 'Removed-plugin references', 'datatype': 'Data tables', 'field': 'Data fields',
                     'mobileview': 'Mobile views', 'mobilenav': 'Broken mobile navigations'}
    unused_pages = [p for p in pages if p['unused']]
    ref_url_pages = sorted([p for p in pages if p.get('referenced_by_url')], key=lambda x: -x['name_url_hits'])
    # attach sheet verdicts
    for p in unused_pages:
        a = page_audit.get(p['name'])
        p['verdict'] = (a['verdict'] if a and a['verdict'] else ('nostatus'))
        p['status_text'] = a['status_text'] if a else ''
    order = {'confirmed-dead': 1, 'candidate': 2, 'nostatus': 3, 'in-use': 4}
    unused_pages.sort(key=lambda p: (order.get(p['verdict'], 3), p['name'] or ''))
    n_conf = sum(1 for p in unused_pages if p['verdict'] == 'confirmed-dead')
    n_cand = sum(1 for p in unused_pages if p['verdict'] == 'candidate')
    n_inuse = sum(1 for p in unused_pages if p['verdict'] == 'in-use')
    VB = {'confirmed-dead': ('v-red', T['confirmed']), 'candidate': ('v-orange', T['candidate']),
          'in-use': ('v-green', T['inuse']), 'nostatus': ('v-gray', T['nostatus'])}
    # a checkbox <td> keyed by a stable "<category>:<id>" so marks survive report regeneration
    def chk(key, label):
        return (f"<td class='cellchk'><input type='checkbox' class='delchk' "
                f'data-key="{esc(key)}" data-label="{esc(label)}">{ev_tag(key)}</td>')
    del_h = f"<th class='cellchk'>{T['th_del']}</th>"

    # section sign-off: "this section is audited" even when some items are deliberately kept
    def sech(sid, title):
        return (f'<h2 id="{sid}" class="sec"><span>{title}</span>'
                f"<label class='secdone' title=\"{esc(T['sec_done_t'])}\">"
                f"<input type='checkbox' class='secchk' data-sec='{sid}'> {T['sec_done']}</label>"
                f"<span class='secpill'>{T['sec_done_pill']}</span></h2>")

    # every category renders a green all-clear note when the audit found nothing in it
    def all_clear(msg):
        return f"<div class='note note-green'>{msg}</div>"

    def prow(p):
        tag = f" <span class='tag'>{T['legacy']}</span>" if p['name_flag_old'] else ''
        # classification/status columns only exist when the user supplied a page-audit CSV;
        # without one the audit is .bubble-only and there is no verdict to show
        if page_audit:
            cls, lbl = VB.get(p['verdict'], ('v-gray', T['nostatus']))
            klass = f"<td><span class='vbadge {cls}'>{esc(lbl)}</span></td><td>{esc(p['status_text'])}</td>"
        else:
            klass = ''
        return (f"<tr data-v='{p['verdict']}'><td class='mono'>{esc(p['name'])}{tag}</td>{klass}"
                f"<td class='mono dim'>{esc(p['inner_id'])}</td>{chk(TK['page'](p), p['name'])}</tr>")
    class_hdr = f"<th>{T['th_class']}</th><th>{T['th_sit']}</th>" if page_audit else ''
    verdict_pills = ((
        f'<span class="pill on" data-v="all" onclick="pv(this)">{T["all"]} ({len(unused_pages)})</span>'
        f'<span class="pill" data-v="confirmed-dead" onclick="pv(this)">{T["confirmed"]} ({n_conf})</span>'
        f'<span class="pill" data-v="candidate" onclick="pv(this)">{T["candidate"]} ({n_cand})</span>'
        f'<span class="pill" data-v="in-use" onclick="pv(this)">{T["inuse"]} ({n_inuse})</span>'
    ) if page_audit else '')
    # sort key that ignores leading emoji/symbols (❌ ♻️ 🧩 …) so names sort by their first letter
    def _nk(s):
        return re.sub(r'^[^\w]+', '', (s or '')).lower()
    reuse_hard = sorted([r for r in reuse if r['unused_hard']], key=lambda r: _nk(r['name']))
    reuse_trans = sorted([r for r in reuse if r['unused_transitive']], key=lambda r: _nk(r['name']))
    reuse_dup = sorted([r for r in reuse if r.get('dup_name_conflict')], key=lambda r: _nk(r['name']))
    back_hard = sorted([r for r in backend if r['unused_hard']], key=lambda x: (x['folder'], x['wf_name'] or ''))
    back_trans = sorted([r for r in backend if r['unused_transitive']], key=lambda x: (x['folder'], x['wf_name'] or ''))
    opt_unused = [o for o in opt if o['unused']]
    opt_deleted = sum(1 for o in opt if o['deleted'])
    # styles ordered by Type then Style name (as requested)
    sty_unused = sorted([s for s in sty if s['unused']],
                        key=lambda s: ((s['stype'] or '').lower(), (s['display'] or '').lower()))

    def simple(rows, headers, cells, keyfn=None):
        h = ''.join(f'<th>{esc(x)}</th>' for x in headers) + (del_h if keyfn else '')
        b = ''
        for r in rows:
            cells_html = ''.join(f'<td>{c}</td>' for c in cells(r))
            if keyfn:
                k, lab = keyfn(r)
                cells_html += chk(k, lab)
            b += '<tr>' + cells_html + '</tr>'
        return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"

    reuse_tbl = simple(reuse_hard, [T['th_reuse'], T['th_id']],
                       lambda r: [f"<span class='mono'>{esc(r['name'])}</span>", f"<span class='mono dim'>{esc(r['inner_id'])}</span>"],
                       keyfn=lambda r: (TK['reusable'](r), r['name']))
    reuse_block = (f"<p><strong>{len(reuse_hard)}</strong> {T['reuse_body']}</p>{reuse_tbl}"
                   if reuse_hard else all_clear(T['reuse_none']))
    reuse_tbl_t = simple(reuse_trans, [T['th_reuse'], T['th_id']],
                         lambda r: [f"<span class='mono'>{esc(r['name'])}</span>", f"<span class='mono dim'>{esc(r['inner_id'])}</span>"],
                         keyfn=lambda r: (TK['reusable'](r), r['name'])) if reuse_trans else ''
    reuse_tbl_dup = simple(reuse_dup, [T['th_reuse'], T['th_id'], T['th_twin']],
                           lambda r: [f"<span class='mono'>{esc(r['name'])}</span>", f"<span class='mono dim'>{esc(r['inner_id'])}</span>",
                                      f"<span class='mono'>{esc(r['twin_used_id'])}</span> <span class='vbadge v-green'>{T['twin_in_use']}</span>"],
                           keyfn=lambda r: (TK['reusable'](r), r['name'])) if reuse_dup else ''
    back_rows = ''.join(
        f"<tr data-k='hard'><td class='mono'>{esc(r['wf_name'])}</td><td>{esc(r['folder'])}</td>"
        f"<td><span class='vbadge v-red'>{T['nav_never']}</span></td><td class='mono dim'>{esc(r['inner_id'])}</td>"
        f"{chk(TK['workflow'](r), r['wf_name'])}</tr>"
        for r in back_hard) + ''.join(
        f"<tr data-k='trans'><td class='mono'>{esc(r['wf_name'])}</td><td>{esc(r['folder'])}</td>"
        f"<td><span class='vbadge v-orange'>{T['nav_trans']}</span></td><td class='mono dim'>{esc(r['inner_id'])}</td>"
        f"{chk(TK['workflow'](r), r['wf_name'])}</tr>"
        for r in back_trans)
    back_block = ((
        f"<div class=\"filter\"><input id=\"bf\" placeholder=\"{T['filter_wf']}\" oninput=\"fb()\">"
        f"<span class=\"pill on\" data-k=\"all\" onclick=\"bk(this)\">{T['all']} ({len(back_hard) + len(back_trans)})</span>"
        f"<span class=\"pill\" data-k=\"hard\" onclick=\"bk(this)\">{T['direct']} ({len(back_hard)})</span>"
        f"<span class=\"pill\" data-k=\"trans\" onclick=\"bk(this)\">{T['trans']} ({len(back_trans)})</span></div>"
        f"<div class=\"scroll\"><table id=\"btab\"><thead><tr><th>{T['th_wf']}</th><th>{T['th_folder']}</th>"
        f"<th>{T['th_sit']}</th><th>{T['th_id']}</th>{del_h}</tr></thead><tbody>{back_rows}</tbody></table></div>")
        if (back_hard or back_trans) else all_clear(T['back_none']))
    back_wh = sorted([r for r in backend if r.get('webhook_verify')],
                     key=lambda x: (x['folder'], x['wf_name'] or ''))
    back_wh_block = ((
        f"<h3>{T['back_wh_t']} ({len(back_wh)})</h3><p class=\"dim\">{T['back_wh_b']}</p>"
        + simple(back_wh, [T['th_wf'], T['th_folder'], T['wh_exposed'], T['th_id']],
                 lambda r: [f"<span class='mono'>{esc(r['wf_name'])}</span>{ev_tag(TK['workflow'](r))}", esc(r['folder']),
                            ((f"<span class='vbadge v-green'>{T['wh_yes']}</span>" if r['expose']
                              else f"<span class='vbadge v-red'>{T['wh_no']}</span>")
                             + (f" <span class='tag'>{T['wh_payload']}</span>"
                                if r.get('webhook_initialized') else '')),
                            f"<span class='mono dim'>{esc(r['inner_id'])}</span>"]))
        if back_wh else '')
    opt_tbl = simple(opt_unused, [T['th_os'], T['th_osd']],
                     lambda r: [f"<span class='mono'>{esc(r['name'])}</span>", esc(r['display'])],
                     keyfn=lambda r: (TK['optionset'](r), r['name'])) \
              if opt_unused else all_clear(T['opt_none'])
    sty_tbl = simple(sty_unused, [T['th_styt'], T['th_sty'], T['th_styid']],
                     lambda r: [f"<span class='tag'>{esc(r['stype'])}</span>", esc(r['display']), f"<span class='mono dim'>{esc(r['id'])}</span>"],
                     keyfn=lambda r: (TK['style'](r), r['display'] or r['id'])) \
              if sty_unused else all_clear(T['sty_none'])
    # unused color / font variables (design tokens)
    vcolors = (variables or {}).get('colors', {'unused': [], 'active': 0, 'deleted': 0})
    vfonts = (variables or {}).get('fonts', {'unused': [], 'active': 0, 'deleted': 0})
    _colorlike = re.compile(r'^(#[0-9a-fA-F]{3,8}|rgba?\([\d.,%\s]+\))$')
    def var_tbl(rows, kind, extra_label):
        body = ''
        for r in rows:
            if kind == 'color':
                val = str(r.get('extra') or '')
                sw = f"<span class='swatch' style='background:{esc(val)}'></span> " if _colorlike.match(val) else ''
                extra = sw + f"<span class='mono dim'>{esc(val)}</span>"
            else:
                extra = esc(r.get('extra'))
            key = TK['colorvar' if kind == 'color' else 'fontvar'](r)
            body += (f"<tr><td>{esc(r['name'])}</td><td>{extra}</td><td class='mono dim'>{esc(r['id'])}</td>"
                     f"{chk(key, r['name'])}</tr>")
        return f"<table><thead><tr><th>{T['th_var']}</th><th>{extra_label}</th><th>{T['th_styid']}</th>{del_h}</tr></thead><tbody>{body}</tbody></table>"
    colorvar_tbl = var_tbl(vcolors['unused'], 'color', T['th_rgba']) if vcolors['unused'] else f"<div class='note note-green'>{T['var_none_c']}</div>"
    fontvar_tbl = var_tbl(vfonts['unused'], 'font', T['th_family']) if vfonts['unused'] else f"<div class='note note-green'>{T['var_none_f']}</div>"
    def plug_name_cell(r):
        if r.get('url'):
            label = esc(r['name']) if r['name'] else T['plug_open']
            tag = f" <span class='tag'>{T['plug_delisted']}</span>" if r.get('delisted') else ''
            return f"<a href='{esc(r['url'])}' target='_blank' rel='noopener'>{label} ↗</a>{tag}"
        return esc(r['name']) if r['name'] else f"<span class='dim'>{T['noname']}</span>"
    global_badge = " <span class='vbadge v-green'>" + T['plug_global'] + "</span>"
    def paid_badge(r):
        if not r.get('paid'):
            return ''
        px = ' · ' + esc(r['price']) if r.get('price') else ''
        return " <span class='vbadge v-red'>" + T['plug_paid'] + px + "</span>"
    unused_paid = [p for p in (plug_orphan + plug_cfg) if p.get('paid')]
    def author_cell(r):
        return esc(r.get('author')) if r.get('author') else "<span class='dim'>—</span>"
    def plug_tbl(rows):
        b = ''.join(f"<tr><td>{plug_name_cell(r)}{global_badge if r.get('headless') else ''}{paid_badge(r)}</td>"
                    f"<td>{author_cell(r)}</td>"
                    f"<td class='mono dim'>{esc(r['id'])}</td><td class='mono'>{esc(r['version'])}</td>"
                    f"<td class='dim'>{esc(r['reason'])}</td>{chk(TK['plugin'](r), r['name'] or r['id'])}</tr>" for r in rows)
        return f"<table><thead><tr><th>{T['th_plug']}</th><th>{T['th_author']}</th><th>ID</th><th>{T['th_ver']}</th><th>{T['th_obs']}</th>{del_h}</tr></thead><tbody>{b}</tbody></table>"
    plug_orphan_tbl = plug_tbl(plug_orphan) if plug_orphan else all_clear(T['plug_none_orphan'])
    plug_cfg_block = (f"<div class='note note-amber'>{T['plug_cfg_b']}</div>{plug_tbl(plug_cfg)}"
                      if plug_cfg else all_clear(T['plug_none_cfg']))
    # in-use plugins: reference list only (kept), name + marketplace link, no checkbox
    plug_used_rows = plug_used_list or []
    plug_used_tbl = (f"<div class='scroll'><table><thead><tr><th>{T['th_plug']}</th><th>{T['th_author']}</th><th>ID</th><th>{T['th_ver']}</th></tr></thead><tbody>"
                     + ''.join(f"<tr><td>{plug_name_cell(r)}</td><td>{author_cell(r)}</td><td class='mono dim'>{esc(r['id'])}</td>"
                               f"<td class='mono'>{esc(r['version'])}</td></tr>" for r in plug_used_rows)
                     + "</tbody></table></div>")

    # ---- data types & fields (section 7) ----
    dtT, dtF = dt['types'], dt['fields']
    def dt_type_row(r):
        api = f"<span class='vbadge v-green'>{T['api_yes']}</span>" if r['exposed'] else f"<span class='dim'>{T['api_no']}</span>"
        return (f"<tr><td class='mono'>{esc(r['display'])}</td><td class='dim'>{r['active_fields']}</td>"
                f"<td>{api}</td><td class='mono dim'>{esc(r['type_key'])}</td>"
                f"{chk(TK['datatype'](r), r['display'])}</tr>")
    dt_tables_tbl = (f"<table><thead><tr><th>{T['th_table']}</th><th>{T['th_field']}s</th><th>{T['th_api']}</th><th>{T['th_key']}</th>{del_h}</tr></thead>"
                     f"<tbody>{''.join(dt_type_row(r) for r in dtT['unused'])}</tbody></table>") if dtT['unused'] \
                    else f"<div class='note note-green'>{T['dt_none_tables']}</div>"
    def clean_ftype(v):
        return str(v or '').replace('custom.', '→ ').replace('option.', 'option:')
    def dt_field_row(r, status):
        cls, lbl = ('v-orange', T['st_unused']) if status == 'unused' else ('v-green', T['st_api'])
        api = f"<span class='vbadge v-green'>{T['api_yes']}</span>" if r['exposed'] else f"<span class='dim'>{T['api_no']}</span>"
        return (f"<tr data-f='{status}'><td class='mono'>{esc(r['type_display'])}</td>"
                f"<td>{esc(r['display'])} <span class='vbadge {cls}'>{esc(lbl)}</span></td>"
                f"<td class='mono dim'>{esc(r['field_key'])}</td><td class='mono dim'>{esc(clean_ftype(r['ftype']))}</td>"
                f"<td>{api}</td>{chk(TK['field'](r), (r['type_display'] or '') + ' > ' + (r['display'] or r['field_key']))}</tr>")
    dt_field_rows = ''.join(dt_field_row(r, 'unused') for r in dtF['candidates']) + ''.join(dt_field_row(r, 'api') for r in dtF['exposed'])
    n_fcand, n_fexp = len(dtF['candidates']), len(dtF['exposed'])
    if n_fcand + n_fexp:
        dt_fields_block = (
            (f"<div class='note note-amber'>{n_fexp} {T['dt_exposed_note']}</div>" if n_fexp else '')
            + f"<div class=\"filter\" id=\"datafilter\"><input id=\"df\" placeholder=\"{T['th_field']}…\" oninput=\"fd()\">"
            + f"<span class=\"pill on\" data-f=\"all\" onclick=\"dv(this)\">{T['all']} ({n_fcand + n_fexp})</span>"
            + f"<span class=\"pill\" data-f=\"unused\" onclick=\"dv(this)\">{T['st_unused']} ({n_fcand})</span>"
            + f"<span class=\"pill\" data-f=\"api\" onclick=\"dv(this)\">{T['st_api']} ({n_fexp})</span></div>"
            + f"<div class=\"scroll\"><table id=\"dtab\"><thead><tr><th>{T['th_table']}</th><th>{T['th_field']}</th>"
            + f"<th>{T['th_key']}</th><th>{T['th_ftype']}</th><th>{T['th_api']}</th>{del_h}</tr></thead>"
            + f"<tbody>{dt_field_rows}</tbody></table></div>")
    else:
        dt_fields_block = all_clear(T['dt_none_fields'])

    # ---- workflow audit (section 8 + backend 3b) ----
    wf = wfaudit or {'backend_ce': [], 'page_ce': [], 'orphan': [], 'hidden': []}
    def kindtag(k):
        lbl = {'page': T['wf_kp'], 'reusable': T['wf_kr'], 'mobile': T['wf_km'], 'backend': 'backend'}.get(k, T['wf_kr'])
        return f"<span class='tag'>{lbl}</span>"
    wf_bce_tbl = ''.join(f"<tr><td class='mono'>{esc(r['name'])}</td><td class='mono dim'>{esc(r['id'])}</td>"
                         f"{chk(TK['customevent'](r), r['name'])}</tr>" for r in wf['backend_ce'])
    wf_bce_tbl = (f"<table><thead><tr><th>{T['th_event']}</th><th>{T['th_id']}</th>{del_h}</tr></thead><tbody>{wf_bce_tbl}</tbody></table>"
                  if wf['backend_ce'] else f"<div class='note note-green'>{T['wf_bce_none']}</div>")
    wf_ce_tbl = ''.join(f"<tr><td class='mono'>{esc(r['name'])}</td><td>{esc(r['container'])} {kindtag(r['kind'])}</td>"
                        f"<td class='mono dim'>{esc(r['id'])}</td>{chk(TK['customevent'](r), (r['container'] or '') + ' › ' + (r['name'] or ''))}</tr>"
                        for r in wf['page_ce'])
    wf_ce_tbl = (f"<table><thead><tr><th>{T['th_event']}</th><th>{T['th_container']}</th><th>{T['th_id']}</th>{del_h}</tr></thead><tbody>{wf_ce_tbl}</tbody></table>"
                 if wf['page_ce'] else f"<div class='note note-green'>{T['wf_ce_none']}</div>")
    def orphan_where(r):
        if r.get('moved_to'):
            return (f"<span class='vbadge v-orange'>{T['wf_orphan_moved']}</span> "
                    f"<span class='mono'>{esc(r['moved_to'])}</span> {kindtag(r.get('moved_to_kind') or '')}")
        return f"<span class='vbadge v-red'>{T['wf_orphan_del']}</span>"
    wf_orphan_tbl = ''.join(f"<tr><td>{esc(r['container'])} {kindtag(r['kind'])}</td><td><span class='tag'>{esc(r['trigger'])}</span></td>"
                            f"<td class='mono dim'>{esc(r['element_id'])}</td><td>{orphan_where(r)}</td>{chk(TK['pagewf'](r), (r['container'] or '') + ' · ' + (r['trigger'] or ''))}</tr>"
                            for r in wf['orphan'])
    wf_orphan_tbl = (f"<table><thead><tr><th>{T['th_container']}</th><th>{T['th_trigger']}</th><th>{T['th_id']} (elem)</th><th>{T['th_elemwhere']}</th>{del_h}</tr></thead><tbody>{wf_orphan_tbl}</tbody></table>"
                     if wf['orphan'] else f"<div class='note note-green'>{T['wf_orphan_none']}</div>")
    # native mobile views (only rendered when the app has any)
    mob = mobile or {'total': 0, 'rows': [], 'unused': [], 'duplicate_name': [], 'roles': {}, 'broken': []}
    mob_roles_note = (('<div class="note note-blue">' + T['mob_roles'] + ' ' +
                       ', '.join(f"<span class='mono'>{esc(r['name'])}</span> "
                                 f"({esc(T['mob_initial'] if r['role'] == 'initial' else r['role'])})"
                                 for r in mob['rows'] if r.get('role')) + '</div>')
                      if any(r.get('role') for r in mob['rows']) else '')
    mob_unused_tbl = (simple(mob['unused'], [T['th_view'], T['th_wfs'], T['th_id']],
                             lambda r: [f"<span class='mono'>{esc(r['name'])}</span>"
                                        + (f" <span class='vbadge v-orange'>{T['legacy']}</span>" if r['name_flag_old'] else ''),
                                        str(r['workflows']),
                                        f"<span class='mono dim'>{esc(r['inner_id'])}</span>"],
                             keyfn=lambda r: (TK['mobileview'](r), r['name'] or r['inner_id']))
                      ) if mob['unused'] else all_clear(T['mob_none'])
    mob_broken_tbl = (simple(mob['broken'], [T['th_container'], T['th_target'], ''],
                             lambda e: [esc(e['container']) + ' ' + kindtag(e['kind']),
                                        f"<span class='mono dim'>{esc(e['target'])}</span>",
                                        (f"<span class='vbadge v-orange'>{T['mob_disabled']}</span>" if e.get('disabled') else '')],
                             keyfn=lambda e: (TK['mobilenav'](e),
                                              (e['container'] or '') + ' → ' + (e['target'] or '')))
                      ) if mob['broken'] else ''
    mob_dup = mob.get('duplicate_name') or []
    mob_dup_tbl = (simple(mob_dup, [T['th_view'], T['th_wfs'], T['th_id'], T['th_twin']],
                          lambda r: [f"<span class='mono'>{esc(r['name'])}</span>",
                                     str(r['workflows']),
                                     f"<span class='mono dim'>{esc(r['inner_id'])}</span>",
                                     f"<span class='mono'>{esc(r['twin_used_id'])}</span> <span class='vbadge v-green'>{T['twin_in_use']}</span>"],
                          keyfn=lambda r: (TK['mobileview'](r), r['name'] or r['inner_id']))
                   ) if mob_dup else ''
    mob_block = ((f"<h3>{T['mob_t']} ({len(mob['unused'])})</h3><p class=\"dim\">{T['mob_b']}</p>"
                  f"{mob_roles_note}{mob_unused_tbl}"
                  + (f"<h3>{T['mob_dup_t']} ({len(mob_dup)})</h3><div class='note note-amber'>{T['mob_dup_b']}</div>{mob_dup_tbl}"
                     if mob_dup else '')
                  + (f"<h3>{T['mob_broken_t']} ({len(mob['broken'])})</h3><p class=\"dim\">{T['mob_broken_b']}</p>{mob_broken_tbl}"
                     if mob['broken'] else ''))
                 if mob['total'] else '')
    def hidden_reason(r):
        if r.get('reason') == 'ancestor':
            return f"<span class='vbadge v-orange'>{T['wf_h_anc']}</span> <span class='mono'>{esc(r.get('blocker'))}</span>"
        return f"<span class='vbadge v-red'>{T['wf_h_self']}</span>"
    wf_hidden_tbl = ''.join(f"<tr><td>{esc(r['container'])} {kindtag(r['kind'])}</td><td><span class='tag'>{esc(r['trigger'])}</span></td>"
                            f"<td class='mono'>{esc(r['element'])}</td><td>{hidden_reason(r)}</td>"
                            f"{chk(TK['hiddenwf'](r), (r['container'] or '') + ' · ' + (r.get('element') or ''))}</tr>"
                            for r in wf['hidden'])
    wf_hidden_block = ((
        f"<div class=\"note note-amber\">{T['wf_hidden_b']}</div>"
        f"<div class=\"filter\"><input id=\"hf\" placeholder=\"{T['th_container']} / {T['th_elem']}…\" oninput=\"fh()\"></div>"
        f"<div class=\"scroll\"><table id=\"htab\"><thead><tr><th>{T['th_container']}</th><th>{T['th_trigger']}</th>"
        f"<th>{T['th_elem']}</th><th>{T['th_reason']}</th>{del_h}</tr></thead><tbody>{wf_hidden_tbl}</tbody></table></div>")
        if wf['hidden'] else all_clear(T['wf_hidden_none']))

    # ---- API Connector calls (section 9) ----
    apc = apicalls or {'total': 0, 'used': 0, 'providers': 0, 'unused': []}
    api_rows = ''.join(f"<tr><td class='mono'>{esc(r['provider'])}</td><td>{esc(r['call'])}"
                       + (f" <span class='tag'>{T['api_self']} {esc(r['self_wf'])}</span>" if r.get('self_wf') else '')
                       + f"</td><td><span class='tag'>{esc(r['method'])}</span></td><td class='mono dim'>{esc(r['ref'])}</td>"
                       f"{chk(TK['apicall'](r), (r['provider'] or '') + ' › ' + (r['call'] or ''))}</tr>"
                       for r in apc['unused'])
    api_tbl = (f"<div class=\"filter\"><input id=\"af\" placeholder=\"{T['filter_api']}\" oninput=\"fa()\"></div>"
               f"<div class='scroll'><table id='atab'><thead><tr><th>{T['th_provider']}</th><th>{T['th_endpoint']}</th>"
               f"<th>{T['th_method']}</th><th>Ref</th>{del_h}</tr></thead><tbody>{api_rows}</tbody></table></div>") \
              if apc['unused'] else all_clear(T['api_none'])

    # ---- ghost plugin references (section 10) ----
    gh = ghosts or {'refs': [], 'plugin_count': 0, 'plugins': []}
    wherelab = {'element': T['gw_element'], 'action': T['gw_action'], 'trigger': T['gw_trigger']}
    def ghost_name_cell(r):
        nm = esc(r['plugin_name']) if r['plugin_name'] else f"<span class='mono dim'>{esc(r['plugin_id'])}</span>"
        if r.get('url'):
            return f"<a href='{esc(r['url'])}' target='_blank' rel='noopener'>{nm} ↗</a>"
        return nm
    ghost_rows = ''.join(f"<tr><td>{ghost_name_cell(r)}</td><td class='mono'>{esc(r['container'])}</td>"
                         f"<td><span class='tag'>{esc(wherelab.get(r['where'], r['where']))}</span></td>"
                         f"<td class='mono'>{esc(r['location'])}</td>"
                         f"{chk(TK['ghostref'](r), (r['plugin_name'] or r['plugin_id']) + ' — ' + (r['container'] or ''))}</tr>"
                         for r in gh['refs'])
    ghost_block = ((
        f"<div class=\"note note-amber\">{T['ghost_body']}</div>"
        f"<p><strong>{len(gh['refs'])}</strong> " + 'referências · ' + str(gh['plugin_count']) + ' plugins: '
        + ', '.join((esc(p['name'] or p['id'][:14]) + ' (' + str(p['count']) + ')') for p in gh['plugins']) + '</p>'
        f"<div class=\"filter\"><input id=\"gf\" placeholder=\"{T['filter_ghost']}\" oninput=\"fg2()\"></div>"
        f"<div class='scroll'><table id='gtab'><thead><tr><th>{T['th_plug']}</th><th>{T['th_container']}</th>"
        f"<th>{T['th_where']}</th><th>{T['th_loc']}</th>{del_h}</tr></thead><tbody>{ghost_rows}</tbody></table></div>")
        if gh['refs'] else all_clear(T['ghost_none']))

    caveat = T['caveat_pages'].format(L=dyn['ListGoToPage'], D=dyn['dynamic_page_name'])
    refurl_block = ''
    if ref_url_pages:
        body = ''.join(
            f"<tr><td class='mono'>{esc(p['name'])}{ev_tag(TK['page'](p))}</td><td class='dim'>{esc(p['name_url_hits'])}</td>"
            f"<td class='mono dim' style='font-size:11.5px'>…{esc(p['name_url_snippet'])}…</td></tr>"
            for p in ref_url_pages)
        refurl_block = (f"<div class='note note-green'><strong>{len(ref_url_pages)} · {T['refurl_t']}.</strong> {T['refurl_b']}</div>"
                        f"<table><thead><tr><th>{T['th_page']}</th><th>{T['th_hits']}</th><th>{T['th_ev']}</th></tr></thead><tbody>{body}</tbody></table>")
    if unused_pages:
        pages_block = (
            f'<div class="note note-amber">{caveat}</div>{refurl_block}'
            + (('<div class=cards>'
                f'<div class="card k-red"><div class="big">{n_conf}</div><div class="lab">' + T['confirmed'] + '</div></div>'
                f'<div class="card k-orange"><div class="big">{n_cand}</div><div class="lab">' + T['candidate'] + '</div></div>'
                f'<div class="card k-green"><div class="big">{n_inuse}</div><div class="lab">' + T['inuse'] + '</div></div>'
                '</div>') if page_audit else '')
            + f'<div class="filter"><input id="pf" placeholder="{T["filter_page"]}" oninput="fp()">{verdict_pills}</div>'
            + f'<div class="scroll"><table id="ptab"><thead><tr><th>{T["th_page"]}</th>{class_hdr}<th>{T["th_id"]}</th>{del_h}</tr></thead>'
            + f'<tbody>{"".join(prow(p) for p in unused_pages)}</tbody></table></div>')
    else:
        pages_block = all_clear(T['pages_none']) + refurl_block
    total_pages = len(pages)
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(app_name)} — {T['title']}</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--ink:#1a1f2b;--dim:#6b7280;--line:#e4e7ec;--accent:#2f6bd8;--red:#c0392b;--redbg:#fdecea;--orange:#b9770e;--orangebg:#fdf3e2;--green:#1e7d46;--greenbg:#e8f6ee;--graybg:#eef0f3;--shadow:0 1px 3px rgba(16,24,40,.06)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1319;--card:#161b23;--ink:#e6e9ef;--dim:#9aa4b2;--line:#262d38;--accent:#6ea0f0;--red:#f0796b;--redbg:#2a1714;--orange:#e0a94a;--orangebg:#2a2011;--green:#63c98d;--greenbg:#12271b;--graybg:#1c222b;--shadow:0 1px 3px rgba(0,0,0,.4)}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1160px;margin:0 auto;padding:32px 22px 80px}}h1{{font-size:25px;margin:0 0 4px;letter-spacing:-.02em}}.sub{{color:var(--dim);font-size:13.5px}}
h2{{font-size:20px;margin:38px 0 10px;scroll-margin-top:118px}}h3{{font-size:15px;margin:22px 0 8px}}.q{{color:var(--accent);font-weight:600}}
.stickyhead{{position:sticky;top:0;z-index:10;background:var(--bg);margin:6px -22px 12px;padding:9px 22px;border-bottom:1px solid var(--line);box-shadow:0 4px 10px -8px rgba(16,24,40,.35)}}
.stickyhead .toc{{margin:0 0 8px}}.stickyhead .tracker{{margin:0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px;margin:20px 0 6px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}}
.card .big{{font-size:29px;font-weight:700;letter-spacing:-.02em;line-height:1.1}}.card .lab{{font-size:12.5px;color:var(--dim);margin-top:3px}}.card .of{{font-size:12px;color:var(--dim)}}
.k-red .big{{color:var(--red)}}.k-orange .big{{color:var(--orange)}}.k-green .big{{color:var(--green)}}
.note{{border:1px solid var(--line);border-left-width:4px;border-radius:8px;padding:12px 15px;margin:14px 0;background:var(--card);font-size:14px}}
.note-blue{{border-left-color:var(--accent)}}.note-amber{{border-left-color:var(--orange);background:var(--orangebg)}}.note-green{{border-left-color:var(--green);background:var(--greenbg)}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:7px 11px;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:var(--graybg);font-weight:600;font-size:12.5px;position:sticky;top:0}}tr:last-child td{{border-bottom:none}}
.scroll{{max-height:520px;overflow:auto;border-radius:10px;border:1px solid var(--line)}}.scroll table{{border:none;border-radius:0}}
.mono{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px}}.dim{{color:var(--dim)}}
.tag{{display:inline-block;background:var(--graybg);border:1px solid var(--line);border-radius:5px;padding:0 6px;font-size:11px;color:var(--dim)}}
.vbadge{{display:inline-block;border-radius:20px;padding:1px 9px;font-size:11.5px;font-weight:600;white-space:nowrap}}
.v-red{{background:var(--redbg);color:var(--red)}}.v-orange{{background:var(--orangebg);color:var(--orange)}}.v-green{{background:var(--greenbg);color:var(--green)}}.v-gray{{background:var(--graybg);color:var(--dim)}}
.filter{{margin:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}}.filter input{{padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font-size:13px;min-width:220px}}
.pill{{cursor:pointer;border:1px solid var(--line);background:var(--card);border-radius:20px;padding:3px 11px;font-size:12px;color:var(--dim)}}.pill.on{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.toc{{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}}.toc a{{font-size:13px;text-decoration:none;color:var(--accent);border:1px solid var(--line);border-radius:20px;padding:4px 12px;background:var(--card)}}
code{{background:var(--graybg);padding:1px 5px;border-radius:4px;font-size:12.5px}}footer{{margin-top:50px;padding-top:18px;border-top:1px solid var(--line);color:var(--dim);font-size:12.5px}}
td a{{color:var(--accent);text-decoration:none}}td a:hover{{text-decoration:underline}}
.swatch{{display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid var(--line);vertical-align:-2px}}h4{{color:var(--ink)}}
.cellchk{{text-align:center;width:1%;white-space:nowrap}}.evtag{{display:table;margin-top:3px;font-size:10.5px;padding:0 7px}}.cellchk .evtag{{margin-left:auto;margin-right:auto}}.delchk{{width:16px;height:16px;cursor:pointer;accent-color:var(--accent)}}
tr.done td:not(.cellchk){{opacity:.4;text-decoration:line-through}}
h2.sec{{display:flex;align-items:center;flex-wrap:wrap;gap:10px}}
.secdone{{font-size:12.5px;font-weight:500;color:var(--dim);cursor:pointer;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:20px;padding:3px 10px;background:var(--card);white-space:nowrap}}
.secdone input{{width:15px;height:15px;accent-color:var(--green);cursor:pointer;margin:0}}
.secpill{{display:none;font-size:12px;font-weight:600;color:var(--green);background:var(--greenbg);border-radius:20px;padding:3px 10px;white-space:nowrap}}
h2.secok .secpill{{display:inline-block}}h2.secok .secdone{{border-color:var(--green);color:var(--green)}}
tr.kept td:not(.cellchk){{font-style:italic;color:var(--dim)}}.kepttag{{display:block;font-size:10.5px;font-weight:600;color:var(--orange);margin-top:2px}}
#syncstate{{font-size:12px;color:var(--dim)}}#syncstate.ok{{color:var(--green)}}#syncstate.err{{color:var(--red)}}
.tracker{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;margin:16px 0;box-shadow:var(--shadow)}}
.tracker .prog{{font-weight:700;font-variant-numeric:tabular-nums}}.tracker .sp{{flex:1}}
.tracker button,.tracker .btn{{cursor:pointer;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:8px;padding:5px 11px;font-size:12.5px}}
.tracker button:hover,.tracker .btn:hover{{border-color:var(--accent);color:var(--accent)}}
.bar{{flex:0 0 150px;height:7px;background:var(--graybg);border-radius:4px;overflow:hidden}}.bar>i{{display:block;height:100%;background:var(--green);width:0;transition:width .2s}}
@media print{{.stickyhead,.filter{{display:none}}.scroll{{max-height:none;overflow:visible}}h2{{scroll-margin-top:0}}}}
</style></head><body><div class="wrap">
<h1>{esc(app_name)} — {T['title']}</h1>
<div class="sub">{T['sub_src']} · <span class="mono">{esc(app_name)}.bubble</span> · {T['generated']} {esc(date_str)}{prov_sub}</div>
<div class="stickyhead">
<div class="toc"><a href="#p">1 · {T['nv_p']}</a><a href="#r">2 · {T['nv_r']}</a><a href="#b">3 · {T['nv_b']}</a><a href="#o">4 · {T['nv_o']}</a><a href="#pl">5 · {T['nv_pl']}</a><a href="#s">6 · {T['nv_s']}</a><a href="#d">7 · {T['nv_d']}</a><a href="#w">8 · {T['nv_w']}</a><a href="#ap">9 · {T['nv_ap']}</a><a href="#g">10 · {T['nv_g']}</a><a href="#m">{T['nv_m']}</a></div>
<div class="tracker">
<span class="prog"><span id="delcount">0 / 0</span></span><span class="bar"><i id="delbar"></i></span>
<span class="dim">{T['trk_hint']}</span>
<span class="prog"><span id="seccount">0 / 0</span></span><span class="dim">{T['trk_sections']}</span>
<span id="syncstate"></span><span class="sp"></span>
<button onclick="exportProgress('md')" title="{T['trk_export_md_t']}">{T['trk_export_md']}</button>
<button onclick="exportProgress('json')">{T['trk_export_json']}</button>
<label class="btn">{T['trk_import']}<input type="file" accept=".md,.markdown,.json,text/markdown,application/json" style="display:none" onchange="importProgress(this.files[0]);this.value=''"></label>
<button onclick="clearProgress()">{T['trk_clear']}</button>
</div>
</div>
<div class="note note-blue"><strong>{T['how_title']}.</strong> {T['how_body']}</div>{integ_block}{ev_block}
<div class="cards">
<div class="card k-orange"><div class="big">{len(unused_pages)}</div><div class="lab">{T['c_pages']}</div><div class="of">{T['of']} {total_pages}</div></div>
{('<div class="card k-orange"><div class="big">' + str(len(mob['unused'])) + '</div><div class="lab">' + T['c_mob'] + '</div><div class="of">' + T['of'] + ' ' + str(mob['total']) + ' · ' + T['mob_card_of'] + (' · ' + str(len(mob['broken'])) + ' nav ✗' if mob['broken'] else '') + '</div></div>') if mob['total'] else ''}
<div class="card k-red"><div class="big">{len(reuse_hard)+len(reuse_trans)}</div><div class="lab">{T['c_reuse']}</div><div class="of">{T['of']} {len(reuse)}</div></div>
<div class="card k-red"><div class="big">{len(back_hard)+len(back_trans)}</div><div class="lab">{T['c_back']}</div><div class="of">{T['of']} {len(backend)} · {exposed} {T['exposed']}</div></div>
<div class="card k-orange"><div class="big">{len(opt_unused)}</div><div class="lab">{T['c_opt']}</div><div class="of">{T['of']} {len(opt)}</div></div>
<div class="card k-red"><div class="big">{len(plug_orphan)}</div><div class="lab">{T['c_plug']}</div><div class="of">{T['of']} {plug_total} · +{len(plug_cfg)}{(' · '+str(len(unused_paid))+' 💲') if unused_paid else ''}</div></div>
<div class="card k-orange"><div class="big">{len(sty_unused)}</div><div class="lab">{T['c_sty']}</div><div class="of">{T['of']} {len(sty)}</div></div>
<div class="card k-orange"><div class="big">{n_fcand}</div><div class="lab">{T['c_dtF']}</div><div class="of">+{n_fexp} {T['st_api']}</div></div>
<div class="card k-red"><div class="big">{len(dtT['unused'])}</div><div class="lab">{T['c_dtT']}</div><div class="of">{T['of']} {dtT['active']} · {dtT['exposed']} API</div></div>
<div class="card k-orange"><div class="big">{len(wf['backend_ce']) + len(wf['page_ce'])}</div><div class="lab">{T['c_wf']}</div><div class="of">{len(wf['backend_ce'])} backend + {len(wf['page_ce'])} páginas</div></div>
<div class="card k-red"><div class="big">{len(wf['orphan']) + len(wf['hidden'])}</div><div class="lab">{T['c_wf_orphan']}</div><div class="of">{len(wf['orphan'])} inexistente + {len(wf['hidden'])} nunca renderizado</div></div>
<div class="card k-orange"><div class="big">{len(apc['unused'])}</div><div class="lab">{T['c_api']}</div><div class="of">{T['of']} {apc['total']} · {apc['providers']} APIs</div></div>
<div class="card k-red"><div class="big">{len(gh['refs'])}</div><div class="lab">{T['c_ghost']}</div><div class="of">{gh['plugin_count']} plugins removidos</div></div>
</div>

{sech('p', T['s_pages'])}<p class="q">{T['q_pages']}</p>
{pages_block}
{mob_block}

{sech('r', T['s_reuse'])}<p class="q">{T['q_reuse']}</p>
{reuse_block}
{('<h3>+ '+str(len(reuse_trans))+' transitive</h3>'+reuse_tbl_t) if reuse_trans else ''}
{('<h3>'+T['dup_reuse_t']+' ('+str(len(reuse_dup))+')</h3><div class="note note-amber">'+T['dup_reuse_b']+'</div>'+reuse_tbl_dup) if reuse_dup else ''}

{sech('b', T['s_back'])}<p class="q">{T['q_back']}</p>
<p>{T['back_body']}</p>
<div class="cards"><div class="card k-red"><div class="big">{len(back_hard)}</div><div class="lab">{T['direct']}</div></div>
<div class="card k-orange"><div class="big">{len(back_trans)}</div><div class="lab">{T['trans']}</div></div>
<div class="card k-green"><div class="big">{exposed}</div><div class="lab">{T['exposed']}</div></div></div>
{back_block}
{back_wh_block}
<h3>3b · {T['wf_bce_t']} ({len(wf['backend_ce'])})</h3><p class="dim">{T['wf_bce_b']}</p>{wf_bce_tbl}

{sech('o', T['s_opt'])}<p class="q">{T['q_opt']}</p>
<p>{len(opt_unused)} / {len(opt)} ({opt_deleted} {T['already_deleted']}). {T['opt_body']}</p>{opt_tbl}

{sech('pl', T['s_plug'])}<p class="q">{T['q_plug']}</p>
{('<div class="note note-red"><strong>💲 '+str(len(unused_paid))+' '+T['plug_paid_alert']+'</strong><ul>'+''.join('<li><strong>'+esc(p['name'] or p['id'])+'</strong>'+((' — '+esc(p['price'])) if p.get('price') else '')+((' ('+esc(p['pricing_model'])+')') if p.get('pricing_model') else '')+'</li>' for p in unused_paid)+'</ul></div>') if unused_paid else ''}
<p><strong>{plug_used}</strong>/{plug_total} {T['plug_used']}</p>
<h3>{T['plug_orphan_t']} ({len(plug_orphan)})</h3><p class="dim">{T['plug_orphan_b']}</p>{plug_orphan_tbl}
<h3>{T['plug_cfg_t']} ({len(plug_cfg)})</h3>{plug_cfg_block}
<h3>{T['plug_used_t']} ({len(plug_used_rows)})</h3><p class="dim">{T['plug_used_b']}</p>{plug_used_tbl}

{sech('s', T['s_sty'])}<p class="q">{T['q_sty']}</p>
<p>{len(sty_unused)} / {len(sty)}. {T['sty_body']}</p>{sty_tbl}
<h3>{T['s_var']}</h3><p class="dim">{T['var_body']}</p>
<h4 style="margin:16px 0 6px;font-size:14px">{T['var_colors_h']} ({len(vcolors['unused'])}) · <span class="dim" style="font-weight:400">{T['var_stat'] % (vcolors['active'], vcolors['deleted'])}</span></h4>{colorvar_tbl}
<h4 style="margin:16px 0 6px;font-size:14px">{T['var_fonts_h']} ({len(vfonts['unused'])}) · <span class="dim" style="font-weight:400">{T['var_stat'] % (vfonts['active'], vfonts['deleted'])}</span></h4>{fontvar_tbl}

{sech('d', T['s_dt'])}<p class="q">{T['q_dt']}</p>
<div class="note note-blue">{dtF['deleted']} {T['dt_deleted_note']} {dtT['deleted']} {T['dt_tables_deleted']} {dtT['exposed']} {T['dt_exposed_tables']}</div>
<h3>{T['dt_tables_t']} ({len(dtT['unused'])})</h3><p class="dim">{T['dt_tables_b']}</p>{dt_tables_tbl}
<h3>{T['dt_fields_t']} ({n_fcand})</h3><p>{T['dt_fields_b']}</p>
{dt_fields_block}

{sech('w', T['s_wf'])}<p class="q">{T['q_wf']}</p>
<h3>{T['wf_ce_t']} ({len(wf['page_ce'])})</h3><p class="dim">{T['wf_ce_b']}</p>
<div class="scroll">{wf_ce_tbl}</div>
<h3>{T['wf_orphan_t']} ({len(wf['orphan'])})</h3><p class="dim">{T['wf_orphan_b']}</p>
<div class="scroll">{wf_orphan_tbl}</div>
<h3>{T['wf_hidden_t']} ({len(wf['hidden'])})</h3>
{wf_hidden_block}

{sech('ap', T['s_api'])}<p class="q">{T['q_api']}</p>
<p><strong>{len(apc['unused'])}</strong> / {apc['total']}. {T['api_body']}</p>
{api_tbl}

{sech('g', T['s_ghost'])}<p class="q">{T['q_ghost']}</p>
{ghost_block}

<h2 id="m">{T['method']}</h2>
<div class="note note-blue"><p>Pages: id interno referenced by <code>ChangePage</code>/<code>Link.page</code>/<code>MobileNavigate</code> or anywhere in content.
Reusables: definition <code>id</code> used as a <code>CustomElement.custom_id</code>. Backend: <code>APIEvent</code> exposed or targeted by <code>ScheduleAPIEvent(OnList)</code>.
Option sets: token <code>option.&lt;name&gt;</code>. Plugins: element/action <code>type</code> prefix <code>&lt;id&gt;-</code> or config keys. Styles: <code>"style":"&lt;id&gt;"</code>.
Data fields: field key referenced beyond its declaration (in expressions/workflows/searches) or named in a JS/HTML script; Data types: <code>custom.&lt;type&gt;</code> referenced, any field used, or exposed via <code>exposed_api</code>.
Limits: direct-URL / email / iframe / dynamic navigation are not statically detectable (hence page confidence levels); orphan plugin names are not stored in the export; field keys shared across tables are treated conservatively (marked used if referenced on any table); Data-API-exposed fields/tables may have external consumers not visible in the export.</p></div>
<footer>{esc(app_name)} · {total_pages} pages · {len(reuse)} reusables · {len(backend)} API workflows · {len(opt)} option sets · {plug_total} plugins · {len(sty)} styles · {dtT['active']} data tables · {dtF['active']} fields</footer>
</div><script>
function fp(){{var q=pf.value.toLowerCase();document.querySelectorAll('#ptab tbody tr').forEach(function(t){{t.style.display=(t.dataset._h!=='1'&&t.cells[0].innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
function pv(e){{document.querySelectorAll('[data-v]').forEach(p=>p.classList.remove('on'));e.classList.add('on');var v=e.dataset.v;document.querySelectorAll('#ptab tbody tr').forEach(t=>t.dataset._h=(v=='all'||t.dataset.v==v)?'0':'1');fp();}}
function fb(){{var q=bf.value.toLowerCase();document.querySelectorAll('#btab tbody tr').forEach(function(t){{t.style.display=(t.dataset._h!=='1'&&t.cells[0].innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
function bk(e){{document.querySelectorAll('[data-k]').forEach(p=>p.classList.remove('on'));e.classList.add('on');var k=e.dataset.k;document.querySelectorAll('#btab tbody tr').forEach(t=>t.dataset._h=(k=='all'||t.dataset.k==k)?'0':'1');fb();}}
function fd(){{var q=df.value.toLowerCase();document.querySelectorAll('#dtab tbody tr').forEach(function(t){{t.style.display=(t.dataset._h!=='1'&&t.innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
function dv(e){{document.querySelectorAll('#datafilter .pill[data-f]').forEach(p=>p.classList.remove('on'));e.classList.add('on');var v=e.dataset.f;document.querySelectorAll('#dtab tbody tr').forEach(t=>t.dataset._h=(v=='all'||t.dataset.f==v)?'0':'1');fd();}}
function fh(){{var q=hf.value.toLowerCase();document.querySelectorAll('#htab tbody tr').forEach(function(t){{t.style.display=(t.innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
function fa(){{var q=af.value.toLowerCase();document.querySelectorAll('#atab tbody tr').forEach(function(t){{t.style.display=(t.innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
function fg2(){{var q=gf.value.toLowerCase();document.querySelectorAll('#gtab tbody tr').forEach(function(t){{t.style.display=(t.innerText.toLowerCase().indexOf(q)>=0)?'':'none';}});}}
/* ---- deletion tracker: localStorage live store + .md/.json export/import ---- */
const APP_ID={json.dumps(app_name)};
const INITIAL={json.dumps(initial_deleted)};
const TITLES={json.dumps(EXPORT_TITLES)};
const NS='bubble_audit::'+APP_ID;
const SECTIONS=['p','r','b','o','pl','s','d','w','ap','g'];
/* When the report is served by the UnBubble console, audit/bubble_cleanup_progress__<app>.json is the source of truth. */
const SYNC_URL=(location.protocol==='http:'||location.protocol==='https:')?'/api/projects/'+encodeURIComponent(APP_ID)+'/audit-progress':null;
function _load(){{let s=null;try{{s=JSON.parse(localStorage.getItem(NS));}}catch(e){{}}if(!s){{s={{}};INITIAL.forEach(k=>s[k]=1);_save(s);}}return s;}}
function _save(s){{try{{localStorage.setItem(NS,JSON.stringify(s));}}catch(e){{}}}}
let DEL=_load();
function secTitle(k){{var h=document.getElementById(k);return h?h.firstChild.textContent.trim():k;}}
function secItems(k){{var h=document.getElementById(k),out=[];if(!h)return out;var n=h.nextElementSibling;while(n&&n.tagName!=='H2'){{n.querySelectorAll('.delchk').forEach(c=>out.push(c));n=n.nextElementSibling;}}return out;}}
function _count(){{var all=document.querySelectorAll('.delchk'),n=0;all.forEach(c=>{{if(DEL[c.dataset.key])n++;}});var t=all.length;document.getElementById('delcount').textContent=n+' / '+t;document.getElementById('delbar').style.width=(t?100*n/t:0)+'%';var sd=SECTIONS.filter(k=>DEL['section:'+k]).length;document.getElementById('seccount').textContent=sd+' / '+SECTIONS.length;}}
function _applySections(){{SECTIONS.forEach(function(k){{var h=document.getElementById(k);if(!h)return;var on=!!DEL['section:'+k];h.classList.toggle('secok',on);var cb=h.querySelector('.secchk');if(cb)cb.checked=on;secItems(k).forEach(function(c){{var tr=c.closest('tr'),kept=on&&!DEL[c.dataset.key];tr.classList.toggle('kept',kept);var tag=c.parentNode.querySelector('.kepttag');if(kept&&!tag){{tag=document.createElement('span');tag.className='kepttag';tag.textContent={json.dumps(T['kept_tag'])};c.parentNode.appendChild(tag);}}else if(!kept&&tag)tag.remove();}});}});}}
function _apply(){{document.querySelectorAll('.delchk').forEach(function(c){{var on=!!DEL[c.dataset.key];c.checked=on;c.closest('tr').classList.toggle('done',on);}});_applySections();_count();}}
document.addEventListener('change',function(e){{var el=e.target;if(!el.classList)return;
 if(el.classList.contains('delchk')){{var k=el.dataset.key;if(el.checked)DEL[k]=1;else delete DEL[k];el.closest('tr').classList.toggle('done',el.checked);_save(DEL);_applySections();_count();_sync();return;}}
 if(el.classList.contains('secchk')){{var sk='section:'+el.dataset.sec;if(el.checked)DEL[sk]=1;else delete DEL[sk];_save(DEL);_applySections();_count();_sync();}}
}});
/* payload v2: deleted keys + section sign-offs + the items kept on purpose (unchecked inside a signed-off section) */
function _payload(){{var deleted=Object.keys(DEL).filter(k=>DEL[k]&&k.indexOf('section:')!==0),done=SECTIONS.filter(k=>DEL['section:'+k]),sections={{}},kept=[];
 SECTIONS.forEach(function(k){{var items=secItems(k),d=items.filter(c=>DEL[c.dataset.key]).length,on=!!DEL['section:'+k];sections[k]={{title:secTitle(k),done:on,items:items.length,deleted:d,kept:on?items.length-d:0}};if(on)items.forEach(function(c){{if(!DEL[c.dataset.key])kept.push({{key:c.dataset.key,label:c.dataset.label||'',section:k}});}});}});
 return {{app:APP_ID,version:2,updated:new Date().toISOString().slice(0,10),deleted:deleted,sections_done:done,sections:sections,kept:kept}};}}
function _dl(text,name,type){{var b=new Blob([text],{{type:type}});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}}
function exportProgress(fmt){{
 if(fmt==='json'){{_dl(JSON.stringify(_payload(),null,1),'bubble_cleanup_progress__'+APP_ID+'.json','application/json');return;}}
 var NL=String.fromCharCode(10),md='# Bubble cleanup progress — '+APP_ID+NL+NL+'> '+{json.dumps(T['md_hint'])}+NL+'> Updated: '+new Date().toISOString().slice(0,10)+NL;
 SECTIONS.forEach(function(k){{var items=secItems(k),on=!!DEL['section:'+k];if(!items.length&&!on)return;md+=NL+'## '+secTitle(k)+NL+'- ['+(on?'x':' ')+'] `section:'+k+'` — '+{json.dumps(T['sec_done'])}+NL;items.forEach(function(c){{var d=!!DEL[c.dataset.key];md+='- ['+(d?'x':' ')+'] `'+c.dataset.key+'` — '+(c.dataset.label||'')+((on&&!d)?' · '+{json.dumps(T['md_kept'])}:'')+NL;}});}});
 _dl(md,'bubble_cleanup_progress__'+APP_ID+'.md','text/markdown');
}}
function _fromJson(j){{var s={{}};var arr=Array.isArray(j)?j:(j.deleted||[]);arr.forEach(k=>s[k]=1);(Array.isArray(j)?[]:(j.sections_done||[])).forEach(k=>s['section:'+k]=1);return s;}}
function importProgress(file){{if(!file)return;var r=new FileReader();r.onload=function(){{var t=r.result;
 if(/\\.json$/i.test(file.name)){{try{{DEL=_fromJson(JSON.parse(t));}}catch(e){{alert('Invalid JSON');return;}}}}
 else{{var on=/- \\[[xX]\\]\\s*`([^`]+)`/g,off=/- \\[ \\]\\s*`([^`]+)`/g,m;while(m=on.exec(t))DEL[m[1]]=1;while(m=off.exec(t))delete DEL[m[1]];}}
 _save(DEL);_apply();_sync();}};r.readAsText(file);}}
function clearProgress(){{if(!confirm({json.dumps(T['clear_confirm'])}))return;DEL={{}};_save(DEL);_apply();_sync();}}
/* console sync (optional): PUT the payload to the UnBubble console, which writes audit/bubble_cleanup_progress__<app>.json */
var _syncT=null,_syncEl=document.getElementById('syncstate');
function _syncState(cls,txt){{if(!_syncEl)return;_syncEl.className=cls;_syncEl.textContent=txt;}}
function _sync(){{if(!SYNC_URL||!_syncEl.dataset.on)return;clearTimeout(_syncT);_syncState('',{json.dumps(T['sync_saving'])});_syncT=setTimeout(function(){{fetch(SYNC_URL,{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(_payload())}}).then(function(r){{_syncState(r.ok?'ok':'err',r.ok?{json.dumps(T['sync_saved'])}:{json.dumps(T['sync_err'])});}}).catch(function(){{_syncState('err',{json.dumps(T['sync_err'])});}});}},400);}}
_apply();
if(SYNC_URL){{fetch(SYNC_URL).then(function(r){{return r.ok?r.json():null;}}).then(function(j){{if(!j||typeof j!=='object'||!('exists' in j))return;_syncEl.dataset.on='1';if(j.exists){{DEL=_fromJson(j);_save(DEL);_apply();_syncState('ok',{json.dumps(T['sync_saved'])});}}else{{_syncState('ok',{json.dumps(T['sync_ready'])});}}}}).catch(function(){{}});}}
</script></body></html>"""

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description='Static unused-entities audit for a Bubble .bubble export.')
    ap.add_argument('input', help='path to the .bubble export file')
    ap.add_argument('--out', help='output HTML report path (default: <input>_unused_report.html)')
    ap.add_argument('--json', help='also write raw results as JSON to this path')
    ap.add_argument('--pages-csv', help='optional page-audit CSV to cross-reference (join on page name)')
    ap.add_argument('--pages-csv-name-col', help='column in the CSV holding the page name (default: first column)')
    ap.add_argument('--pages-csv-status-col', action='append',
                    help='column(s) whose text carries usage status (repeatable; default: auto-detect)')
    ap.add_argument('--lang', choices=['pt', 'en'], default='pt', help='report language (default: pt)')
    ap.add_argument('--date', default='', help='date string to stamp on the report (e.g. 2026-07-09)')
    ap.add_argument('--state', action='append',
                    help='progress file to pre-mark already-deleted items: a .md/.json exported from the report, '
                         'or the connected-mode cleanup journal (repeatable; keys are merged)')
    ap.add_argument('--evidence', action='append',
                    help='runtime-evidence JSON from the connected mode (unbubble:connect runtime_evidence.py): '
                         'log badges on the candidates it evaluated (repeatable)')
    ap.add_argument('--plugin-names', help='optional JSON {pluginId: name} to override/extend the bundled marketplace name registry')
    ap.add_argument('--plugin-pricing', help='optional JSON {pluginId: {status,model,price}} to override/extend the bundled pricing registry')
    args = ap.parse_args()

    log('loading', args.input, '...')
    with open(args.input, encoding='utf-8') as f:
        data = json.load(f)
    app_name = data.get('_id') or os.path.splitext(os.path.basename(args.input))[0]

    content_raw, quoted = build_index(data)
    domains = app_domains(data)
    url_corpus = build_url_corpus(data)
    log('url/script corpus:', len(url_corpus), 'chars; app domains:', domains)
    pages, dyn = analyze_pages(data, quoted, url_corpus, domains)
    reuse = analyze_reusables(data, quoted)
    apicalls = analyze_api_calls(data)
    backend, exposed = analyze_backend(data, quoted, selfapi_used=set(apicalls['self_used']))
    opt = analyze_optionsets(data, content_raw)
    sty = analyze_styles(data, content_raw)
    variables = analyze_variables(data, content_raw)
    plug_registry = load_plugin_registry(args.plugin_names)
    plug_pricing = load_plugin_pricing(args.plugin_pricing)
    plug_orphan, plug_cfg, plug_used_list, plug_total = analyze_plugins(data, content_raw, plug_registry, plug_pricing)
    script_corpus = build_script_corpus(data)
    dt = analyze_datatypes(data, quoted, content_raw, script_corpus)
    wfaudit = analyze_workflows(data)
    ghosts = analyze_ghost_plugins(data, plug_registry)
    mobile = analyze_mobile_views(data)
    integrity = analyze_export_integrity(data)
    provenance = load_provenance(args.input)
    evidence = load_evidence(args.evidence, app_name) if args.evidence else None

    page_audit = {}
    if args.pages_csv:
        page_audit = load_page_audit(args.pages_csv, args.pages_csv_name_col, args.pages_csv_status_col)
        log('page audit rows:', len(page_audit))

    initial_deleted = load_state(args.state)
    if args.state:
        log('pre-marked from state (%d file%s):' % (len(args.state), '' if len(args.state) == 1 else 's'),
            len(initial_deleted))
    html_str = render_html(app_name, args.date, args.lang, pages, dyn, page_audit, reuse,
                           backend, exposed, opt, sty, plug_orphan, plug_cfg, len(plug_used_list), plug_total,
                           dt, plug_used_list=plug_used_list, variables=variables, wfaudit=wfaudit,
                           apicalls=apicalls, ghosts=ghosts, initial_deleted=initial_deleted, mobile=mobile,
                           integrity=integrity, provenance=provenance, evidence=evidence)
    out = args.out or (os.path.splitext(args.input)[0] + '_unused_report.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html_str)

    up = [p for p in pages if p['unused']]
    ref_url = [p for p in pages if p.get('referenced_by_url')]
    # every finding carries its deletion-tracker `key` (same string as the report checkbox), so the
    # connected-mode cleanup plan and the console never re-derive it
    summary = {
        'app': app_name,
        'summary_version': 2,
        'export_integrity': integrity,
        'provenance': provenance,
        'pages': {'total': len(pages), 'no_internal_nav': len(up) + len(ref_url),
                  'unused': [{'name': p['name'], 'inner_id': p['inner_id'], 'key': TK['page'](p)} for p in up],
                  'referenced_by_url': [{'name': p['name'], 'inner_id': p['inner_id'], 'key': TK['page'](p),
                                         'hits': p['name_url_hits'], 'evidence': p['name_url_snippet']} for p in ref_url],
                  'dynamic_nav': dyn},
        'reusables': {'total': len(reuse),
                      'unused_hard': [{'name': r['name'], 'inner_id': r['inner_id'], 'key': TK['reusable'](r)} for r in reuse if r['unused_hard']],
                      'unused_transitive': [{'name': r['name'], 'inner_id': r['inner_id'], 'key': TK['reusable'](r)} for r in reuse if r['unused_transitive']],
                      'duplicate_name': [{'name': r['name'], 'inner_id': r['inner_id'], 'key': TK['reusable'](r), 'used_twin': r['twin_used_id']} for r in reuse if r.get('dup_name_conflict')]},
        'backend': {'total_apievents': len(backend), 'exposed': exposed,
                    'unused_hard': [{'wf_name': r['wf_name'], 'inner_id': r['inner_id'], 'folder': r['folder'], 'key': TK['workflow'](r)} for r in backend if r['unused_hard']],
                    'unused_transitive': [{'wf_name': r['wf_name'], 'inner_id': r['inner_id'], 'folder': r['folder'], 'key': TK['workflow'](r)} for r in backend if r['unused_transitive']],
                    'webhook_verify': [{'wf_name': r['wf_name'], 'inner_id': r['inner_id'], 'folder': r['folder'], 'key': TK['workflow'](r),
                                        'expose': r['expose'], 'initialized': r.get('webhook_initialized', False)}
                                       for r in backend if r.get('webhook_verify')]},
        'option_sets': {'total': len(opt), 'unused': [{'name': o['name'], 'display': o['display'], 'key': TK['optionset'](o)} for o in opt if o['unused']]},
        'plugins': {'total': plug_total, 'used_with_ui': len(plug_used_list), 'orphaned': keyed(plug_orphan, 'plugin'),
                    'configured_no_ui': keyed(plug_cfg, 'plugin'), 'in_use': plug_used_list,
                    'unused_paid': [{'id': p['id'], 'name': p['name'], 'price': p['price'], 'key': TK['plugin'](p),
                                     'model': p['pricing_model']} for p in (plug_orphan + plug_cfg) if p.get('paid')]},
        'styles': {'total': len(sty), 'unused': [{'id': s['id'], 'display': s['display'], 'type': s['stype'], 'key': TK['style'](s)} for s in sty if s['unused']]},
        'variables': {'colors': {'active': variables['colors']['active'], 'deleted': variables['colors']['deleted'],
                                 'unused': keyed(variables['colors']['unused'], 'colorvar')},
                      'fonts': {'active': variables['fonts']['active'], 'deleted': variables['fonts']['deleted'],
                                'unused': keyed(variables['fonts']['unused'], 'fontvar')}},
        'data_tables': {'active': dt['types']['active'], 'exposed_data_api': dt['types']['exposed'],
                        'deleted': dt['types']['deleted'], 'unused': keyed(dt['types']['unused'], 'datatype')},
        'data_fields': {'active': dt['fields']['active'], 'deleted': dt['fields']['deleted'],
                        'exposed_data_api_only': len(dt['fields']['exposed']),
                        'referenced_in_script': len(dt['fields']['script']),
                        'unused': keyed(dt['fields']['candidates'], 'field'),
                        'exposed_verify': keyed(dt['fields']['exposed'], 'field')},
        'mobile_views': {'total': mobile['total'],
                         'unused': [{'name': r['name'], 'inner_id': r['inner_id'], 'key': TK['mobileview'](r),
                                     'workflows': r['workflows'], 'elements': r['elements']}
                                    for r in mobile['unused']],
                         'duplicate_name': [{'name': r['name'], 'inner_id': r['inner_id'], 'key': TK['mobileview'](r),
                                             'workflows': r['workflows'], 'used_twin': r['twin_used_id']}
                                            for r in mobile['duplicate_name']],
                         'system_roles': [{'inner_id': r['inner_id'], 'name': r['name'], 'role': r['role']}
                                          for r in mobile['rows'] if r.get('role')],
                         'broken_navigations': keyed(mobile['broken'], 'mobilenav')},
        # backend and page custom events share the `customevent:` prefix; `scope` tells them apart
        'workflow_audit': {'backend_custom_events_uncalled': keyed(wfaudit['backend_ce'], 'customevent', scope='backend'),
                           'page_custom_events_uncalled': keyed(wfaudit['page_ce'], 'customevent', scope='page'),
                           'triggers_on_missing_element': keyed(wfaudit['orphan'], 'pagewf'),
                           'triggers_on_hidden_element_leads': keyed(wfaudit['hidden'], 'hiddenwf')},
        'api_connector': {'total_calls': apicalls['total'], 'used': apicalls['used'],
                          'providers': apicalls['providers'], 'unused': keyed(apicalls['unused'], 'apicall')},
        'removed_plugin_refs': {'total': len(ghosts['refs']), 'plugin_count': ghosts['plugin_count'],
                                'plugins': ghosts['plugins'], 'refs': keyed(ghosts['refs'], 'ghostref')},
    }
    if evidence:
        # per tracker key: how often the candidate shows up in the server logs (counts only)
        summary['runtime_evidence'] = evidence
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=1, ensure_ascii=False)

    print('== Bubble unused-entities audit: %s ==' % app_name)
    if integrity['incomplete']:
        print('  !! EXPORT INCOMPLETE: %d of %d reusable definitions have no payload in the export (%d hollow) -'
              ' references made inside them are invisible; findings may be false positives. Re-export first.'
              % (integrity['missing_payload'] + integrity['hollow_payload'], integrity['indexed_definitions'],
                 integrity['hollow_payload']))
    if provenance:
        print('  Provenance      : downloaded via connected mode · version %s · %s'
              % (provenance.get('app_version') or provenance.get('version') or '?', provenance.get('fetched_at') or '?'))
    if evidence:
        print('  Runtime evidence: %d seen in the %s logs (review before deleting), %d not seen, %d unknown - %s days'
              % (evidence['counts']['seen'], evidence.get('app_version') or 'live', evidence['counts']['not_seen'],
                 evidence['counts']['unknown'], (evidence.get('window') or {}).get('days') or '?'))
    print('  Pages           : %d / %d no id-navigation; of those %d linked by URL/name (kept) -> %d deletable candidates'
          % (len(up) + len(ref_url), len(pages), len(ref_url), len(up)))
    if mobile['total']:
        print('  Mobile views    : %d never navigated (+%d duplicate-name to verify) / %d (%d system-role) | broken navigations: %d'
              % (len(mobile['unused']), len(mobile['duplicate_name']), mobile['total'],
                 sum(1 for r in mobile['rows'] if r.get('role')), len(mobile['broken'])))
    print('  Reusables       : %d never placed (+%d transitively dead, %d duplicate-name to verify) / %d'
          % (len(summary['reusables']['unused_hard']), len(summary['reusables']['unused_transitive']),
             len(summary['reusables']['duplicate_name']), len(reuse)))
    print('  Backend WFs     : %d unreachable (+%d transitive, %d webhook-shaped to verify) / %d APIEvents (%d exposed endpoints)'
          % (len(summary['backend']['unused_hard']), len(summary['backend']['unused_transitive']),
             len(summary['backend']['webhook_verify']), len(backend), exposed))
    print('  Option sets     : %d unused / %d' % (len(summary['option_sets']['unused']), len(opt)))
    _paid = [p for p in (plug_orphan + plug_cfg) if p.get('paid')]
    print('  Plugins         : %d orphaned (+%d no-UI-but-active) / %d | UNUSED PAID (alert): %d'
          % (len(plug_orphan), len(plug_cfg), plug_total, len(_paid)))
    print('  Styles          : %d unused / %d' % (len(summary['styles']['unused']), len(sty)))
    print('  Color/font vars : %d color + %d font unused (of %d/%d active)'
          % (len(variables['colors']['unused']), len(variables['fonts']['unused']),
             variables['colors']['active'], variables['fonts']['active']))
    print('  Custom events   : %d backend + %d page/reusable never called'
          % (len(wfaudit['backend_ce']), len(wfaudit['page_ce'])))
    _hs = sum(1 for r in wfaudit['hidden'] if r.get('reason') == 'self')
    _moved = sum(1 for r in wfaudit['orphan'] if r.get('moved_to'))
    print('  Dead triggers   : %d on missing element (%d moved to a reusable, %d deleted) + %d never-rendered (%d element itself, %d hidden ancestor group)'
          % (len(wfaudit['orphan']), _moved, len(wfaudit['orphan']) - _moved,
             len(wfaudit['hidden']), _hs, len(wfaudit['hidden']) - _hs))
    print('  API Connector   : %d unused calls / %d declared (%d providers)'
          % (len(apicalls['unused']), apicalls['total'], apicalls['providers']))
    print('  Removed plugins : %d ghost references from %d uninstalled plugins still in the app'
          % (len(ghosts['refs']), ghosts['plugin_count']))
    print('  Data tables     : %d unused / %d active (%d exposed in Data API, %d already deleted)'
          % (len(dt['types']['unused']), dt['types']['active'], dt['types']['exposed'], dt['types']['deleted']))
    print('  Data fields     : %d unused (+%d exposed-Data-API-only, %d already deleted)'
          % (len(dt['fields']['candidates']), len(dt['fields']['exposed']), dt['fields']['deleted']))
    if page_audit:
        conf = sum(1 for p in up if page_audit.get(p['name'], {}).get('verdict') == 'confirmed-dead')
        cand = sum(1 for p in up if page_audit.get(p['name'], {}).get('verdict') == 'candidate')
        print('  Page cross-ref  : %d confirmed-dead + %d candidates corroborated by the sheet' % (conf, cand))
    print('  HTML report ->', out)
    if args.json:
        print('  JSON  ->', args.json)

if __name__ == '__main__':
    main()
