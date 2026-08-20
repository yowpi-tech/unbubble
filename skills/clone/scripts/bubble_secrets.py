#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bubble_secrets.py — preserve every API key / credential / private config value from a
Bubble.io export (.bubble) into a .env + documentation, so the rebuild agent can
configure the new system later. UnBubble pipeline, step 2 (clone) — companion to
bubble_inventory.py (which deliberately redacts these values).

Sources extracted:
  settings.secure               ALL of it: named service keys (sendgrid/stripe/mailchimp/
                                slack/docusign/google_geocode/dbconnector...), the API
                                Connector secure mirror (private_key, basic-auth, appsecret,
                                private shared/per-call params — each entry carries its own
                                param `key` name), flat plugin secure keys (<pluginid>_*),
                                Bubble Data/Workflow API tokens (api_tokens), OAuth provider
                                apps, Zapier webhook URLs, mobile app signing credentials
                                (Apple APNs / Android keystore), and Bubble-internal values.
  settings.client_safe          plugin CONFIG values (<pluginid>_* string keys — publishable
                                keys, app ids). Client-visible in Bubble, still needed to
                                reconfigure the rebuilt system.

Outputs into --outdir (default: <input>_secrets/):
  .env           every extracted value, one var per key, commented with its export path.
                 chmod 600. LIVE CREDENTIALS — never commit, never paste, never cat.
  .env.example   same vars + comments, values blanked. Safe to commit in the rebuild repo.
  ENV-KEYS.md    the documentation: var ↔ export path ↔ service/context ↔ live/test ↔
                 in-use flag (NO values). This is the file the documentation model reads.
  .gitignore     ignores .env so the folder can live inside a git-tracked workdir.

SECURITY CONTRACT: values are written ONLY into .env. Nothing on stdout/stderr and nothing
in ENV-KEYS.md / .env.example ever contains a value (lengths and key names only). A leaf
accounting is printed: every scalar under settings.secure is exported, empty, or a listed
non-credential toggle — if the numbers don't add up the script says so loudly.

Dependency-free (Python 3.8+ stdlib). Usage:
  python3 bubble_secrets.py path/to/export.bubble [--outdir DIR] [--plugin-names FILE]
"""
import argparse, json, os, re, sys
from collections import OrderedDict

def log(*a):
    print(*a, file=sys.stderr)

PLUGIN_ID = re.compile(r'^(\d{13}x\d+)_(.+)$')
BARE_OK = re.compile(r'^[A-Za-z0-9_@./:+=,-]*$')

# ---------------------------------------------------------------- naming helpers
def slug(s, fallback='X'):
    """UPPER_SNAKE env-name fragment from an arbitrary label."""
    if not isinstance(s, str) or not s.strip():
        return fallback
    out = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_').upper()
    return (out[:40].rstrip('_')) or fallback

def env_quote(v):
    """dotenv-compatible value encoding; non-strings become compact JSON."""
    if not isinstance(v, str):
        v = json.dumps(v, ensure_ascii=False, separators=(',', ':'))
    if BARE_OK.match(v) and v == v.strip():
        return v
    v = (v.replace('\\', '\\\\').replace('"', '\\"')
          .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'))
    return '"%s"' % v

def is_test_key(raw):
    return bool(re.search(r'(_test$|private_key_test$)', raw))

# ---------------------------------------------------------------- entry collector
class Collector:
    """Accumulates env entries per section, deduping var names."""
    def __init__(self):
        self.sections = OrderedDict()   # title -> [entry]
        self.taken = {}
        self.ignored = []               # non-credential toggles (bool/int) — documented, not exported
        self.skipped = []               # deliberately NOT exported (PII-risk samples) — path + reason only
        self.labels = 0                 # leaves consumed as names/labels (entry 'key', token 'name')

    def add(self, section, var, value, source, context, in_use=None):
        base, n = var, 1
        while var in self.taken:
            n += 1
            var = '%s_%d' % (base, n)
        self.taken[var] = True
        vs = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        self.sections.setdefault(section, []).append({
            'var': var, 'value': value, 'source': source, 'context': context,
            'test': is_test_key(source.split('.')[-1]) or var.endswith('_TEST'),
            'empty': (not vs.strip()), 'len': len(vs), 'in_use': in_use})

    def ignore(self, source, value):
        self.ignored.append({'source': source, 'value': value})

    def skip(self, source, reason, leaf_count):
        self.skipped.append({'source': source, 'reason': reason, 'leaves': leaf_count})

    def count(self):
        return sum(len(v) for v in self.sections.values())

# ---------------------------------------------------------------- extraction
SEC_EXTERNAL = 'External service credentials (Bubble built-in integrations)'
SEC_APICONN = 'API Connector (settings.secure mirror — private auth & params)'
SEC_PLUGSEC = 'Plugin secure keys (settings.secure)'
SEC_PLUGCS = 'Plugin client-safe config (settings.client_safe — publishable keys / app ids)'
SEC_APITOK = 'Bubble Data/Workflow API tokens (for migration via Data API)'
SEC_OAUTH = 'OAuth provider apps (this app acts as an OAuth provider)'
SEC_ZAPIER = 'Zapier'
SEC_MOBILE = 'Mobile app signing (Apple / Android)'
SEC_INTERNAL = 'Bubble internal (not reusable outside Bubble — kept for completeness)'

INTERNAL_KEYS = {'cRb', 'public_jwk', 'private_jwk', 'oauth_login_page',
                 'username', 'password'}

def flatten(prefix_path, name_parts, obj, put):
    """Generic fallback: emit every scalar leaf; dicts recurse; lists JSON-dump."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(prefix_path + '.' + k, name_parts + [k], v, put)
    else:
        put(name_parts, obj, prefix_path)

