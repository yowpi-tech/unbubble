#!/usr/bin/env python3
"""Write the .bubble export of Tidewater Rentals, a FICTIONAL equipment-rental app.

Nothing here comes from a real app: every name, id, key and value is made up. The export is small
on purpose and planted so that every section of the audit has something in use and something dead,
including the cases UnBubble is careful about (a reusable placed only inside a dead one, a same-name
twin, a webhook, an exposed endpoint without auth, an unused paid plugin, a removed plugin still
referenced, an API call used only as a data source).

    python3 examples/demo-app/make_demo_export.py            # writes tidewater-rentals.bubble next to it

stdlib only, Python 3.8+.
"""
import json
import os

APP = 'tidewater-rentals'
CAL = '1600000000001x100000000000000001'    # Calendar Pro (demo)  - installed, placed
PDF = '1600000000002x200000000000000002'    # PDF Maker (demo)     - installed, unused, "paid"
CHART = '1600000000003x300000000000000003'  # Chart Studio (demo)  - uninstalled, still referenced
SMS = '1600000000004x400000000000000004'    # SMS Gateway (demo)   - installed, configured, no element


def text(caption):
    """A static TextExpression, the way the editor stores a caption."""
    return {'entries': {'0': caption}}


def button(eid, letter, caption, **extra):
    el = {'id': eid, 'type': 'Button', 'default_name': 'Button ' + letter,
          'properties': {'text': text(caption)}}
    el.update(extra)
    return el


def page(pid, name, elements=None, workflows=None):
    return {'id': pid, 'name': name, 'type': 'Page', 'properties': {'title': name},
            'elements': elements or {}, 'workflows': workflows or {}}


def clicked(wid, element_id, actions=None):
    return {'id': wid, 'type': 'ButtonClicked', 'properties': {'element_id': element_id},
            'actions': actions or {}}


