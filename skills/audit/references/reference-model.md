# Bubble `.bubble` export — reference model

How a Bubble app export stores entities and the references between them. Read this before
changing `scripts/bubble_audit.py` or when a result looks wrong. Everything below was derived
empirically from real exports and validated against a hand audit. Names and ids in the examples are
made up; data from the apps being migrated (names, ids, counts) stays in each project's folder and
never goes into this file.

## File shape

- One giant single-line JSON object, UTF-8, often 50–150 MB. Load with `json.load`; never read
  it into an LLM context.
- Top-level keys that matter:
  - `pages` — every page (keyed by a **wrapper id**, not the page's own id).
  - `element_definitions` — reusable element definitions.
  - `api` — backend workflows (API workflows, DB triggers, recurring events, custom events) **and**
    API Connector calls.
  - `option_sets` — option sets (keyed by name).
  - `styles` — styles (keyed by style id, which equals the style's `id`).
  - `user_types` — data types / fields.
  - `mobile_views` — mobile views/reusables.
  - `settings.client_safe` / `settings.secure` — app settings, incl. `plugins` registry,
    `api_wf_folder_list`, `default_styles`, `dbconnector_queries`, plugin credentials.
- Top-level keys to **exclude** from any "usage" scan (they are editor metadata or trash, and
  counting them inflates usage):
  - `_index` — `id_to_path` (every element→path), `issues_list`/`issues_sub` (the editor issue
    checker — NOT an unused analysis), `page_name_to_id`, `custom_name_to_id`. A page/reusable
    id appears here as pure metadata.
  - `comments` — editor comments.
  - `holding_pen` — the deleted-elements bin. A reference from here must NOT count as "used".
  - `screenshot`, `closest_ancestor_snapshots`.

## The id gotcha

- Every entity id is a short base-62-ish token (e.g. `aB3xQ`, `cZ9kL0`, `ORDER_EVT_001`). **Ids are
  globally unique** across the whole app (single uid counter), so counting a quoted id token is
  collision-safe.
- **Trailing digits are part of the id, not an instance suffix.** Many page/def/api ids end in a
  digit (`cZ9kL0`, `dQ4mn2`). Do **not** strip trailing digits.
- Instance suffixes DO exist but only for elements *inside a placed reusable* (when reusable `X`
  is dropped on a page, its internal element `fK2pa` becomes `fK2pa1`, `fK2pa2`, …). Top-level
  entities (pages, defs, api events, option sets, styles) are referenced by their **exact id**.

## Element display names (what the editor shows)

When reporting *which element* a workflow/ghost-ref/dead-trigger sits on, show the name the user
sees in the Bubble **editor's element tree**, not Bubble's internal auto-label. Each element dict
can carry up to three name fields:

- **`name`** — the custom name the user typed in the editor (`"Button Archive note"`,
  `"date Start"`, `"g list"`, even a single `"X"`). Present **only when the element was renamed**.
  Users write anything, so it often does NOT start with the type word.
- **`default_name`** — the auto-generated `"<Type> <letters>"` label (`"Button H"`, `"Group A"`,
  `"Popup L"`). Present for essentially every placed element; it's Bubble's internal fallback.
- **`custom_definition_name`** — only on reusable-element instances (`type: CustomElement`); holds
  a snapshot of the reusable's name at placement.

**For a regular element the editor label is, in order:**
1. `name` if non-empty (the human rename).
2. Else, for a **content-bearing element** (Button, Text, Link, Input, Dropdown…), a label computed
   LIVE from its content: **`"<Type> <caption/text/placeholder>"`** — e.g. a button with no custom
   name whose caption is "Issue receipt" shows as **`"Button Issue receipt"`**, NOT "Button H". The
   content lives in `properties.text` / `properties.caption` / `properties.placeholder` (a
   `TextExpression` — take `entries.0`, the leading static run; strip Bubble `[ul]/[li]/[color=…]`
   markup; content-less or purely-dynamic → skip). The `<Type>` word = `default_name` minus its
   trailing instance letters ("Button H" → "Button"). This is NEVER stored in `default_name`; the
   editor derives it. Confirmed empirically: elements whose `name` equals their content overwhelmingly
   match `"<Type> <caption>"`, not the bare caption, and unnamed content elements are common.
3. Else `default_name` ("Group A", "Icon B" — content-less elements).

In a large app, most element nodes carry `default_name`, many also carry `name`, and where both
exist they almost always differ. **Showing `default_name` for an unnamed content element is the #1
recognizability complaint** — an auditor searching for "Button H" finds nothing; "Button Issue
receipt" they recognize.

**Reusable-element INSTANCES (`type: CustomElement`) are the exception — all three baked name fields
go STALE when the reusable is renamed.** `default_name` (= reusable-name + instance letter),
`name`, and `custom_definition_name` are all snapshotted at placement time and are NOT updated when
the definition is later renamed. Verified on production exports: a large share of instances carry
a stale `default_name`, and `name` is stale for most instances that have one (a stale auto-name like
`"z3 Top Menu A"` is string-indistinguishable from a genuine per-instance rename). The editor instead
labels an instance by the **definition's CURRENT name**, resolved via `properties.custom_id` → the
`element_definitions` entry whose inner `id` == custom_id (instances resolve by inner id, never by
wrapper key). So: **CustomElement label = current def name (+ the frozen instance letter from
`default_name`)**, e.g. instance with `default_name "z2 Top Menu A"` whose def is now `"Side Nav"`
→ show `"Side Nav A"`. This deliberately drops genuine per-instance renames (a small minority)
in favor of a name that always exists in the reusables list. If custom_id doesn't resolve (deleted
reusable), fall back to `name`/`default_name`/`custom_definition_name`.

`bubble_audit.py` centralizes all of this in `editor_name(el, fallback, def_names)` (order: reusable
instance → `name` → content-label → `default_name`; helpers `_element_content`, `_type_word`,
`build_def_names`) and uses it for the workflow audit (section 8) and removed-plugin refs (section
10). Never surface `default_name` alone — the auditor won't recognize "Button H" or a stale "z2 Top
Menu A". (Both the content-label and stale-instance cases were caught by adversarial
verification after an initial `name`→`default_name`→`custom_definition_name` rule shipped.)

