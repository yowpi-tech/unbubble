#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bubble_inventory.py — extract a structured AS-IS inventory from a Bubble.io export (.bubble).

UnBubble pipeline, step 2 (clone). This script does the DETERMINISTIC extraction; the
interpretation (documentation prose, business rules, PRD) is done by the model reading
the JSON files this script emits.

Outputs into --outdir (default: <input>_inventory/):
  summary.json            app meta + counts (read this first)
  database.json           data types: fields, types, list-ness, references, privacy rules,
                          Data API exposure; plus a relationship edge list
  option_sets.json        every option set with its options (display + db_value)
  api_connector.json      external API providers & calls: method, URL (masked), params
                          (KEY NAMES ONLY), publish_as, used/unused
  plugins.json            installed plugins: version, usage count, config key NAMES
                          (client_safe + secure — values NEVER copied)
  data_api.json           Data/Workflow API global switches + exposed tables
  backend_workflows.json  every backend workflow: kind, endpoint name, expose, method,
                          auth flags, parameters, action chain (types), schedule graph
  pages.json              per page: title, content type, element census, workflows with
                          editor-name labels + action types, reusables/plugins/API calls
                          used, navigation targets
  reusables.json          same census for reusable elements + where each is placed

SECURITY: settings.secure VALUES are never read into the output — only key names.
API-call parameter VALUES are omitted (names + private flag only); URLs and body
templates are masked for secret-looking query params. APIEvent raw_data (may contain
real PII samples) is omitted. The output is safe to hand to a documentation model,
but still lists ENDPOINT names/paths — treat the inventory directory as internal.
Credential VALUES are preserved separately by the companion bubble_secrets.py
(-> <workdir>/secrets/.env) so they are not lost — run BOTH scripts (see SKILL.md).

Dependency-free (Python 3.8+ stdlib). Usage:
  python3 bubble_inventory.py path/to/export.bubble [--outdir DIR] [--plugin-names FILE]