def extract(data, plugin_names):
    s = data.get('settings') or {}
    sec = s.get('secure') or {}
    cs = s.get('client_safe') or {}
    col = Collector()

    # usage detection — same content + reference idioms as bubble_inventory.py
    content_raw = json.dumps({k: data.get(k) for k in
                              ('pages', 'element_definitions', 'api', 'option_sets',
                               'styles', 'settings', 'user_types', 'mobile_views')},
                             separators=(',', ':'))
    def plugin_used(pid):
        return content_raw.count('"type":"%s-' % pid) > 0
    cs_ac = cs.get('apiconnector2') or {}
    def provider_used(aid):
        prov = cs_ac.get(aid) if isinstance(cs_ac.get(aid), dict) else {}
        for cid in (prov.get('calls') or {}):
            if ('"apiconnector2-%s.%s"' % (aid, cid)) in content_raw or \
               ('"apiconnector2.%s.%s"' % (aid, cid)) in content_raw:
                return True
        return False
    def provider_name(aid):
        prov = cs_ac.get(aid)
        return (prov.get('human') if isinstance(prov, dict) else None) or aid
    def call_name(aid, cid):
        prov = cs_ac.get(aid)
        call = (prov.get('calls') or {}).get(cid) if isinstance(prov, dict) else None
        return (call.get('name') if isinstance(call, dict) else None) or cid
    def pname(pid):
        return plugin_names.get(pid) or pid

    for key, val in sec.items():
        src = 'settings.secure.' + key
        if isinstance(val, (bool, int, float)) and not isinstance(val, str):
            col.ignore(src, val)
            continue

        m = PLUGIN_ID.match(key)
        if m:                                              # flat plugin secure key
            pid, suffix = m.group(1), m.group(2)
            col.add(SEC_PLUGSEC, 'PLUGIN_%s_%s' % (slug(pname(pid), pid), slug(suffix)),
                    val, src, 'plugin "%s" (%s)' % (pname(pid), pid),
                    in_use=plugin_used(pid))

        elif key == 'apiconnector2' and isinstance(val, dict):
            for aid, prov in val.items():
                if not isinstance(prov, dict):
                    continue
                pn, used = provider_name(aid), provider_used(aid)
                psrc = src + '.' + aid
                pslug = slug(pn, aid)
                for fk, fv in prov.items():
                    if fk == 'calls' and isinstance(fv, dict):
                        for cid, call in fv.items():
                            if not isinstance(call, dict):
                                continue
                            for pg, pgd in call.items():
                                if pg in ('url_params', 'body_params', 'headers', 'params') \
                                        and isinstance(pgd, dict):
                                    for pid_, entry in pgd.items():
                                        if isinstance(entry, dict):
                                            kn = entry.get('key') or pid_
                                            if entry.get('key'):
                                                col.labels += 1
                                            col.add(SEC_APICONN,
                                                    'API_%s_%s_%s' % (pslug, slug(call_name(aid, cid), cid), slug(kn)),
                                                    entry.get('value', ''),
                                                    '%s.calls.%s.%s.%s' % (psrc, cid, pg, pid_),
                                                    'provider "%s" · call "%s" · %s param "%s"'
                                                    % (pn, call_name(aid, cid), pg.replace('_', ' '), kn),
                                                    in_use=used)
                                elif pg == 'full_response':
                                    # saved initialization response body — sample DATA (may hold
                                    # real PII), not a credential; never copied into .env
                                    col.skip('%s.calls.%s.full_response' % (psrc, cid),
                                             'initialization sample response (PII risk) — re-initialize the call instead',
                                             count_scalar_leaves(pgd))
                                else:
                                    col.skip('%s.calls.%s.%s' % (psrc, cid, pg),
                                             'unrecognized call field (%s) — inspect manually if needed'
                                             % type(pgd).__name__,
                                             count_scalar_leaves(pgd))
                    elif fk in ('shared_headers', 'shared_params') and isinstance(fv, dict):
                        for pid_, entry in fv.items():
                            if isinstance(entry, dict):
                                kn = entry.get('key') or pid_
                                if entry.get('key'):
                                    col.labels += 1
                                col.add(SEC_APICONN, 'API_%s_SHARED_%s' % (pslug, slug(kn)),
                                        entry.get('value', ''),
                                        '%s.%s.%s' % (psrc, fk, pid_),
                                        'provider "%s" · %s "%s"' % (pn, fk.replace('_', ' '), kn),
                                        in_use=used)
                    elif isinstance(fv, (bool, int, float)) and not isinstance(fv, str):
                        col.ignore(psrc + '.' + fk, fv)
                    else:                                   # private_key[_test], appsecret, username, password…
                        col.add(SEC_APICONN, 'API_%s_%s' % (pslug, slug(fk)),
                                fv, psrc + '.' + fk,
                                'provider "%s" · %s' % (pn, fk), in_use=used)

        elif key == 'api_tokens' and isinstance(val, dict):
            for tid, tok in val.items():
                if isinstance(tok, dict):
                    label = tok.get('name') or tid[:8]
                    if tok.get('name'):
                        col.labels += 1
                    col.add(SEC_APITOK, 'BUBBLE_API_TOKEN_%s' % slug(label, tid[:8]),
                            tok.get('private_key', ''), src + '.' + tid,
                            'Bubble API token "%s"' % label)

        elif key == 'oauth_client_apps' and isinstance(val, dict):
            for oid, app in val.items():
                if isinstance(app, dict):
                    label = app.get('name') or oid[:8]
                    if app.get('name'):
                        col.labels += 1
                    for fk in ('client_secret', 'redirect_uri'):
                        if app.get(fk) is not None:
                            col.add(SEC_OAUTH, 'OAUTH_APP_%s_%s' % (slug(label, oid[:8]), slug(fk)),
                                    app.get(fk), '%s.%s.%s' % (src, oid, fk),
                                    'OAuth client app "%s"' % label)

        elif key == 'zapier' and isinstance(val, dict):
            for zid, zap in (val.get('zaps') or {}).items():
                col.add(SEC_ZAPIER, 'ZAPIER_ZAP_%s' % slug(zid),
                        zap, '%s.zaps.%s' % (src, zid),
                        'Zapier zap %s (JSON, incl. webhook URLs)' % zid)

        elif key == 'mobile' and isinstance(val, dict):
            def put_mobile(parts, leaf, path):
                if isinstance(leaf, (bool, int, float)) and not isinstance(leaf, str):
                    col.ignore(path, leaf)
                else:
                    col.add(SEC_MOBILE, 'MOBILE_%s' % '_'.join(slug(p) for p in parts),
                            leaf, path, 'mobile app config/signing')
            for k2, v2 in val.items():
                if isinstance(v2, dict) and k2 in ('apple', 'android'):
                    for k3, v3 in v2.items():
                        put_mobile([k2, k3], v3, '%s.%s.%s' % (src, k2, k3))
                else:
                    put_mobile([k2], v2, src + '.' + k2)

        elif key == 'appconnector' and isinstance(val, dict):
            for aid, app in val.items():
                if isinstance(app, dict):
                    for fk, fv in app.items():
                        col.add(SEC_INTERNAL, 'BUBBLE_APPCONNECTOR_%s_%s' % (slug(aid), slug(fk)),
                                fv, '%s.%s.%s' % (src, aid, fk),
                                'Bubble App Connector')

        elif key == 'general_keys' and isinstance(val, dict):
            for gk, gv in val.items():
                if isinstance(gv, (bool, int, float)) and not isinstance(gv, str):
                    col.ignore(src + '.' + gk, gv)
                else:
                    col.add(SEC_EXTERNAL, slug(gk), gv, src + '.' + gk,
                            'Bubble general key "%s"' % gk)

        elif key in INTERNAL_KEYS:
            nice = {'username': 'BUBBLE_SITE_USERNAME', 'password': 'BUBBLE_SITE_PASSWORD',
                    'cRb': 'BUBBLE_INTERNAL_CRB'}.get(key, 'BUBBLE_' + slug(key))
            col.add(SEC_INTERNAL, nice, val, src, 'Bubble internal')

        elif isinstance(val, str):                          # named service keys + unknown strings
            col.add(SEC_EXTERNAL, slug(key), val, src, 'Bubble built-in setting "%s"' % key)

        else:                                               # unknown structure — flatten, lose nothing
            def put_generic(parts, leaf, path, _k=key):
                if isinstance(leaf, (bool, int, float)) and not isinstance(leaf, str):
                    col.ignore(path, leaf)
                else:
                    col.add(SEC_INTERNAL, '_'.join(slug(p) for p in parts),
                            leaf, path, 'settings.secure.%s (unrecognized structure)' % _k)
            flatten(src, [key], val, put_generic)

    # plugin client-safe config values
    for key in sorted(cs.keys()):
        m = PLUGIN_ID.match(key)
        if not m:
            continue
        val = cs[key]
        if not isinstance(val, str):
            continue                       # element defaults etc. — not config values
        pid, suffix = m.group(1), m.group(2)
        col.add(SEC_PLUGCS, 'PLUGIN_%s_%s' % (slug(pname(pid), pid), slug(suffix)),
                val, 'settings.client_safe.' + key,
                'plugin "%s" (%s) — client-safe' % (pname(pid), pid),
                in_use=plugin_used(pid))

    return col, sec