## Usage-scan primitive

Serialize the content sections (everything except the excluded metadata/trash above) to a string,
then `Counter(re.findall(r'"([A-Za-z0-9_]+)"', content_raw))`. For any id, the number of quoted
occurrences **minus** the occurrences inside its own definition object = references elsewhere.
This uniformly answers "is X referenced?" and catches reference paths you didn't enumerate.

## Per-entity reference rules

### Pages
- `pages` is keyed by a **wrapper id** ≠ the page's inner `id` field. Navigation targets the
  **inner id**.
- A page's inner id appears in its own object once (`"id":"<inner>"`).
- Referenced by: `ChangePage.element_id` (yes, the field is `element_id` but it holds a **page**
  inner id), `Link.page`, `MobileNavigate`, and `ListGoToPage` (whose target is a dynamic
  expression — not statically resolvable).
- **Name/URL references (second pass).** A page can also be linked by its **name (URL slug)**, not
  its id, inside free text the id-scan never sees: hardcoded `Link`/`OpenURL` URLs,
  Run-JavaScript action code, `HTML` embed elements, per-page `html_header`, and app custom
  headers. This content lives inside nested expression structures, so scan string *leaves*, not
  flat property values. The real signal is the app's own page-URL form:
  `(www.)?<app_topdomain>/[version-<branch>/]<slug>` (also `<appid>.bubbleapps.io/...`). The
  `version-<branch>/` segment is easy to forget and is where OAuth-callback pages hide
  (`.../version-live/<oauth-callback-page>`). Filter out same-slug matches on *other* hosts
  (third-party backends, file storage such as Dropbox or S3 `appforest_uf`, social networks) — those
  are coincidental. The script rescues
  name-referenced pages from the deletable list.