"""
import argparse, json, os, re, sys
from collections import Counter

def log(*a):
    print(*a, file=sys.stderr)

SECRETISH = re.compile(r'(key|token|secret|password|pwd|signature|bearer|auth|credential)', re.I)

# ---------------------------------------------------------------- shared helpers
# (duplicated from unbubble:audit/scripts/bubble_audit.py so each skill is standalone)
_INSTANCE_LETTER = re.compile(r'\s+([A-Z]{1,6})$')
_BBCODE = re.compile(r'\[/?[a-zA-Z][^\]]*\]')

def build_def_names(data):
    out = {}
    for dv in (data.get('element_definitions') or {}).values():
        if isinstance(dv, dict) and dv.get('id'):
            out[dv['id']] = dv.get('name')
    return out

def _element_content(el):
    props = el.get('properties') if isinstance(el.get('properties'), dict) else {}
    for key in ('text', 'caption', 'placeholder'):
        v = props.get(key)
        s = None
        if isinstance(v, str):
            s = v
        elif isinstance(v, dict) and isinstance(v.get('entries'), dict):
            z = v['entries'].get('0')
            s = z if isinstance(z, str) else None
        if s and s.strip():
            s = ' '.join(_BBCODE.sub('', s).split())
            if s:
                return s
    return None

def _type_word(el):
    dn = el.get('default_name')
    if isinstance(dn, str) and dn:
        return _INSTANCE_LETTER.sub('', dn).strip() or dn
    t = el.get('type')
    return t if isinstance(t, str) else ''

def editor_name(el, fallback=None, def_names=None):
    """Element name as shown in the Bubble editor tree (see audit reference-model.md)."""
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

# ---------------------------------------------------------------- masking
def mask_url(u):
    """Mask query-param values whose name looks secret-ish."""
    if not isinstance(u, str) or '?' not in u:
        return u
    base, q = u.split('?', 1)
    parts = []
    for kv in q.split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            parts.append(k + '=' + ('***' if SECRETISH.search(k) else v))
        else:
            parts.append(kv)
    return base + '?' + '&'.join(parts)

def mask_body(b, limit=200):
    """Mask secret-ish k=v pairs in a body template and truncate."""
    if not isinstance(b, str):
        return None
    b = re.sub(r'("?)([A-Za-z0-9_\-]*(?:' + SECRETISH.pattern + r')[A-Za-z0-9_\-]*)("?\s*[:=]\s*"?)([^",&\s]+)',
               r'\1\2\4***', b, flags=re.I)
    return b[:limit] + ('…' if len(b) > limit else '')

# ---------------------------------------------------------------- extraction
CONTENT_KEYS = ['pages', 'element_definitions', 'api', 'option_sets', 'styles',
                'settings', 'user_types', 'mobile_views']

def build_content_raw(data):
    content = {k: data.get(k) for k in CONTENT_KEYS}
    return json.dumps(content, separators=(',', ':'))

def inv_database(data):
    types, edges = [], []
    for tk, tv in (data.get('user_types') or {}).items():
        if not isinstance(tv, dict):
            continue
        display = tv.get('display')
        if not display:            # primitive built-ins (text, number, …) have no display
            continue
        fields = []
        for fk, fv in (tv.get('fields') or {}).items():
            if not isinstance(fv, dict):
                continue
            vt = str(fv.get('value') or '')
            is_list = vt.startswith('list.')
            base = vt[5:] if is_list else vt
            ref = None
            if base.startswith('custom.'):
                ref = {'kind': 'table', 'target': base[7:]}
                if not fv.get('deleted'):
                    edges.append({'from': tk, 'field': fv.get('display'), 'to': base[7:],
                                  'is_list': is_list})
            elif base.startswith('option.'):
                ref = {'kind': 'option_set', 'target': base[7:]}
            elif base == 'user':
                ref = {'kind': 'table', 'target': 'user'}
                if not fv.get('deleted'):
                    edges.append({'from': tk, 'field': fv.get('display'), 'to': 'user',
                                  'is_list': is_list})
            fields.append({'key': fk, 'display': fv.get('display'), 'type': base,
                           'is_list': is_list, 'ref': ref,
                           'deleted': bool(fv.get('deleted'))})
        privacy = {}
        pr = tv.get('privacy_role')
        if isinstance(pr, dict):
            for role, rv in pr.items():
                if isinstance(rv, dict):
                    perms = rv.get('permissions')
                    privacy[rv.get('display') or role] = perms if isinstance(perms, dict) else {}
        types.append({'key': tk, 'display': display,
                      'exposed_api': bool(tv.get('exposed_api')),
                      'deleted': bool(tv.get('deleted')),
                      'privacy_rules': privacy,
                      'field_count_active': sum(1 for f in fields if not f['deleted']),
                      'fields': sorted(fields, key=lambda f: (f['display'] or '').lower())})
    types.sort(key=lambda t: (t['display'] or '').lower())
    return {'types': types, 'relationships': edges}

def inv_option_sets(data):
    out = []
    for k, v in (data.get('option_sets') or {}).items():
        if not isinstance(v, dict):
            continue
        options = []
        vals = v.get('values')
        if isinstance(vals, dict):
            for ov in vals.values():
                if isinstance(ov, dict):
                    options.append({'display': ov.get('display'), 'db_value': ov.get('db_value'),
                                    'sort': ov.get('sort_factor')})
        options.sort(key=lambda o: (o.get('sort') is None, o.get('sort'), str(o.get('display'))))
        out.append({'key': k, 'display': v.get('display'), 'deleted': bool(v.get('deleted')),
                    'options': options})
    out.sort(key=lambda s: (s['display'] or s['key'] or '').lower())
    return out

def inv_api_connector(data, content_raw):
    ac = ((data.get('settings') or {}).get('client_safe') or {}).get('apiconnector2') or {}
    providers = []
    for aid, prov in ac.items():
        if not isinstance(prov, dict):
            continue
        auth = prov.get('auth')
        auth_info = None
        if isinstance(auth, dict):
            auth_info = {'type': auth.get('type') or auth.get('auth_type'),
                         'config_keys': sorted(k for k in auth.keys()
                                               if k not in ('type', 'auth_type'))}
        calls = []
        for cid, call in (prov.get('calls') or {}).items():
            if not isinstance(call, dict):
                continue
            # a call is invoked as a workflow ACTION (hyphen form) or as a DATA SOURCE
            # (dot form, `"provider":"apiconnector2.<aid>.<cid>"`) — same rule as bubble_audit.py
            ref_action = '"apiconnector2-%s.%s"' % (aid, cid)
            ref_data = '"apiconnector2.%s.%s"' % (aid, cid)
            params = []
            for pgroup in ('url_params', 'body_params', 'headers', 'params'):
                pg = call.get(pgroup)
                if isinstance(pg, dict):
                    for pv in pg.values():
                        if isinstance(pv, dict) and pv.get('key'):
                            params.append({'key': pv.get('key'), 'in': pgroup,
                                           'private': bool(pv.get('private'))})
            calls.append({'id': cid, 'name': call.get('name'),
                          'method': (call.get('method') or '').upper() or None,
                          'url': mask_url(call.get('url')),
                          'publish_as': call.get('publish_as'),   # action | data
                          'body_template': mask_body(call.get('body')),
                          'params': params,
                          'initialized': bool(call.get('initialized')),
                          'used': ref_action in content_raw or ref_data in content_raw})
        calls.sort(key=lambda c: (c['name'] or '').lower())
        providers.append({'id': aid, 'name': prov.get('human'), 'auth': auth_info,
                          'call_count': len(calls),
                          'calls_used': sum(1 for c in calls if c['used']),
                          'calls': calls})
    providers.sort(key=lambda p: (p['name'] or '').lower())
    return providers

def inv_plugins(data, content_raw, names, authors=None):
    authors = authors or {}
    cs = (data.get('settings') or {}).get('client_safe') or {}
    secure_keys = sorted(((data.get('settings') or {}).get('secure') or {}).keys())
    installed = cs.get('plugins') or {}
    out = []
    for pid, ver in installed.items():
        usage = content_raw.count('"type":"%s-' % pid)
        cfg = sorted(k for k in cs.keys() if k.startswith(pid + '_'))
        sec = [k for k in secure_keys if k.startswith(pid + '_') or k.startswith(pid)]
        out.append({'id': pid, 'version': ver,
                    'name': names.get(pid),
                    'author': authors.get(pid),
                    'marketplace_url': 'https://bubble.io/plugin/' + pid if re.match(r'^\d{13}x', pid) else None,
                    'usage_type_refs': usage,
                    'config_key_names': cfg,          # names only — values live in the app
                    'secure_key_names': sec})         # names only — NEVER values
    out.sort(key=lambda p: ((p['name'] or p['id']).lower()))
    return out

def inv_data_api(data, db):
    cs = (data.get('settings') or {}).get('client_safe') or {}
    exposed = [{'key': t['key'], 'display': t['display']}
               for t in db['types'] if t['exposed_api'] and not t['deleted']]
    return {'data_api_enabled (exposes_get_api)': bool(cs.get('exposes_get_api')),
            'workflow_api_enabled (exposes_wf_api)': bool(cs.get('exposes_wf_api')),
            'swagger_hidden (hide_swagger_api)': bool(cs.get('hide_swagger_api')),
            'exposed_types': exposed,
            'note': ('Data API root: https://<domain>/api/1.1/obj/<type> ; Workflow API root: '
                     'https://<domain>/api/1.1/wf/<endpoint>. Per-type allowed operations are '
                     'governed by privacy rules (see database.json privacy_rules) and API tokens. '
                     'The tokens themselves live in settings.secure.api_tokens and are preserved '
                     'by bubble_secrets.py into <workdir>/secrets/.env (BUBBLE_API_TOKEN_*).')}

def inv_backend(data):
    folders = ((data.get('settings') or {}).get('client_safe') or {}).get('api_wf_folder_list') or {}
    fname = {k: (v.get('name') if isinstance(v, dict) else str(v)) for k, v in folders.items()}
    items, by_id = [], {}
    for k, v in (data.get('api') or {}).items():
        if not isinstance(v, dict) or not v.get('type'):
            continue
        p = v.get('properties') if isinstance(v.get('properties'), dict) else {}
        params = []
        pr = p.get('parameters')
        if isinstance(pr, dict):
            for pv in pr.values():
                if isinstance(pv, dict) and pv.get('key'):
                    params.append({'key': pv.get('key'),
                                   'type': pv.get('value') if isinstance(pv.get('value'), str) else None})
        actions, schedules = [], []
        ac = v.get('actions')
        if isinstance(ac, dict):
            for order, a in sorted(ac.items(), key=lambda kv: str(kv[0])):
                if isinstance(a, dict):
                    ap = a.get('properties') if isinstance(a.get('properties'), dict) else {}
                    actions.append({'order': order, 'type': a.get('type'),
                                    'has_condition': 'condition' in ap})
                    tgt = ap.get('api_event')
                    if isinstance(tgt, str):
                        schedules.append(tgt)
        item = {'key': k, 'id': v.get('id'), 'kind': v.get('type'),
                'name': p.get('wf_name') or p.get('event_name'),
                'folder': fname.get(p.get('wf_folder'), p.get('wf_folder')),
                # Bubble only serializes expose:false when the checkbox is UNchecked —
                # an APIEvent with no expose key IS exposed (same rule as bubble_audit.py)
                'expose': (v.get('type') == 'APIEvent' and 'expose' not in p) or bool(p.get('expose')),
                'method': p.get('trigger_option'),
                'auth_not_required': bool(p.get('auth_unecessary')),
                'ignore_privacy_rules': bool(p.get('ignore_privacy_rules')),
                'has_condition': 'condition' in p,
                'return_200_if_not_run': bool(p.get('return_200_if_not_run')),
                'parameters': params, 'actions': actions,
                'schedules_workflows': schedules, 'scheduled_by': []}
        items.append(item)
        if item['id']:
            by_id[item['id']] = item
    # reverse schedule graph — page/reusable-side ScheduleAPIEvent targets count too
    def collect(o, src):
        if isinstance(o, dict):
            if o.get('type') in ('ScheduleAPIEvent', 'ScheduleAPIEventOnList'):
                tgt = (o.get('properties') or {}).get('api_event')
                if isinstance(tgt, str) and tgt in by_id and src not in by_id[tgt]['scheduled_by']:
                    by_id[tgt]['scheduled_by'].append(src)
            for vv in o.values():
                collect(vv, src)
        elif isinstance(o, list):
            for vv in o:
                collect(vv, src)
    for it in items:
        collect({'a': [a for a in (data.get('api') or {}).values()
                       if isinstance(a, dict) and a.get('id') == it['id']]}, 'backend:' + (it['name'] or it['key']))
    for coll, kind in (('pages', 'page'), ('element_definitions', 'reusable')):
        for cv in (data.get(coll) or {}).values():
            if isinstance(cv, dict):
                collect(cv.get('workflows'), '%s:%s' % (kind, cv.get('name')))
    items.sort(key=lambda i: ((i['kind'] or ''), (i['name'] or '').lower()))
    return items

PLUGIN_TYPE = re.compile(r'^(\d{13}x\d+)-')

def census_container(v, def_names, page_names_by_id, plugin_names):
    """Element census + workflow summaries for one page/reusable."""
    el_types, plugin_ids, api_calls, reusables, nav = Counter(), Counter(), set(), Counter(), set()
    id2el = {}
    def walk_el(e):
        if isinstance(e, dict):
            for el in e.values():
                if isinstance(el, dict):
                    t = el.get('type')
                    if isinstance(t, str):
                        el_types[t] += 1
                        m = PLUGIN_TYPE.match(t)
                        if m:
                            plugin_ids[m.group(1)] += 1
                        if t.startswith('apiconnector2-'):
                            api_calls.add(t[len('apiconnector2-'):])
                        if t == 'CustomElement':
                            nm = editor_name(el, None, def_names)
                            if nm:
                                reusables[_INSTANCE_LETTER.sub('', nm).strip()] += 1
                    if el.get('id'):
                        id2el[el['id']] = el
                    walk_el(el.get('elements'))
    walk_el(v.get('elements'))
    wfs = []
    def deep_scan(o):
        if isinstance(o, dict):
            t = o.get('type')
            if isinstance(t, str):
                if t.startswith('apiconnector2-'):
                    api_calls.add(t[len('apiconnector2-'):])
                m = PLUGIN_TYPE.match(t)
                if m:
                    plugin_ids[m.group(1)] += 1
                if t in ('ChangePage',):
                    tgt = (o.get('properties') or {}).get('element_id')
                    if tgt in page_names_by_id:
                        nav.add(page_names_by_id[tgt])
                if t == 'Link':
                    tgt = (o.get('properties') or {}).get('page')
                    if tgt in page_names_by_id:
                        nav.add(page_names_by_id[tgt])
            for vv in o.values():
                deep_scan(vv)
        elif isinstance(o, list):
            for vv in o:
                deep_scan(vv)
    deep_scan(v)
    for wf in (v.get('workflows') or {}).values() if isinstance(v.get('workflows'), dict) else []:
        if not isinstance(wf, dict):
            continue
        p = wf.get('properties') if isinstance(wf.get('properties'), dict) else {}
        eid = p.get('element_id')
        label = p.get('event_name') or p.get('wf_name')
        if not label and eid:
            label = editor_name(id2el.get(eid), eid, def_names)
        atypes = []
        ac = wf.get('actions')
        if isinstance(ac, dict):
            for order, a in sorted(ac.items(), key=lambda kv: str(kv[0])):
                if isinstance(a, dict) and a.get('type'):
                    atypes.append(a['type'])
        wfs.append({'trigger': wf.get('type'), 'on': label,
                    'has_condition': 'condition' in p, 'action_types': atypes})
    return {'element_count': sum(el_types.values()),
            'elements_by_type': dict(el_types.most_common(15)),
            'workflow_count': len(wfs), 'workflows': wfs,
            'reusables_used': dict(reusables.most_common()),
            'plugin_ids_used': {plugin_names.get(pid) or pid: c
                                for pid, c in plugin_ids.most_common()},
            'api_calls_used': sorted(api_calls),
            'navigates_to': sorted(nav)}

def inv_pages(data, def_names, plugin_names):
    page_names_by_id = {v.get('id'): v.get('name') for v in (data.get('pages') or {}).values()
                        if isinstance(v, dict) and v.get('id')}
    pages = []
    for k, v in (data.get('pages') or {}).items():
        if not isinstance(v, dict):
            continue
        p = v.get('properties') if isinstance(v.get('properties'), dict) else {}
        title = p.get('title')
        if isinstance(title, dict) and isinstance(title.get('entries'), dict):
            title = title['entries'].get('0')
        rec = {'key': k, 'id': v.get('id'), 'name': v.get('name'),
               'title': title if isinstance(title, str) else None,
               'content_type': p.get('page_item_type')}
        rec.update(census_container(v, def_names, page_names_by_id, plugin_names))
        pages.append(rec)
    pages.sort(key=lambda x: (x['name'] or '').lower())
    return pages

def inv_reusables(data, def_names, plugin_names, content_raw):
    page_names_by_id = {v.get('id'): v.get('name') for v in (data.get('pages') or {}).values()
                        if isinstance(v, dict) and v.get('id')}
    out = []
    for k, v in (data.get('element_definitions') or {}).items():
        if not isinstance(v, dict):
            continue
        rec = {'key': k, 'id': v.get('id'), 'name': v.get('name'),
               'placed_instances': content_raw.count('"custom_id":"%s"' % v.get('id')) if v.get('id') else 0}
        rec.update(census_container(v, def_names, page_names_by_id, plugin_names))
        out.append(rec)
    out.sort(key=lambda x: (x['name'] or '').lower())
    return out

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='Extract an as-is inventory from a .bubble export')
    ap.add_argument('input')
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--plugin-names', default=None,
                    help='JSON {pluginId: name}; defaults to the audit skill\'s plugin_names.json')
    args = ap.parse_args()

    outdir = args.outdir or (os.path.splitext(args.input)[0] + '_inventory')
    os.makedirs(outdir, exist_ok=True)

    log('Loading %s …' % args.input)
    with open(args.input, 'r') as f:
        data = json.load(f)

    names_path = args.plugin_names or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..', 'audit', 'references', 'plugin_names.json')
    names, authors = {}, {}
    if os.path.exists(names_path):
        try:
            for k, v in json.load(open(names_path)).items():
                if k.startswith('_') or not v:
                    continue
                # registry value forms: "Name" | null | {"name":..., "author":..., "delisted":...}
                if isinstance(v, dict):
                    if v.get('name'):
                        names[k] = v['name']
                    if v.get('author'):
                        authors[k] = v['author']
                else:
                    names[k] = v
        except Exception as e:
            log('  (plugin names not loaded: %s)' % e)

    content_raw = build_content_raw(data)
    def_names = build_def_names(data)

    db = inv_database(data)
    osets = inv_option_sets(data)
    ac = inv_api_connector(data, content_raw)
    plugins = inv_plugins(data, content_raw, names, authors)
    dapi = inv_data_api(data, db)
    backend = inv_backend(data)
    pages = inv_pages(data, def_names, names)
    reus = inv_reusables(data, def_names, names, content_raw)

    cs = (data.get('settings') or {}).get('client_safe') or {}
    summary = {
        'app_domain': cs.get('app_topdomain'),
        'generated_by': 'unbubble:clone bubble_inventory.py',
        'counts': {
            'data_types_active': sum(1 for t in db['types'] if not t['deleted']),
            'data_types_deleted': sum(1 for t in db['types'] if t['deleted']),
            'fields_active': sum(t['field_count_active'] for t in db['types'] if not t['deleted']),
            'option_sets': sum(1 for s in osets if not s['deleted']),
            'api_providers': len(ac),
            'api_calls': sum(p['call_count'] for p in ac),
            'api_calls_used': sum(p['calls_used'] for p in ac),
            'plugins_installed': len(plugins),
            'backend_workflows': sum(1 for b in backend if b['kind'] == 'APIEvent'),
            'backend_exposed_endpoints': sum(1 for b in backend if b['expose']),
            'backend_custom_events': sum(1 for b in backend if b['kind'] == 'CustomEvent'),
            'db_trigger_events': sum(1 for b in backend if b['kind'] == 'DatabaseTriggerEvent'),
            'recurring_events': sum(1 for b in backend if b['kind'] == 'RecurringEvent'),
            'pages': len(pages),
            'reusables': len(reus),
            'data_api_exposed_types': len(dapi['exposed_types']),
        },
        'security_flags': {
            'endpoints_without_auth': [b['name'] for b in backend
                                       if b['expose'] and b['auth_not_required']],
            'endpoints_ignoring_privacy_rules': [b['name'] for b in backend
                                                 if b['expose'] and b['ignore_privacy_rules']],
        },
    }

    files = {'summary.json': summary, 'database.json': db, 'option_sets.json': osets,
             'api_connector.json': ac, 'plugins.json': plugins, 'data_api.json': dapi,
             'backend_workflows.json': backend, 'pages.json': pages, 'reusables.json': reus}
    for fn, obj in files.items():
        path = os.path.join(outdir, fn)
        with open(path, 'w') as f:
            json.dump(obj, f, indent=1, ensure_ascii=False)
        log('  wrote %-24s %6.1f KB' % (fn, os.path.getsize(path) / 1024))

    c = summary['counts']
    log('\nInventory summary:')
    log('  Data types  : %d active (%d fields), %d deleted; %d exposed in Data API'
        % (c['data_types_active'], c['fields_active'], c['data_types_deleted'],
           c['data_api_exposed_types']))
    log('  Option sets : %d' % c['option_sets'])
    log('  External API: %d providers, %d calls (%d in use)'
        % (c['api_providers'], c['api_calls'], c['api_calls_used']))
    log('  Plugins     : %d installed' % c['plugins_installed'])
    log('  Backend WFs : %d (%d exposed endpoints, %d custom events, %d DB triggers, %d recurring)'
        % (c['backend_workflows'], c['backend_exposed_endpoints'], c['backend_custom_events'],
           c['db_trigger_events'], c['recurring_events']))
    log('  Pages       : %d   Reusables: %d' % (c['pages'], c['reusables']))
    if summary['security_flags']['endpoints_without_auth']:
        log('  ⚠ endpoints WITHOUT auth: %d' % len(summary['security_flags']['endpoints_without_auth']))
    n_secure = len((data.get('settings') or {}).get('secure') or {})
    if n_secure:
        log('  ⚠ settings.secure holds %d entries (API keys/credentials) NOT extracted here —'
            % n_secure)
        log('    run bubble_secrets.py to preserve them into <workdir>/secrets/.env (see SKILL.md).')
    log('\nInventory -> %s' % outdir)

if __name__ == '__main__':
    main()