# ---------------------------------------------------------------- leaf accounting
def count_scalar_leaves(o):
    if isinstance(o, dict):
        return sum(count_scalar_leaves(v) for v in o.values())
    if isinstance(o, list):
        return 1                            # lists are exported as one JSON value
    return 1

def accounted_leaves(col):
    """Leaves of settings.secure accounted for (client-safe section comes from elsewhere)."""
    n = col.labels
    for title, entries in col.sections.items():
        if title == SEC_PLUGCS:
            continue
        for e in entries:
            v = e['value']
            n += count_scalar_leaves(v) if isinstance(v, (dict, list)) else 1
    n += len(col.ignored)
    n += sum(s['leaves'] for s in col.skipped)
    return n

# ---------------------------------------------------------------- writers
def write_outputs(col, outdir, app_domain, input_name):
    os.makedirs(outdir, exist_ok=True)
    order = [SEC_EXTERNAL, SEC_APICONN, SEC_PLUGSEC, SEC_PLUGCS, SEC_APITOK,
             SEC_OAUTH, SEC_ZAPIER, SEC_MOBILE, SEC_INTERNAL]
    sections = [(t, col.sections[t]) for t in order if t in col.sections]
    for t in col.sections:                  # any section not in the fixed order
        if t not in order:
            sections.append((t, col.sections[t]))

    header = ('# Credentials extracted from the Bubble export %s (app: %s).\n'
              '# LIVE VALUES — never commit this file, never paste it into chats/docs.\n'
              '# Map of every var: see ENV-KEYS.md. Blank template: .env.example.\n'
              % (input_name, app_domain or '?'))

    env_path = os.path.join(outdir, '.env')
    with open(env_path, 'w') as f, open(os.path.join(outdir, '.env.example'), 'w') as fx:
        f.write(header)
        fx.write(header.replace('LIVE VALUES — never commit this file, never paste it into chats/docs.',
                                'Blank template — safe to commit; fill from the secret store.'))
        for title, entries in sections:
            for fh in (f, fx):
                fh.write('\n# ==== %s ====\n' % title)
            for e in entries:
                note = ' · UNUSED in app' if e['in_use'] is False else ''
                for fh in (f, fx):
                    fh.write('# %s%s\n' % (e['source'], note))
                f.write('%s=%s\n' % (e['var'], env_quote(e['value'])))
                fx.write('%s=\n' % e['var'])
    os.chmod(env_path, 0o600)

    with open(os.path.join(outdir, '.gitignore'), 'w') as f:
        f.write('.env\n')

    md = os.path.join(outdir, 'ENV-KEYS.md')
    with open(md, 'w') as f:
        f.write('# ENV keys extracted from the Bubble export\n\n')
        f.write('App: **%s** · source: `%s` · %d variables. Values live ONLY in `secrets/.env` '
                '(chmod 600, gitignored) — this file and `.env.example` carry names, not values.\n\n'
                % (app_domain or '?', input_name, col.count()))
        f.write('**For the rebuild agent:** configure each var in the new system\'s secret store / '
                '`.env` as mapped by the level-up pack (integration map + TARGET-ARCHITECTURE). '
                '`test` rows are Bubble *test-version* values; `in use = no` rows belong to '
                'providers/plugins the app never invokes (candidates to drop, confirm with the '
                'owner). Rotate anything that may have leaked before go-live.\n\n')
        for title, entries in sections:
            f.write('## %s\n\n' % title)
            f.write('| Var | Source (export path) | Context | test | len | in use |\n')
            f.write('|---|---|---|---|---|---|\n')
            for e in entries:
                f.write('| `%s` | `%s` | %s | %s | %s | %s |\n' % (
                    e['var'], e['source'], e['context'],
                    'test' if e['test'] else '',
                    'EMPTY' if e['empty'] else str(e['len']),
                    {True: 'yes', False: 'no', None: '—'}[e['in_use']]))
            f.write('\n')
        if col.skipped:
            f.write('## Deliberately NOT exported (data samples, not credentials)\n\n')
            for sk in col.skipped:
                f.write('- `%s` — %s\n' % (sk['source'], sk['reason']))
            f.write('\n')
        if col.ignored:
            f.write('## Ignored non-credential toggles (bool/int — informational)\n\n')
            for ig in col.ignored:
                f.write('- `%s` = `%s`\n' % (ig['source'], json.dumps(ig['value'])))
            f.write('\n')
    return env_path

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='Extract every credential/private config value '
                                             'from a .bubble export into secrets/.env + docs')
    ap.add_argument('input')
    ap.add_argument('--outdir', default=None)
    ap.add_argument('--plugin-names', default=None,
                    help="JSON {pluginId: name}; defaults to the audit skill's plugin_names.json")
    args = ap.parse_args()
    outdir = args.outdir or (os.path.splitext(args.input)[0] + '_secrets')

    log('Loading %s …' % args.input)
    with open(args.input, 'r') as f:
        data = json.load(f)

    names = {}
    names_path = args.plugin_names or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..', 'audit', 'references', 'plugin_names.json')
    if os.path.exists(names_path):
        try:
            for k, v in json.load(open(names_path)).items():
                if k.startswith('_') or not v:
                    continue
                names[k] = v.get('name') if isinstance(v, dict) else v
        except Exception as e:
            log('  (plugin names not loaded: %s)' % e)

    col, sec = extract(data, names)
    app_domain = ((data.get('settings') or {}).get('client_safe') or {}).get('app_topdomain')
    env_path = write_outputs(col, outdir, app_domain, os.path.basename(args.input))

    total_leaves = count_scalar_leaves(sec)
    accounted = accounted_leaves(col)
    log('\nSecrets preserved -> %s' % outdir)
    for title, entries in col.sections.items():
        log('  %-70s %3d vars' % (title, len(entries)))
    log('  Ignored non-credential toggles: %d (listed in ENV-KEYS.md)' % len(col.ignored))
    if col.skipped:
        log('  Skipped data samples (PII risk, e.g. call full_response): %d (paths in ENV-KEYS.md)'
            % len(col.skipped))
    log('  Leaf accounting: %d scalar leaves in settings.secure, %d accounted for%s'
        % (total_leaves, accounted,
           '' if accounted >= total_leaves else '  ⚠ MISMATCH — some values were NOT preserved!'))
    if accounted < total_leaves:
        sys.exit(2)
    log('  .env is chmod 600 and gitignored. NEVER commit, cat, or paste it.')

if __name__ == '__main__':
    main()