- **Caveat:** Bubble pages are all URL-routable. Even after both passes, "no reference found" ≠
  provably safe — bare-name JS navigation and truly external inbound links are undetectable. Page
  results are *candidates*, ranked by confidence, not a delete list.

### Native mobile views (`mobile_views`)

- Top-level `mobile_views` dict: entries are `type: 'Page'` with `is_mobile_view: true`, same
  shape as pages (dict-key ≠ inner `id`, `elements`, `workflows`, `custom_states`). They have NO
  public URL — reachability is closed-world.
- A view is reachable only via: `settings.client_safe.initial_mobile_view` (id of the entry
  view), a system role in `settings.client_safe.built_in_mobile_views` ({role_name: view_id},
  e.g. update_app, reset_password; `built_in_mobile_reusables` similarly pins reusables like
  offline_banner), a **`MobileNavigate` action whose `properties.element_id` is the DESTINATION
  view's inner id** (naming quirk: it's called element_id but holds a view id), or a **`DeepLink`
  action whose `properties.destination_view` is the view id** — push notifications / magic links
  landing on a view. DeepLink lives in BACKEND workflows too, so scan the `api` section for view
  references, not just pages/reusables/views (a backend workflow that sends a magic link can be
  the only thing pointing at a login view — and note Bubble built-ins are always registered in
  `built_in_mobile_views`, so a view NOT listed there is developer-created, not a Bubble default).
- **Do NOT count quoted-id occurrences to decide view usage**: elements of views created by
  cloning keep `current_parent` pointing at the SOURCE view's id — pure structural noise (a cloned
  view can carry many such refs and still never be navigated to). Only MobileNavigate targets +
  settings roles count.
- **Broken navigations**: a MobileNavigate target matching no existing view id = the view was
  deleted; the action silently fails at runtime. Report container + whether the owning workflow
  has `properties.workflow_disabled: true`.
- **Same-name twin guard** (mirrors the reusables rule): views can share an exact display name.
  Bubble's App Search Tool matches "Go to view …" by NAME, so a live twin's navigations look
  like they belong to the dead one — the owner will search, find "1 thing" and conclude the
  flagged view is used (e.g. a navbar navigates to the live twin, and the dead twin looks used).
  Never present a same-named view as a clean delete; route it to
  a verify bucket showing the used twin's id. NB: when counting refs by wrapper key, the view's
  own dict KEY in `mobile_views` shows up as 1 structural occurrence — not a reference.
  **Editor quirk (verified in the editor):** the App Manager shows a SINGLE list entry for
  duplicated view names — the dead twin is invisible in the list even though it exists and is
  indexed in `_index.id_to_path`. To surface it: open the visible one, confirm it's the live
  twin, RENAME it temporarily → the hidden twin appears in the list → delete it → undo the
  rename. This procedure is written into the report's dup-name note.
- Mobile views participate in everything else: they're inside the CONTENT_KEYS corpus (so
  plugin/option-set/field/style usage in mobile counts — no false "unused"), they must be roots
  for reusable placement, backend `sched_client` (a WF scheduled only from a mobile view is NOT
  transitively dead), and the page/reusable workflow audit (custom events, orphan triggers,
  never-rendered triggers) with kind='mobile'.
- **Reusables & mobile**: placements inside mobile views are reachability ROOTS (`MOBILE:` in the
  placement scan), and ids in `settings.client_safe.built_in_mobile_reusables` (e.g.
  offline_banner) are shown by the native runtime itself — treat them as roots/used even when
  never placed as a `CustomElement` (they may also be placed, but don't rely on that). Mobile
  reusables live in the same `element_definitions` dict as web ones, so
  their internal workflows are covered by the normal reusable audit.
- Caveat for the deletable list: push notifications / deep links can open views directly and are
  not in the export — phrase as "verify before deleting".
- **WebView elements — web pages embedded in the native app**: a mobile view can embed a WEB page
  via a `WebView` element whose `properties.page` holds the web page's **inner id** (plus
  `data_to_send` / `add_parameters`). Because `mobile_views` is inside CONTENT_KEYS, the pages
  audit's quoted-id count sees these — a page used only as a native webview is NOT flagged (apps
  often keep pages that exist solely for this). A WebView pointing at an EXTERNAL/literal URL lands
  in the url corpus, which
  also spans CONTENT_KEYS. Keep `build_script_corpus` covering `mobile_views` too (JS/HTML strings
  in mobile can reference data fields/types by name).