def build():
    pages = {
        'pw_index': page('pIdx01', 'index', elements={
            'e1': {'id': 'eHdr01', 'type': 'CustomElement', 'default_name': 'Header A',
                   'properties': {'custom_id': 'dHdr01'}},
            'e2': button('eBtn01', 'A', 'Book equipment', style='sBtnPri'),
            'e3': {'id': 'eTxt01', 'type': 'Text', 'default_name': 'Text A',
                   'properties': {'text': text('Rent tools by the day'),
                                  'font_color': 'var(--color_tkBrand_default)',
                                  'font_family': 'var(--font_fnBody_default)'}},
            # a group that never shows: the button inside it can never be clicked
            'e4': {'id': 'eGrp09', 'type': 'Group', 'default_name': 'Group B',
                   'properties': {'is_visible': False},
                   'elements': {'e41': button('eBtn09', 'B', 'Claim spring discount')}},
            'e5': {'id': 'ePlg01', 'type': CAL + '-CalendarPicker', 'default_name': 'CalendarPicker A',
                   'properties': {}},
            # element of a plugin that is no longer installed
            'e6': {'id': 'ePlg02', 'type': CHART + '-LineChart', 'default_name': 'LineChart A',
                   'properties': {}},
        }, workflows={
            'w1': clicked('wIdx01', 'eBtn01', actions={
                '0': {'type': 'ChangePage', 'properties': {'element_id': 'pBook01'}},
                '1': {'type': 'ScheduleAPIEvent', 'properties': {'api_event': 'aRem01'}},
                '2': {'type': 'TriggerCustomEvent', 'properties': {'custom_event': 'wCe01'}},
            }),
            'w2': clicked('wIdx02', 'eBtn09'),          # never rendered
            'w3': clicked('wIdx03', 'eGone77'),         # trigger element was deleted
            'w4': {'id': 'wCe01', 'type': 'CustomEvent', 'properties': {'event_name': 'recalc_totals'},
                   'actions': {}},
            'w5': {'id': 'wCe02', 'type': 'CustomEvent', 'properties': {'event_name': 'legacy_refresh'},
                   'actions': {}},
        }),
        'pw_dash': page('pDash01', 'dashboard', elements={
            'e1': {'id': 'eHdr02', 'type': 'CustomElement', 'default_name': 'Header A',
                   'properties': {'custom_id': 'dHdr01'}},
            # the OAuth return page is reached by URL only
            'e2': {'id': 'eLnk02', 'type': 'Link', 'default_name': 'Link B',
                   'properties': {'text': text('Connect calendar'),
                                  'url': 'https://' + APP + '.bubbleapps.io/version-live/oauth_return'}},
            # an API Connector call used only as a data source
            'e3': {'id': 'eRg01', 'type': 'RepeatingGroup', 'default_name': 'RepeatingGroup A',
                   'properties': {'data_source': {'type': 'GetDataFromAPI',
                                                  'provider': 'apiconnector2.apiWx.cHol01'}}},
            'e4': {'id': 'eTxt02', 'type': 'Text', 'default_name': 'Text B',
                   'properties': {'text': {'entries': {'0': 'Hello '},
                                           'expr': {'field': 'full_name_text'}}}},
        }, workflows={
            # an API Connector call used as a workflow action
            'w1': {'id': 'wDash01', 'type': 'PageLoaded', 'properties': {},
                   'actions': {'0': {'type': 'apiconnector2-apiWx.cFc01', 'properties': {}}}},
        }),
        'pw_book': page('pBook01', 'booking', elements={
            'e1': {'id': 'eBkc01', 'type': 'CustomElement', 'default_name': 'BookingCard A',
                   'properties': {'custom_id': 'dBkc01'}},
            'e2': {'id': 'eDd01', 'type': 'Dropdown', 'default_name': 'Dropdown A',
                   'properties': {'placeholder': 'Status', 'option_set': 'option.booking_status',
                                  'data_source': {'type': 'Search', 'search_type': 'custom.rental_order',
                                                  'field': 'status_option_booking_status'}}},
        }),
        'pw_promo': page('pPromo23', 'promo_2023_old'),
        'pw_admin': page('pAdm01', 'admin_legacy', elements={
            'e1': button('eBtn20', 'A', 'Export legacy invoices', style='sBtnPri'),
        }),
        'pw_oauth': page('pOauth01', 'oauth_return'),
        'pw_404': page('p404', '404'),
    }

    element_definitions = {
        'dw_hdr': {'id': 'dHdr01', 'name': 'Header', 'elements': {
            'e1': {'id': 'eLnk01', 'type': 'Link', 'default_name': 'Link A',
                   'properties': {'page': 'pDash01', 'text': text('My bookings')}},
        }, 'workflows': {}},
        # a leftover copy with the exact same name, placed nowhere
        'dw_hdr_copy': {'id': 'dHdr02', 'name': 'Header', 'elements': {}, 'workflows': {}},
        'dw_bkc': {'id': 'dBkc01', 'name': 'BookingCard', 'elements': {
            'e1': {'id': 'eTxt10', 'type': 'Text', 'default_name': 'Text A',
                   'properties': {'text': text('Equipment'), 'expr': {'field': 'name_text'},
                                  'source': 'custom.equipment_unit',
                                  'via': {'field': 'equipment_custom_equipment_unit'}}},
        }, 'workflows': {}},
        'dw_foot': {'id': 'dFoot01', 'name': 'OldFooter', 'elements': {
            'e1': {'id': 'ePrm01', 'type': 'CustomElement', 'default_name': 'PromoBanner A',
                   'properties': {'custom_id': 'dPrm01'}},
        }, 'workflows': {}},
        # placed only inside OldFooter, which is placed nowhere: transitively dead
        'dw_prm': {'id': 'dPrm01', 'name': 'PromoBanner', 'elements': {}, 'workflows': {}},
    }

    api = {
        'aw_rem': {'id': 'aRem01', 'type': 'APIEvent',
                   'properties': {'wf_name': 'send_reminder', 'expose': False, 'wf_folder': 'fOps'},
                   'actions': {}},
        'aw_sync': {'id': 'aSync01', 'type': 'APIEvent',
                    'properties': {'wf_name': 'sync_inventory_v1', 'expose': False, 'wf_folder': 'fOps'},
                    'actions': {'0': {'type': 'ScheduleAPIEvent', 'properties': {'api_event': 'aArch01'}}}},
        # scheduled only by the dead sync_inventory_v1: transitively dead
        'aw_arch': {'id': 'aArch01', 'type': 'APIEvent',
                    'properties': {'wf_name': 'archive_old_orders', 'expose': False}, 'actions': {}},
        # webhook signature: "Detect request data" plus the captured sample payload
        'aw_pay': {'id': 'aPay01', 'type': 'APIEvent',
                   'properties': {'wf_name': 'payment_webhook', 'expose': False, 'parameter_def': 'auto',
                                  'raw_data': '{"event": "demo.payment", "amount": 100}'},
                   'actions': {}},
        # no "expose" key means exposed; also callable without auth and ignoring privacy rules
        'aw_quote': {'id': 'aQuote01', 'type': 'APIEvent',
                     'properties': {'wf_name': 'public_quote', 'auth_unecessary': True,
                                    'ignore_privacy_rules': True,
                                    'parameters': {'0': {'key': 'days', 'value': 'number'}}},
                     'actions': {}},
        'aw_avail': {'id': 'aAvail01', 'type': 'APIEvent',
                     'properties': {'wf_name': 'update_availability', 'expose': False}, 'actions': {}},
        'aw_trig': {'id': 'aTrig01', 'type': 'DatabaseTriggerEvent',
                    'properties': {'wf_name': 'on_order_change', 'trigger_type': 'custom.rental_order'},
                    'actions': {'0': {'type': 'ScheduleAPIEvent', 'properties': {'api_event': 'aAvail01'}}}},
        'aw_night': {'id': 'aNight01', 'type': 'RecurringEvent',
                     'properties': {'wf_name': 'nightly_cleanup'}, 'actions': {}},
        'aw_ce': {'id': 'aCe01', 'type': 'CustomEvent',
                  'properties': {'event_name': 'recompute_rates'}, 'actions': {}},
    }

    option_sets = {
        'booking_status': {'display': 'Booking status', 'values': {
            'v1': {'display': 'Reserved', 'db_value': 'reserved', 'sort_factor': 1},
            'v2': {'display': 'Returned', 'db_value': 'returned', 'sort_factor': 2}}},
        'legacy_tier': {'display': 'Legacy tier', 'values': {
            'v1': {'display': 'Gold', 'db_value': 'gold', 'sort_factor': 1}}},
    }

    styles = {
        'sBtnPri': {'id': 'sBtnPri', 'display': 'Button Primary', 'type': 'Button'},
        'sTxtMuted': {'id': 'sTxtMuted', 'display': 'Text Muted', 'type': 'Text'},
        'sLegacyBan': {'id': 'sLegacyBan', 'display': 'Legacy Banner', 'type': 'Group'},
    }

    user_types = {
        'user': {'display': 'User', 'fields': {
            'full_name_text': {'display': 'Full name', 'value': 'text'}}},
        'rental_order': {'display': 'Rental order', 'fields': {
            'status_option_booking_status': {'display': 'Status', 'value': 'option.booking_status'},
            'equipment_custom_equipment_unit': {'display': 'Equipment', 'value': 'custom.equipment_unit'},
            'internal_memo_text': {'display': 'Internal memo', 'value': 'text'}}},
        'equipment_unit': {'display': 'Equipment unit', 'fields': {
            'name_text': {'display': 'Name', 'value': 'text'}}},
        'legacy_invoice': {'display': 'Legacy invoice', 'fields': {
            'amount_number': {'display': 'Amount', 'value': 'number'}}},
        # exposed in the Data API but referenced nowhere inside the app
        'activity_log': {'display': 'Activity log', 'exposed_api': True, 'fields': {
            'event_text': {'display': 'Event', 'value': 'text'}}},
    }

    client_safe = {
        'plugins': {'apiconnector2': '1.0.0', CAL: '2.4.0', PDF: '1.3.0', SMS: '1.0.1'},
        'default_styles': {'Text': 'sTxtMuted'},
        'api_wf_folder_list': {'fOps': 'Operations'},
        'exposes_wf_api': True,
        'color_tokens_user': {'default': {
            'tkBrand': {'name': 'Brand', 'rgba': 'rgba(32,96,160,1)', 'order': 1},
            'tkLegacy': {'name': 'Legacy Accent', 'rgba': 'rgba(200,120,40,1)', 'order': 2}}},
        'font_tokens_user': {'default': {
            'fnBody': {'name': 'Body', 'font_family': 'Inter', 'order': 1},
            'fnDisplay': {'name': 'Old Display', 'font_family': 'Lobster', 'order': 2}}},
        'apiconnector2': {
            'apiWx': {'human': 'Weather Service (demo)', 'calls': {
                'cFc01': {'name': 'Get forecast', 'url': 'https://api.example.com/forecast', 'method': 'get'},
                'cHol01': {'name': 'Get holidays', 'url': 'https://api.example.com/holidays', 'method': 'get'},
                'cAl01': {'name': 'Get alerts', 'url': 'https://api.example.com/alerts', 'method': 'get'}}},
            # the app calling its own Workflow API, never invoked
            'apiSelf': {'human': 'Tidewater API (self)', 'calls': {
                'cSelf01': {'name': 'Trigger reminder', 'method': 'post',
                            'url': 'https://' + APP + '.bubbleapps.io/version-live/api/1.1/wf/send_reminder'}}},
        },
    }

    # Obviously fake values in no real key format, only to show what bubble_secrets.py preserves.
    secure = {
        'apiconnector2': {'apiWx': {'private_key': 'demo-weather-key-not-real'}},
        SMS + '_apikey': 'demo-sms-key-not-real',
        'api_tokens': [{'name': 'Reporting', 'private_key': 'demo-data-api-token-not-real'}],
    }

    return {'_id': APP, 'pages': pages, 'element_definitions': element_definitions, 'api': api,
            'option_sets': option_sets, 'styles': styles, 'user_types': user_types,
            'mobile_views': {}, 'settings': {'client_safe': client_safe, 'secure': secure}}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), APP + '.bubble')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(build(), f, indent=1, sort_keys=True)
        f.write('\n')
    print('wrote', os.path.relpath(out))


if __name__ == '__main__':
    main()
