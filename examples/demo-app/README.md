# Demo app: Tidewater Rentals (fictional)

A small, made-up Bubble export of an equipment-rental app, built so you can try the whole pipeline
without an export of your own. Nothing here comes from a real app: every name, id, key and value is
invented. The export is planted so that every section of the audit has something in use and something
dead.

## Try it

```bash
# audit → HTML report you can open in a browser
python3 skills/audit/scripts/bubble_audit.py examples/demo-app/tidewater-rentals.bubble --lang en \
        --plugin-names examples/demo-app/plugin-names.json --plugin-pricing examples/demo-app/plugin-pricing.json \
        --out /tmp/tidewater-report.html

# or open the reports already generated
open examples/demo-app/projects/tidewater-rentals/audit/tidewater-rentals-v1_unused_report_EN.html
```

The console can show the demo instead of your projects:

```bash
cd ui && UNBUBBLE_PROJECTS_DIR=../examples/demo-app/projects UNBUBBLE_MCP_HOME=/tmp/unbubble-demo-mcp \
        BEFREE_BUBBLE_MCP_CONFIG_DIR=/tmp/unbubble-demo-befree npm run dev
```

`UNBUBBLE_MCP_HOME` and `BEFREE_BUBBLE_MCP_CONFIG_DIR` point the setup page at empty folders, so it
lists neither the Bubble profiles of your own connected-mode install nor the browser profiles of an
earlier befree-bubble-mcp install. Use this mode for screenshots and live demos.

## What the audit finds

| Section | In use | Dead (planted) |
|---|---|---|
| Pages | `index`, `dashboard`, `booking`; `oauth_return` is reached only by URL and kept | `promo_2023_old`, `admin_legacy` |
| Reusable elements | `Header`, `BookingCard` | `OldFooter`; `PromoBanner`, placed only inside `OldFooter`; a second `Header` with the same name, flagged to verify |
| Backend workflows | `send_reminder` (scheduled from a page), `update_availability` (scheduled by a database trigger), `public_quote` (exposed) | `sync_inventory_v1`; `archive_old_orders`, scheduled only by the dead one; `payment_webhook` goes to "verify", because a webhook's caller is outside the app |
| Option sets | `booking_status` | `legacy_tier` |
| Plugins | API Connector, Calendar Pro (demo); SMS Gateway (demo) is configured with no element | PDF Maker (demo), flagged as an unused paid plugin |
| Styles and design tokens | `Button Primary`, `Text Muted`, the `Brand` color, the `Body` font | `Legacy Banner`, `Legacy Accent`, `Old Display` |
| Data | `Rental order`, `Equipment unit` and their used fields; `Activity log` is exposed in the Data API, flagged to verify | the `Legacy invoice` table; the `Amount` and `Internal memo` fields |
| Workflows | `recalc_totals` | the `legacy_refresh` and `recompute_rates` custom events, never triggered; a trigger on a deleted element; a trigger on a button inside a group that never shows |
| API Connector | `Get forecast` (workflow action), `Get holidays` (data source only) | `Get alerts`; `Trigger reminder`, a call to the app's own workflow API |
| Removed-plugin references | | a chart element of Chart Studio (demo), a plugin no longer installed |

The clone step's `inventory/summary.json` also flags `public_quote` as an endpoint without
authentication that ignores privacy rules.

## Files

| File | What it is |
|---|---|
| `make_demo_export.py` | writes `tidewater-rentals.bubble`; read it to see how each case is planted |
| `tidewater-rentals.bubble` | the export |
| `plugin-names.json`, `plugin-pricing.json` | names and a made-up price for the fictional plugin ids, passed to the scripts |
| `build_demo.py` | rebuilds the export and every output below with the real scripts |
| `projects/tidewater-rentals/` | the outputs, in the project-folder layout the console reads: audit reports (EN and PT) and JSON, `inventory/`, `secrets/ENV-KEYS.md` and `.env.example` |

`build_demo.py` also writes `secrets/.env`. It is gitignored like every `.env` UnBubble writes, and its
values are fake. Rebuild everything with `python3 examples/demo-app/build_demo.py`.