### Reusable elements
- Definition has a wrapper key and an inner `id`. A **placed** reusable is an element with
  `type == "CustomElement"` and `properties.custom_id == <definition inner id>`. That is the only
  placement mechanism.
- **Deleted reusables** are excluded up front (skip `element_definitions` entries with
  `deleted:true`, like option sets/fields/tables). In practice Bubble rarely flags them — it drops
  deleted reusables from the export or moves them to `holding_pen` (excluded anyway); flagged-deleted
  reusables are rare and the holding_pen is often empty. So a definition that
  is still present in `element_definitions` and in `_index.id_to_path` (`%ed.<wrapper>`) is a
  **live** reusable even if unplaced — not a deleted one.
- "Used" = its inner id appears as some `CustomElement.custom_id`. Reusables can nest inside other
  reusables, so also do a reachability pass from page/mobile roots to catch definitions that are
  only placed inside other *dead* definitions (transitively dead).
- Dev convention: names prefixed `❌` / containing `copy` / `test` are usually already-dead.
- **Duplicate-name gotcha (important false-positive class).** The editor can end up with two
  reusable definitions sharing an *exact* name (a leftover copy). They have distinct inner ids and
  are placed independently — one twin may be used (`custom_id` = its id) while the other is placed
  nowhere. The unplaced twin is *technically* unused, but **Bubble's reusable search matches by
  NAME**, so selecting the orphan shows the twin's placements under it, making it look used — and
  it's easy to delete the wrong one. So: for any reusable flagged unused, check whether a same-name
  sibling is reachable; if so, do NOT list it as a clean delete — surface it in a separate
  "duplicate name — verify (used twin: <id>)" bucket. (Seen in practice: before this rule, the
  unplaced twin of a used menu reusable was shown as a clean delete.)

### Backend workflows (`api`)
- Entry types: `APIEvent` (the API Workflows — the ones this question is about), plus
  `DatabaseTriggerEvent` (auto-fires on DB change), `RecurringEvent` (scheduled), `CustomEvent`.
  DB triggers and recurring events self-fire — exclude them from "unused".
- `api` dict key ≠ inner `id`. References use the **inner id**.
- An `APIEvent` is reachable iff it is **exposed** (see next bullet) **or** its inner
  id is the `api_event` target of a `ScheduleAPIEvent` / `ScheduleAPIEventOnList` action anywhere
  **or** the app calls it on itself via an API Connector self-call (see below).
- **Exposure — the `expose` key is serialized only when it differs from the default.** A MISSING
  `expose` key means the workflow IS exposed (checkbox checked); the export writes
  `expose: false` only when "Expose as a public API workflow" is explicitly unchecked. Verified
  empirically on production exports: the absent-key APIEvents were exactly the endpoints the app
  itself invokes through API Connector self-calls, or external webhooks. So:
  `expose = p.get('expose', True)`, gated
  on the app-level switch `settings.client_safe.exposes_wf_api` (if the Workflow API is off,
  nothing is externally reachable and the absent-key default falls back to false).
  Treating absent as not-exposed produced FALSE POSITIVES (flagging live endpoints as dead).
- **Self-API calls:** apps commonly declare an API Connector provider pointing at their own
  Workflow API (call URL `…/wf/<wf_name>` or `<shared-param>]/<wf_name>`). When the last URL
  segment matches a backend `wf_name`, that call references the workflow: a USED self-call makes
  the workflow used (extra reachability root); an unused one is annotated in the report
  (`→ workflow interno: <name>`) so call and workflow can be deleted together.
- Because a non-exposed workflow can *only* run if scheduled internally, an `APIEvent` that is not
  exposed, appears in no scheduling action and is target of no used self-call literally cannot
  execute — high confidence dead.
