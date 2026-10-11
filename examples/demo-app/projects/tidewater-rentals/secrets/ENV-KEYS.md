# ENV keys extracted from the Bubble export

App: **?** · source: `tidewater-rentals.bubble` · 3 variables. Values live ONLY in `secrets/.env` (chmod 600, gitignored) — this file and `.env.example` carry names, not values.

**For the rebuild agent:** configure each var in the new system's secret store / `.env` as mapped by the level-up pack (integration map + TARGET-ARCHITECTURE). `test` rows are Bubble *test-version* values; `in use = no` rows belong to providers/plugins the app never invokes (candidates to drop, confirm with the owner). Rotate anything that may have leaked before go-live.

## API Connector (settings.secure mirror — private auth & params)

| Var | Source (export path) | Context | test | len | in use |
|---|---|---|---|---|---|
| `API_WEATHER_SERVICE_DEMO_PRIVATE_KEY` | `settings.secure.apiconnector2.apiWx.private_key` | provider "Weather Service (demo)" · private_key |  | 25 | yes |

## Plugin secure keys (settings.secure)

| Var | Source (export path) | Context | test | len | in use |
|---|---|---|---|---|---|
| `PLUGIN_SMS_GATEWAY_DEMO_APIKEY` | `settings.secure.1600000000004x400000000000000004_apikey` | plugin "SMS Gateway (demo)" (1600000000004x400000000000000004) |  | 21 | no |

## Bubble internal (not reusable outside Bubble — kept for completeness)

| Var | Source (export path) | Context | test | len | in use |
|---|---|---|---|---|---|
| `API_TOKENS` | `settings.secure.api_tokens` | settings.secure.api_tokens (unrecognized structure) |  | 70 | — |