- Transitive deadness — the reachability graph must span **ALL `api` entries, not just
  `APIEvent`s**: `DatabaseTriggerEvent` and `RecurringEvent` fire on their own (always-live
  ROOTS — a DB trigger that schedules an APIEvent keeps it alive), and backend `CustomEvent`s are
  intermediate nodes (page triggers a backend custom event whose actions schedule an APIEvent).
  Edges come from each node's `actions`: `ScheduleAPIEvent(OnList)`.`api_event` AND the
  custom-event trigger actions (`TriggerCustomEvent`, `ScheduleCustom`,
  `TriggerCustomEventFromReusable`, **`TriggerBackendCustomEvent`** — the last one is how PAGES
  call backend custom events; forgetting it orphans every such chain).`custom_event`.
  Roots = exposed endpoints + used self-API targets + anything scheduled/triggered from a
  page/reusable (client) context + DB triggers/recurring events. Unreachable = transitively dead.
  NB: a workflow that only schedules ITSELF (batch recursion) is still dead — self-loops don't
  make a root.
- Folder id → name via `settings.client_safe.api_wf_folder_list`.
- **Webhook signature — route to "verify", never to "delete".** An `APIEvent` whose
  `properties.parameter_def == 'auto'` had "Parameter definition = Detect request data" set in the
  editor — the setup used for **incoming webhooks** (payment gateways, messaging, e-signature…). If
  `properties.raw_data` is present it holds the sample payload captured when the endpoint was
  initialized by a real external call — hard evidence it was wired to an outside service. The
  caller is external and invisible to static analysis, so a webhook-shaped WF that "looks
  unreachable" goes to a **verify bucket**, not the deletable list. Caveat to surface: if
  `expose: false`, Bubble rejects external calls TODAY — the webhook is either broken, disabled on
  purpose, or enabled only in another environment; the owner must check live. Seen in practice: a
  payment-provider webhook (expose false + captured sample payload) was flagged deletable until the
  owner identified it.
- Some `api` entries have no `type` and only `{ignore_privacy_rules}` — empty placeholders; ignore.

### Option Sets
- Keyed by name in `option_sets`; some carry `deleted: true` (already trashed).
- Canonical reference token is **`option.<name>`** (e.g. a field of type option set is
  `"value":"option.order_status"`, a dropdown source `"option_set":"option.<name>"`). Used iff
  `option.<name>` appears anywhere in content.

### Plugins
- `settings.client_safe.plugins` = `{ id → version }`. Short-name ids (`chartjs`, `fullcalendar`,
  `apiconnector2`, `google`…) are official/legacy plugins; long ids (`1581699734631x…`) are
  marketplace plugins.
- A plugin's elements/actions have `type` values `"<pluginId>-<suffix>"`; API Connector calls are
  `"apiconnector2-<callId>"`. Used iff any `type` starts with `<pluginId>-`/`<pluginId>.`.
- Plugins with no element/action can still be functional: `dbconnector` with populated
  `dbconnector_queries`; `google` (fonts/maps/OAuth, appears hundreds of times); any plugin with
  credential/config settings keys (`<id>_appsecret`, `<id>_shared_headers_*`, `<plugin>_apikey`,
  `docusign_*`). The script splits these into "no visible element but active — verify" vs "orphaned".
- **Config-based plugins** (used via settings, not element/action types) are another false-positive
  class: **Zapier** (`zapiernew`) is used iff `settings.client_safe.zapier.zaps` is non-empty (each
  zap has a real subscribed webhook in `settings.secure.zapier`); `dbconnector` via
  `dbconnector_queries`; credential/header settings keys. Check these, not just types.
- **Paid plugins**: an unused *paid* plugin is wasted recurring cost, so flag it louder. Pricing is
  NOT in the export — research it from the marketplace (the plugin page is a JS SPA; a JS-rendering
  proxy like `r.jina.ai/https://bubble.io/plugin/<id>` reveals the price block, or vendor/forum
  pages). Cache in `references/plugin_pricing.json` (`{id:{status,model,price}}`, marketplace-global).
  Only mark `paid` with a concrete source. The report shows a red alert + `💲 paid · <price>` badge
  and sorts paid unused plugins first.
- **Removed-plugin references (report section 10)**: some plugin ids appear in element/action
  `type`s (`<pluginId>-…`) but are NOT in `settings.client_safe.plugins` — the plugin was
  uninstalled while its elements/actions remained (broken/ghost refs). Detect by matching any
  `type` = `\d{13}x\d+-…` whose plugin-id part isn't installed; report each with the resolved plugin
  name + page/reusable + the element's **editor name** (see *Element display names*) or the workflow
  label (event name / triggering element + trigger type). Dedup actions per (plugin, workflow).
  Conversely a registered plugin with a same-named sibling can confuse (e.g. a client-side and a
  server-side variant of one plugin, one registered + unused and the other actually used) — verify
  by id, and a plugin flagged unused with a live same-named sibling deserves a note.
- **Headless/global plugins** are a real false-positive class: they're active project-wide the
  moment they're installed and place NO element or action, so they have **zero footprint** in the
  export yet are genuinely used — e.g. **Classify** (`1568299250417x684448291308175400`) applies
  CSS to elements globally via the element's ID; also SEO / header-injector / analytics plugins.
  "No footprint" therefore ≠ "safe to delete" for plugins. The script keeps a curated
  `HEADLESS_PLUGINS` set (routes them to the "verify" bucket with a *global* badge), and the
  orphaned bucket is framed as "review" with an explicit caveat about this class. Add newly-found
  global plugins to `HEADLESS_PLUGINS`.
- Plugin **display names are not in the export** for unused plugins (no placed element to name
  them). Resolve them from the marketplace: `https://bubble.io/plugin/<id>` (id is marketplace-
  global). The script caches known id→name in `references/plugin_names.json` (reused across
  projects) and renders each long-id plugin as a link to its marketplace page. A page returning
  only Bubble's generic shell = the plugin is **delisted** (store `null`; flagged as such — a
  strong safe-to-remove signal). Short-name ids get a friendly label from a built-in map.

### API Connector calls (declared endpoints)
- `settings.client_safe.apiconnector2` = `{apiId: {human: <provider name>, calls: {callId: {name,
  url, method, types, ...}}, auth...}}`. Each call is a declared outbound endpoint.
- A call is **invoked in TWO serialized forms — check BOTH** (they differ only in one character):
  * workflow ACTION ("use as action"): the action's `type` is `apiconnector2-<apiId>.<callId>` (HYPHEN);
  * DATA SOURCE ("use as data"): the expression node carries
    `"provider":"apiconnector2.<apiId>.<callId>"` (DOT).
  Unused = NEITHER form appears in the app logic (pages + element_definitions + api). Checking only
  the hyphen form false-flags every call used purely as a data source — in practice most of the
  calls it flagged were data-source usages (the editor's App Search Tool shows them).
  The declaration in settings uses `<apiId>.<callId>` in the `types` schema and
  `api.apiconnector2.<apiId>.<callId>` in `ret_value`, but settings are NOT part of the scanned app
  logic, so the declaration never false-matches either invocation form.
- **Exclude auth-internal calls**: OAuth `token_call` (id/name contains "token") and the provider's
  `oauth_user_data_call` are invoked automatically by the auth flow, not via the type — treat as
  used, or you get false positives.

### Styles
- `styles` is keyed by the style `id` (key == id). An element referencing a style stores
  `"style":"<id>"`. Used iff that pattern appears, or the style is a `settings.client_safe.
  default_styles[<type>]` (default for its element type). Note: because the style's own dict key
  equals its id, a naive quoted-token count over-counts by 1 — use the `"style":"<id>"` pattern.

### Workflows & Custom Events (page/reusable audit)
- Page/reusable workflows live under the container's `workflows` dict; each has a trigger `type`
  (event) + `properties` + `actions`. Backend custom events are `api` entries `type=CustomEvent`.
- **Custom events**: a `CustomEvent` workflow (backend or page/reusable) is "called" iff its `id`
  is the `custom_event` target of a `TriggerCustomEvent` / `ScheduleCustom` /
  `TriggerCustomEventFromReusable` / `TriggerBackendCustomEvent` action anywhere (the last type is
  how a page/reusable calls a BACKEND custom event — omitting it false-flags every backend custom
  event that is only called from pages). Uncalled = dead (high confidence).
- **Element-triggered workflows** (`ButtonClicked`, `InputChanged`, `PopupClosed/Opened`,
  `MapMarkerClicked`, `<pluginId>-<evt>` element events, …) fire on interaction with
  `properties.element_id` — which points to an element's **`id` FIELD, not its dict key** (elements
  have key ≠ id, same as pages/defs). **Root-id gotcha:** the container's OWN root element id lives
  at `container['id']`, NOT inside `container['elements']` — and it IS a valid trigger target. A
  popup-rooted reusable triggers on itself: "When <this popup> is closed/opened" binds
  `element_id` to the reusable's root id (same for a group-rooted reusable's ButtonClicked).
  Seed the element map with `container['id']` (always displayable — a reusable root's visibility
  is decided per placed instance) or every such self-referencing trigger is falsely flagged as
  "element deleted" (before this fix, popup- and group-rooted reusables were the main source of
  false orphan flags). Two dead-trigger cases:
  * **Orphan**: `element_id` resolves to no element in the container (root id included) → can
    never fire there. High confidence. But "missing from the container" ≠ "deleted": check a
    GLOBAL element-id index (all pages + element_definitions) — if the id exists in ANOTHER
    container, the element was **moved, not deleted**. The classic producer is **"convert group
    to reusable"**: Bubble moves the elements into a new reusable definition but leaves the
    original container's workflows behind, still bound to the old element_id (the element gets
    fresh workflows INSIDE the reusable). Report where the element went (`moved_to`) — it makes
    the finding verifiable in the editor, and answers the owner's objection "deleting a button
    deletes its workflows, so how can this exist?" (true for plain deletion; not for conversion).
    In practice orphan triggers often turn out to be this class: the buttons now live in a
    reusable, and the leftover workflows sit in the page or reusable they came from.
  * **Never rendered**: the trigger element is never displayable. Compute "can be visible" per
    element: `properties.is_visible` is not false (always a static bool — no dynamic expr), OR a
    `ShowElement`/`ToggleElement`/`AnimateElement`/`AlertShowMessage` action targets its id, OR a
    **conditional** reveals it. **Conditionals ARE in the export — under the element's `states` key**
    (each state = `{condition, properties, type:"State"}` = the "Conditional" tab).
    A conditional can show a hidden element when some state's `properties` contains `is_visible`.
    (Earlier I wrongly concluded conditionals were absent — I searched `"conditions"`; the real key
    is `"states"`.) Then walk the **parent chain**: the element is never rendered iff IT or ANY
    ANCESTOR can never be visible — a visible click target inside a group that never shows is dead.
- Lifecycle triggers (`PageLoaded`, `LoggedIn/Out`, `DoInterval`, `ConditionTrue`) have no
  `element_id` and can always fire → never flagged.
- When naming the trigger element and its blocking ancestor in the report, use the **editor name**
  (`editor_name(el)` — see *Element display names*), not the raw `default_name`, so the auditor
  recognizes the element they see in the editor (e.g. `Group checkout form`, not `Group A`).
- NB: a naive element-only never-rendered check (ignoring conditionals) produces mostly false
  positives — elements shown by a conditional. Residual caveat: conditionals that never evaluate
  true, plugin/JS-driven visibility.

### Color & font variables (design tokens)
- User-defined variables live in `settings.client_safe.color_tokens_user.default` and
  `font_tokens_user.default` — `{id: {name, deleted, rgba|font_family, order, …}}`. (`color_tokens`
  / `font_tokens` are the built-in theme tokens — not user variables; skip them.) A `deleted:true`
  flag marks trashed ones — exclude.
- **Do NOT count the bare token id.** Token ids are a *separate namespace* that can collide with
  element ids (the same id can be both a color var and an element), and the whole theme is snapshotted
  many times in the export (`hardcode_stored_expanded`) — both inflate a bare-id count into the
  thousands of false hits.
- Real usage = the CSS custom property: `var(--color_<id>_<state>)` / `var(--font_<id>_<state>)`
  (states: `_default`, `_default_rgb`, hover, …). A variable is unused iff no `var(--color_<id>`
  (resp. `var(--font_<id>`) with a `_`/`)` boundary appears anywhere in content. Definitions store
  `rgba`/`font_family`, never a `var()` self-ref, so this is collision- and snapshot-proof.
  (Same-named twin variables happen — one unused, the other referenced: check usage per id, never
  by name.)

### List ordering (report presentation)
Reusables sort alphabetically by name with leading emoji/symbols stripped (so `❌orders…` sorts
under "o", `🔁header…` under "h"). Plugins sort by name (unknown-name ones last, by id). Styles sort by
**Type then style name**. Backend workflows by folder then name. Keep these stable so re-runs diff
cleanly.

### Data types (tables) and fields — `user_types`
- `user_types` is keyed by type key. Built-in primitives (e.g. `text`) have only `fields`; **custom
  types have a `display`** — filter on that. Each type may carry `exposed_api` (bool = exposed in
  the native Data API), `privacy_role` (privacy rules, which reference fields), and `deleted:true`
  (already trashed). The **User** type is referenced as bare `"user"`, not `custom.user`;
  treat it as always-used.
- **Fields** live in `type.fields`, keyed by a **mangled key** (`<slug>_<typesuffix>`, e.g.
  `status_option_orderstatus`, `assignee_user`, `remark_text`). The value object has
  `display` (human name), `value` (the field's type: `text` / `user` / `custom.<t>` /
  `option.<o>` / …), and often `deleted:true`. Fields are referenced by their key.
- **Field used** iff `quoted["<key>"] - (number of types declaring that key) > 0` — i.e. the key
  appears somewhere beyond its own declaration(s): an expression, workflow, search, privacy rule,
  etc. Subtracting the declaration count handles keys shared across tables; shared keys are
  therefore conservative (a field is called "used" if *any* table's same-key field is used).
- **Type used** iff exposed_api, OR `"custom.<key>"` appears anywhere, OR any of its fields is
  used, OR it's named in a script, OR it's User.
- **JS/HTML check** (per the "also scripts" requirement): a candidate field/type key that appears
  inside a code/markup string leaf (Run-JavaScript, HTML embed, header) is reclassified as
  "referenced in a script" and kept. Field keys are distinctive enough for a substring match;
  display names are too generic to search reliably (and the Data API concern is already covered by
  `exposed_api`).
- **Report buckets:** unused (no ref, not exposed, not in script) → deletable candidate;
  exposed-via-Data-API (no internal use but table exposed) → verify external consumers; already
  deleted → excluded. **Deleting a type/field destroys its data** — always frame as "confirm no
  data to keep," never a plain "safe to delete."

## Action/type vocabulary (handy when extending)

Navigation: `ChangePage`, `ListGoToPage`, `MobileNavigate`, `RefreshPage`.
Scheduling/triggering: `ScheduleAPIEvent`, `ScheduleAPIEventOnList`, `ScheduleCustom`,
`TriggerCustomEvent`, `TriggerCustomEventFromReusable`, `CancelScheduledAPIEvent`.
Others: `CustomElement` (placed reusable), `APIEvent`/`DatabaseTriggerEvent`/`RecurringEvent`/
`CustomEvent` (workflow kinds), `GetDataFromAPI` (API Connector call), `APIReturnData`.

## Validation anchor

Before and after changing `bubble_audit.py`, run it (`--json`) on the exports of the projects you
are working on and compare the counts per section. A count that moves without a rule change that
explains it is a regression. Keep those runs and their numbers in each project's folder
(`~/UnBubble-Projects/<app-id>/audit/`), never in this repository.
