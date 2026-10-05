# ERPNext-Frepple Integration: Architecture Analysis and v17 Migration Plan

> **Active spec:** [`specs/migrate-v17.md`](./specs/migrate-v17.md) — the operational plan with phase gates, decisions, and acceptance criteria. This file is the architecture reference for the source code we're migrating from.
>
> **Repository (source):** `https://github.com/msf4-0/ERPNext-Frepple-Integration`
> **Repository (target):** `apps/fact_frepple/fact_frepple/` (Frappe v17 scaffold, currently 0 doctypes).
> **frepple target:** `ghcr.io/frepple/frepple-community:9.17.0` + side-car `postgres:16`.
> **Planing bench:** Frappe v17.0.0-dev + ERPNext v17.0.0-dev, Python 3.14, MariaDB. Site `test.localhost` already has all three apps installed.
> **License drift:** source is GPLv3; target is MIT + NOTICE attribution.

---

## 1. What the app does (high level)

A custom Frappe app that lives inside an ERPNext site and acts as a **bidirectional data bridge** between ERPNext and a frepple APS server. The planner keeps using ERPNext as the system of record; frepple runs the constraint-based planning; this app shuttles data back and forth and surfaces frepple screens inside ERPNext via an iframe.

Six user-visible capabilities (per the upstream README):

1. Export data from ERPNext to frepple with a few clicks.
2. Generate the plan in frepple from inside the custom app, with configurable constraints.
3. Import manufacturing orders and purchase orders from frepple into ERPNext.
4. Embed the frepple UI into ERPNext via iframe (`Frepple Custom Page`).
5. Generate work orders and purchase orders in ERPNext from the frepple plan result.
6. Sync work-order / purchase-order / sales-order status between ERPNext and frepple.

---

## 2. Repository layout (source)

```
ERPNext-Frepple-Integration/
├── LICENSE                                 (GPLv3, full text)
├── MANIFEST.in                             (includes templates + public)
├── README.md
├── requirements.txt                        (one line: `frappe`)
├── setup.py                                (Python setuptools, name=frepple)
└── frepple/                                (the actual app)
    ├── __init__.py                         (version = 0.0.1)
    ├── hooks.py                            (FRAPPE STANDARD SCAFFOLD, mostly commented out)
    ├── config/
    │   ├── desktop.py                      (one module tile: Frepple)
    │   ├── docs.py                         (brand_html = "Frepple")
    │   └── frepple.py                      (workspace definition: 9 sections, ~30 items)
    ├── templates/                          (empty `__init__.py`, no templates shipped)
    └── frepple/
        ├── __init__.py                     (empty)
        ├── doctype/                        (29 doctypes)
        │   ├── frepple_buffer/             (item, location, onhand — frepple Buffer model)
        │   ├── frepple_calendar/           (frepple Calendar)
        │   ├── frepple_calendar_bucket/    (working-hours slots inside a calendar)
        │   ├── frepple_calendar_calendar_bucket/  (child table)
        │   ├── frepple_custom_page_settings/      (one row, holds iframe URL + height + secret)
        │   ├── frepple_customer/
        │   ├── frepple_data_export/         (THE main export controller — ~16 KB .py)
        │   ├── frepple_demand/              (sales-order demand in frepple terms)
        │   ├── frepple_integration_data_fetching/  (THE main import controller — ~15 KB .py)
        │   ├── frepple_item/                (link to ERPNext Item)
        │   ├── frepple_item_distribution/   (item-to-location flow rules)
        │   ├── frepple_item_supplier/       (purchasing rules)
        │   ├── frepple_location/            (warehouse / WIP location)
        │   ├── frepple_manufacturing_order/ (frepple MO result, before it becomes a Work Order)
        │   ├── frepple_manufacturing_order_page/  (?)
        │   ├── frepple_operation/           (routing + time-per operations)
        │   ├── frepple_operation_material/
        │   ├── frepple_operation_resource/
        │   ├── frepple_purchase_order/      (frepple PO result)
        │   ├── frepple_resource/            (employee OR workstation)
        │   ├── frepple_resource_skill/
        │   ├── frepple_run_plan/            (the "run the plan" action)
        │   ├── frepple_settings/            (single-row, holds URL, token, user, pass, secret)
        │   ├── frepple_skill/
        │   ├── frepple_supplier/
        │   └── (a few more, depending on the v14 schema)
        └── page/                            (6 desk pages — iframe embeds)
            ├── demand_page/
            ├── frepple_custom_page/         (the iframe loader — uses FreppleCustomPage class)
            ├── frepple_test_page/
            ├── manufacturing_order_page/
            ├── purchase_order_page/
            ├── resource_report_page/
            └── supply_path_page/
```

**194 files** total (verified `git ls-files` against `msf4-0/ERPNext-Frepple-Integration` HEAD `60d2d9f`, 2026-08-10): 108 .py, 42 .js, 37 .json, plus LICENSE / README.md / MANIFEST.in / requirements.txt / setup.py / .gitignore. Earlier draft overcounted at 240; the source has 30 doctype folders (29 in `doctype/` + the controller `frepple_run_plan` and the `_page` DocTypes are inside `doctype/`, not `page/`) and 7 page modules under `page/` (the 6 functional ones — `demand_page`, `frepple_custom_page`, `manufacturing_order_page`, `purchase_order_page`, `resource_report_page`, `supply_path_page` — plus the debug `frepple_test_page` which the spec treats as out-of-scope).

---

## 3. Architecture in plain language

There are four logical layers in the app:

### Layer 1 — Single-row settings (`Frepple Settings`)
One ERPNext DocType, single allowed record. Holds:
- `url` (e.g. `http://192.168.112.1:5000`)
- `username` / `password` (default `admin` / `admin`)
- `authorization_header` (the Bearer web token from frepple's REST API help page)
- `frepple_integration` checkbox (turns on auto status sync)
- `secret_key` (used to render the iframe; **v17 migration: now signs the JWT webtoken, not a URL param**)

### Layer 2 — frepple-shape mirror doctypes
For every entity in frepple's domain model, there is a **frappe DocType that mirrors the frepple object and also `Link`s back to the ERPNext native object**. For example:

- `Frepple Item` has a Link field `item` → ERPNext `Item`, plus `description`, `stock_uom`, `valuation_rate`, `item_group` (used as frepple "owner" of the item).
- `Frepple Customer` mirrors Customer.
- `Frepple Location` mirrors Warehouse, with a `location_owner` field pointing to the parent Company.
- `Frepple Resource` mirrors Employee or Workstation (single DocType, two display variants via `employee_check` / `workstation_check`).
- `Frepple Operation` mirrors BOM + BOM Operation.
- `Frepple Demand` mirrors Sales Order Item.
- `Frepple Buffer` mirrors Bin (item + warehouse + onhand).
- `Frepple Calendar` and `Frepple Calendar Bucket` are the frepple calendar model (not directly mirrored from ERPNext — the user maintains them by hand in this DocType).

These mirror DocTypes exist so the planner has a **familiar ERPNext form to fill in** for data that will be pushed to frepple. They are not the source of truth for items, customers, etc. — `Item` and `Customer` are. The mirror DocType is a *projection* of ERPNext data shaped to match what frepple expects.

### Layer 3 — Two controller doctypes
These do the work. They are the "buttons" the user clicks.

- **`Frepple Data Export`** — a form with checkboxes (one per frepple entity). When the user clicks *Export Data to Frepple*, the Python controller reads the relevant mirror DocType rows (or native ERPNext tables), reshapes each row into the frepple REST API JSON shape, and POSTs to `http://<user>:<pass>@<host>/api/input/<entity>/`. One POST per row.

- **`Frepple Integration Data Fetching`** — the reverse. Reads from the mirror DocTypes, calls frepple to download the plan result (manufacturing orders, purchase orders), and writes the rows back into mirror DocTypes. Also has a `fetch_data` function that pulls *from ERPNext native tables into mirror DocTypes* — i.e. mirrors first, then export next.

There is also a `Frepple Run Plan` DocType (referenced in `config/frepple.py`) that triggers the plan generation on the frepple side.

### Layer 4 — Page iframes
Six desk pages, the most important being `Frepple Custom Page`. This is a `frappe.pages['frepple-custom-page'].on_page_load` that:
- Renders a Link field in the page actions area to pick a `Frepple Custom Page Settings` record.
- On selection, calls `frappe.call` to `get_iframe_url` (in `frepple_custom_page_settings.py`).
- Receives a URL + iframe height, builds `<iframe src=URL>`, and appends it to the page.
- The URL is constructed using the `secret_key` from settings so frepple accepts the cross-origin request.

The other pages are similar iframe wrappers for specific frepple views (demand, manufacturing orders, purchase orders, supply path, resource report).

---

## 4. The export pipeline in detail

File: `frepple/frepple/doctype/frepple_data_export/frepple_data_export.py`

```
export_data(doc)  [frappe.whitelist()]
  reads the checkbox form (a JSON dict)
  for each ticked entity, calls the matching export_*() function
  each export_*() function:
    1. queries `tabFrepple X` (or `tabItem`, `tabBOM`, etc.) via frappe.db.sql
    2. for each row, builds a dict with the frepple-API field names
    3. json.dumps() the dict
    4. POST it to /api/input/<entity>/ via make_post_request()
  prints "X is exported" msgprint for each entity
```

The URL builder (`get_frepple_params`) inlines the username:password into the URL (basic auth) and adds the `Authorization: Bearer …` header. It returns `(url, headers)`.

For each entity, the field mapping is hand-coded. Examples:

| Source table | frepple entity | Key transformations |
|---|---|---|
| `tabFrepple Calendar` | `calendar` | name, defaultvalue |
| `tabFrepple Calendar Bucket` | `calendarbucket` | ISO datetime, weekday booleans as "true"/"false" strings |
| `tabFrepple Item` | `item` | also POSTs the `item_group` first as the frepple item "owner" (Frepple requires referenced objects to exist) |
| `tabFrepple Buffer` | `buffer` | item + location + onhand |
| `tabFrepple Resource` | `resource` | split into human-resource vs workstation branches via `employee_check` flag |
| `tabBOM` + `tabBOM Operation` | `operation` | two passes: one for `type=routing` (the BOM itself), one for `type=time_per` (each BOM op) |
| `tabBOM Item` | `operationmaterial` | operation + item + quantity + type |
| `tabFrepple Operation Resource` | `operationresource` | branches on `employee_check` (sends `resource: "Operator"` placeholder) |
| `tabFrepple Demand` | `demand` | sales order line → frepple demand |
| `tabFrepple Item Supplier` | `itemsupplier` | leadtime encoded as `"N days HH:MM:SS"` string |

A critical detail: **the mirror doctype rows are pre-populated from ERPNext native tables via the "Integration Data Fetching" controller**, then the export reads from the mirror. So the flow is: ERPNext native → fetch → mirror → export → frepple.

---

## 5. The import / fetch pipeline

File: `frepple/frepple/doctype/frepple_integration_data_fetching/frepple_integration_data_fetching.py`

Two separate flows share this file:

1. **`fetch_data(doc)`** — pulls from ERPNext native (`tabItem`, `tabCustomer`, `tabWarehouse`, `tabBin`, `tabEmployee`, `tabWorkstation`, `tabSkill`, `tabBOM`, `tabBOM Operation`, `tabBOM Item`, `tabSupplier`, etc.) into the `Frepple *` mirror DocTypes. Uses `if not frappe.db.exists(...)` to skip existing rows, and `frappe.db.set_value(...)` to update the onhand / cost / proficiency fields on subsequent runs.

2. **`fetch_sales_orders()`** — pulls from frepple into mirror. Calls frepple's REST API with `api="demand"` and an ERPNext-side filter to fetch the plan-result manufacturing orders, then writes them into `Frepple Manufacturing Order` mirror DocType.

The file ends with helper functions for resource_skills, suppliers, demand (sales-order shape), operations, operation_materials, operation_resources, buffers, items, customers, locations.

This is **not symmetric**: the export side is much more polished than the import side, and the import side has hardcoded assumptions (e.g. looks for a `Frepple Location` whose name starts with `"Work In Progress"` to use as the WIP location — **v17 migration: made configurable via `Frepple Settings.wip_location_name`**).

---

## 6. The frepple REST API contract the app assumes

All calls go to:
```
http://<user>:<pass>@<host>:<port>/api/input/<entity>/
```

with `Authorization: Bearer <token>` and JSON body. Used entities:

`calendar`, `calendarbucket`, `item`, `customer`, `location`, `buffer`, `itemdistribution`, `resource`, `skill`, `resourceskill`, `supplier`, `itemsupplier`, `operation`, `operationmaterial`, `operationresource`, `demand`, `manufacturingorder`, `purchaseorder`.

The app **only does POST** (push) to frepple. It does GET to retrieve plan results, but only in a handful of places (`fetch_sales_orders`, `get_frepple_params` accepts a filter for the `demand` endpoint).

It never deletes from frepple. There is no `frepple.delete(...)` call. If you delete a row from the mirror DocType, the corresponding frepple object stays in the frepple DB.

**v17 migration note:** frepple 9.17 supports all the above entities but the auth model for the *plan iframe* has changed. See §7 below.

---

## 7. The custom-page iframe (v14 → v17 contract change)

### v14 (source)

`frepple/frepple/page/frepple_custom_page/frepple_custom_page.js`:

```javascript
frappe.pages['frepple-custom-page'].on_page_load = (wrapper) => {
    const page = frappe.ui.make_app_page({ parent: wrapper, title: 'Frepple Custom Page', single_column: true });
    new FreppleCustomPage(page, wrapper);
};

class FreppleCustomPage {
    init()         { this.createSelectionField(); }
    showIframe()   { this.getSettings().then(r => { /* build <iframe src=URL> and append */ }); }
    getSettings()  { frappe.call({ method: 'frepple.frepple.doctype.frepple_custom_page_settings.frepple_custom_page_settings.get_iframe_url', args: { pageName: this.pageName } }); }
}
```

The matching Python (`frepple_custom_page_settings.py`) reads the `Frepple Custom Page Settings` DocType, looks up the secret_key, and returns a URL of the form `http://<host>/<view>/?embedded=true&secret=<key>`.

### v17 (target) — what changes

frepple 9.x dropped the `?secret=<key>` URL-param approach. Authentication now uses a **JWT webtoken** (HS256, signed with a shared secret configured in frepple's `djangosettings.py` as `SECRET_WEBTOKEN_KEY`). The token carries `{user, exp, navbar}` and is appended as `?webtoken=<jwt>`.

Reference: `https://github.com/frePPLe/frepple/blob/master/doc/integration-guide/embedding.rst`

**Migration fix (F14 in the spec):** rewrite `get_iframe_url()` in `frepple_custom_page_settings.py`:

```python
import jwt
import time

def get_iframe_url(page_name: str) -> tuple[str, int]:
    settings = frappe.get_single("Frepple Settings")
    page = frappe.get_doc("Frepple Custom Page Settings", page_name)

    webtoken = jwt.encode(
        {
            "exp": round(time.time()) + 3600,
            "user": settings.username,
            "navbar": False,
        },
        settings.secret_key,
        algorithm="HS256",
    )

    url = f"{settings.url.rstrip('/')}/{page.view_name}/?webtoken={webtoken}"
    return url, page.iframe_height or 800
```

`pyjwt` must be a dependency (add to `pyproject.toml`).

The page JS itself still works in v17 — the `frappe.pages['x'].on_page_load` pattern is preserved (verified at `frappe/public/js/frappe/views/pageview.js:130`).

---

## 8. What v17 changes that will break this code (revised for v17)

**Status (2026-08-10, post-Phase 4):** all B-items and soft issues below are
resolved on `feat/migrate-v17`. Verified by inspection of the migrated tree:
0 files still carry `"module": "Frepple"`, 0 `.py` files still import
`get_request_session` or `from __future__ import unicode_literals`, and all
29 DocType JSONs carry `sort_field`/`sort_order`. The **Fix** column is the
fix that was applied, not a proposal.

| # | What breaks in v17 | Where in this app | Fix |
|---|---|---|---|
| B1 | `from frappe.utils import get_request_session` is removed (since v15). | `data_export.py` and any helper that touches it | Drop the import; use `frappe.integrations.utils.make_get_request` |
| B2 | `frappe.db.set_value()` no longer auto-commits. | `data_fetching.py` lines 96, 142, 211, 274 | Add `frappe.db.commit()` after each `set_value` block, or use `doc.db_set(...)` |
| B3 | Vue 2 → Vue 3, Webpack → Vite. | All 42 .js files | Source JS uses `frappe.call(...)` and `frappe.ui.form.make_control(...)` — still works in v17. Audit each file for Vue components / Options API |
| B4 | List-view default sort changed from `modified` to `creation`. | All 29 DocType JSONs | Add `"sort_field": "creation"` and `"sort_order": "asc"` to each JSON |
| B5 | Type annotations mandatory on whitelisted methods (scaffold has `require_type_annotated_api_methods = True`). | ~20 whitelisted methods in the migrated controllers | Annotate every whitelisted method (parameters + return type) |
| B6 | `frappe.pages['x'].on_page_load = (wrapper) => {...}` and `frappe.ui.make_app_page(...)` — still works in v17. | `frepple_custom_page.js` | **No rewrite** — verified at `frappe/public/js/frappe/views/pageview.js:130` |
| B7 | `frappe.integrations.utils.make_post_request` — **still exists** in v17. | `data_export.py` | **No change required** (verified at `frappe/integrations/utils.py:90`). The original import is correct. |
| B8 | Module path in DocType JSONs. | All 29 JSONs | Rewrite `"module": "Frepple"` → `"module": "Fact Frepple"` |
| B9 | **frepple 9.x JWT webtoken auth** (not v14's `?secret=<key>`). | `frepple_custom_page_settings.py.get_iframe_url` | See §7 above. Rewrite with `pyjwt`. |
| B10 | `frappe.whitelist()` defaults now include GET/POST/PUT/DELETE/QUERY in v17 (`frappe/__init__.py:591`). | n/a | No change required — v14's bare `@frappe.whitelist()` is still permissive |
| B11 | Hard-coded WIP location lookup (`name LIKE 'Work In Progress%'`). | `data_fetching.py` | Make configurable: add `wip_location_name` field to `Frepple Settings` |

### Soft issues (work but with warnings)

| # | What | Where | Fix |
|---|---|---|---|
| S1 | `from __future__ import unicode_literals` (Python 2 relic). | All .py files | Removed |
| S2 | `print(...)` statements (ad-hoc logging). | Both controllers | Replaced with `frappe.logger().info(...)` |
| S3 | `app_license = "MIT"` in scaffold but source is GPLv3. | repo license | Scaffold stays MIT; `NOTICE` credits msf4-0 and flags the GPLv3 chain |
| S4 | No `patches.txt` / migration patches in source. | repository root | `patches.txt` scaffolded; no v14→v17 field renames needed a patch (greenfield site) |
| S5 | Test stubs. | `test_*.py` | Replaced with real tests in Phase 4 (37 tests) |
| S6 | No CI. | repository root | `ci.yml` runs bench tests; `linter.yml` runs ruff + prettier + pip-audit |

### Bugs found during migration (not predicted by this analysis)

These surfaced only because Phase 4 replaced the stubs with real tests — they
are the concrete return on that phase:

| # | Bug | Fixed in |
|---|---|---|
| M1 | `fetch_items` wrote `uom`/`cost`/`item_owner`, which don't exist on the v17 `Frepple Item` DocType | `a399e2d` — renamed to `stock_uom`/`valuation_rate`/`item_group` |
| M2 | `get_iframe_url` passed `doc.expiration` (minutes) where `sign_jwt_url` expects seconds | `a399e2d` — multiplied by 60 |
| M3 | `UnitTestCase` has no implicit rollback, so the second fetch silently took the update branch | `6be757c` — mirror DocTypes scrubbed in `setUp` |
| M4 | `sign_jwt_url` used `round(time.time())`, putting `exp` a second past a truncated-clock upper bound (failed 7/12 runs) | `246b327` — truncate with `int()` |
| M5 | `run_plan` POSTed to `/api/runplan/`, which 302s to the login page — no plan ever ran. Phase 3 changed the correct v14 path and the Phase 4 mock asserted the wrong URL | Phase 6 — restored `/execute/api/runplan/` |
| M6 | `fetch_data` called `fetch_item_suppliers()`, never ported from v14 → `NameError` | Phase 6 — implemented |
| M7 | `fetch_skills`/`fetch_resource_skills` query hrms-only tables → `ProgrammingError` without hrms | Phase 6 — table-existence guard |
| M8 | frepple 9.x rejects an `itemsupplier` without `effective_start` (HTTP 400) | Phase 6 — send an anchor date |
| M9 | frepple's `"Unknown supplier"` placeholder aborted the whole PO import via `LinkValidationError` | Phase 6 — skip and log |
| M10 | Phase 4 unit tests leave fakes in the `Frepple Settings` singleton, breaking any later test that needs real credentials | Phase 6 — E2E config from `site_config.json` |

### Non-issues (verified against v17 source)

- `from frappe.integrations.utils import make_post_request` — **still works** in v17.
- `frappe.pages['x'].on_page_load = (wrapper) => {...}` — **still works** in v17.
- List-view JSON keys beyond `sort_field`/`sort_order` — JSONs are loaded unchanged.
- `frappe.db.sql(...)` — same API.
- `from __future__ import unicode_literals` — harmless (Python ignores it).
- SQL `timestamp()` — works on MariaDB; we're on MariaDB per `site_config.json`.

---

## 9. Migration plan (active spec lives in `specs/migrate-v17.md`)

This section is a **summary** — for the full phase plan with decision rationale, per-phase acceptance gates, and risks, see [`specs/migrate-v17.md`](./specs/migrate-v17.md). Per-phase completion notes live there; Phases 0–6 are done. Phase 7 carries the §6.5 status-sync round-trip.

### Phase 0 — Repository & source prep (~½ day)
Clone source to `/tmp/opencode/erpnext_frepple_connector/`; create `feat/migrate-v17` branch off `dev`.

### Phase 0.5 — Install frepple (Docker) (~½ day)
Stand up `ghcr.io/frepple/frepple-community:9.17.0` + `postgres:16` side-car via `docker/frepple.compose.yaml`. Configure JWT signing secret in frepple's `djangosettings.py`. Validate via `curl http://localhost:9000/` and a manual JWT round-trip.

### Phase 1 — Tracer bullet: Settings + Custom Page (~2-3 days)
Migrate `frepple_settings`, `frepple_custom_page_settings`, `frepple_custom_page` (5 files). Apply F1–F14. Verify iframe loads with a valid JWT.

### Phase 2 — Bulk mirror DocType copy (~3-4 days)
Migrate the remaining 27 DocTypes + 2 controllers. Apply F1–F14 mechanically. Audit ERPNext v17 field names. Make WIP location configurable.

### Phase 3 — Desk pages and Frepple Run Plan (~1 day)
Migrate 5 remaining iframe pages + `Frepple Run Plan` DocType + workspace config. All iframe pages call the same `get_iframe_url(view_name)` helper.

### Phase 4 — Tests, CI, deployment (~2-3 days)
Replace stub tests with real ones (`responses` lib + `unittest`). Add CI step for `bench run-tests`. Add `NOTICE` file.

### Phase 5 — Spec reconciliation + handoff (~½ day)
This document is updated (§8, §12, §13). PR `feat/migrate-v17 → dev`.

### Phase 6 — End-to-end two-way transfer test (~2 days)
Stand up ERPNext fixtures (1 SO → 1 WO + 1 PO). Run the full export → plan → fetch round-trip against the real frepple container from Phase 0.5. Validate the WO and PO land in ERPNext with correct quantities. **Done** — `bench fact-frepple-e2e`, green from a cold start; found six bugs the mocks could not (M5–M10).

**Total:** 11-15 working days.

---

## 10. Risks and unknowns

Outcome column added at Phase 5. Risks 2, 9 and 10 remain open because only
Phase 6 exercises a real frepple container.

| # | Risk | Mitigation | Outcome |
|---|---|---|---|
| 1 | msf4-0 repo deleted or significantly evolved | Phase 0 step 1 fails fast. Backup: ask user for internal fork | Closed — cloned fine, attributed in `NOTICE` |
| 2 | frepple 9.17 REST API contract differs from 2022 source code | Phase 6 E2E catches it (real frepple, not mocks) | **Closed — and it did**: wrong runplan endpoint (M5), required `effective_start` (M8), `"Unknown supplier"` placeholder (M9) |
| 3 | v14 user data on existing customer sites | Greenfield on `test.localhost`. Forward-compatible `patches.txt` | Closed — no patch needed |
| 4 | ERPNext v17 field renames (`Item.valuation_rate`, `Bin.actual_qty`, `BOM.time_in_mins`, `Workstation`) | Audit per field mapping in Phase 2 | Closed — but the audit missed three aliases; Phase 4 tests caught them (M1) |
| 5 | Type-annotation overhead for the ~108 .py files | Only annotate the ~20 whitelisted methods | Closed — no friction |
| 6 | License drift (MIT app next to GPLv3 ERPNext) | Framework is MIT; connector license independent. Documented in `NOTICE` | Closed |
| 7 | Hard-coded WIP location convention | Made configurable via `Frepple Settings.wip_location_name` | Closed |
| 8 | The `frepple_integration` flag auto-syncs status — could fire in unexpected orders | Out of scope for migration; Phase 7 hardening item | Deferred to Phase 7 (with §6.5 status sync) |
| 9 | JWT secret drift between Frepple Settings and frepple container | Phase 0.5.3 stores both; Phase 6.2 asserts they match | Closed — E2E asserts the real frepple returns 200 for our token and rejects a wrong-secret one |
| 10 | `frame-ancestors` CSP blocking the iframe | Phase 0.5.1 compose sets `FREPPLE_CONTENT_SECURITY_POLICY` and `FREPPLE_X_FRAME_OPTIONS` | Closed — asserted against the live response header |
| 11 | Postgres container disk fills up over many plan runs | Named volume `frepple-pgdata`; `make reset` wipes | Closed |
| 12 | **`plan.webservice=true` (frepple default) keeps the plan in memory, so the connector imports nothing and reports no error** | Discovered in Phase 6; `make configure-plan` sets it to `false`, required after every `make reset` | Open as an operational footgun — no env var exists for it |

---

## 11. What is out of scope (deferred)

- **Replacing the connector with a different approach** (e.g. reading directly from SAP). Much bigger project.
- **Adding new frepple entities** (setup-matrix optimization, sequenced manufacturing, etc.). Feature project, not migration.
- **Refactoring the mirror-DocType pattern into native ERPNext fields.** Possible follow-up, but the mirror is the integration contract; do not refactor before the migration works.
- **Production deployment.** Sandbox only on `test.localhost`.
- **Enterprise Edition features.**
- **i18n of UI strings** (English-only).

---

## 12. Estimated effort

Phases 0–6 are complete on `dev`; the table below carries the
original estimate next to what the phase actually cost.

| Phase | Estimate | Actual | Status | Note |
|---|---|---|---|---|
| 0 — Repository setup | 0.5 day | 0.5 day | done | One git clone |
| **0.5 — frepple Docker install** | **0.5 day** | **0.5 day** | **done** | **Enabled real testing** |
| 1 — Tracer bullet (Settings + iframe) | 2-3 days | ~1 day | done | Tracer bullet paid off — B6/B7 turned out to be non-issues |
| 2 — Bulk doctype copy | 3-4 days | ~1 day | done | Scripted via `scripts/migrate_phase2.sh`, not hand-edited |
| 3 — Desk pages | 1 day | ~0.5 day | done | Reuses the shared `sign_jwt_url` helper |
| 4 — Tests + CI + docs | 2-3 days | ~1.5 days | done | Real tests caught 3 real bugs (M1–M3) |
| 5 — Spec + handoff | 0.5 day | ~0.5 day | done | This document update; caught M4 |
| **6 — E2E two-way test** | **2 days** | **~1 day** | **done** | **Real frepple + real bench; found M5–M10** |
| **Total** | **11-15 days** | **~6.5 days** | | Estimates were conservative; scripting Phase 2 was the big saving |

The two compression shortcuts floated before Phase 4 (skip unit tests for
E2E-covered entities; mock Phase 6 instead of running real frepple) both look
like bad trades in hindsight — the Phase 4 unit tests found four bugs that an
E2E happy path would not have isolated, and Phase 6 against the *real*
container found six more that no mock could have caught. Mocking Phase 6, the
shortcut explicitly labelled "not recommended", would have shipped a connector
whose plan endpoint silently did nothing.

---

## 13. File inventory — as shipped (Phases 0–6)

This is the state of `dev` at the end of Phase 6, not a to-do
list. 111 `.py` files, 36 `.js`, 36 `.json` (excluding `__pycache__`).

```
fact_frepple/
  hooks.py                             scaffold; unchanged
  patches.txt                          scaffolded, no v14→v17 patches needed
  config/
    desktop.py  docs.py  frepple.py    module refs Frepple → Fact Frepple
  fact_frepple/
    doctype/                           29 DocTypes, each with a real test_*.py
      frepple_settings/                + wip_location_name field (B11)
      frepple_custom_page_settings/    get_iframe_url → JWT (B9/F14)
      frepple_data_export/             export_<entity>() — responses-tested
      frepple_integration_data_fetching/  fetch_* — SQL-router-tested
      frepple_run_plan/                POSTs /api/runplan/ (was /execute/api/runplan/)
      <24 mirror DocTypes>             sort_field + sort_order + module ref
    page/
      _iframe.py                       shared sign_jwt_url helper (F14)
      test_iframe_helper.py            4 tests incl. deterministic exp clock test
      frepple_custom_page/             Phase 1
      demand_page/  manufacturing_order_page/
      purchase_order_page/  resource_report_page/
      supply_path_page/                Phase 3 — all delegate to _iframe
    workspace/fact_frepple/
      fact_frepple.json                v17 Workspace JSON, 10 sections

Repo root:
  specs/migrate-v17.md                 the operational spec
  ANALYSIS_AND_MIGRATION_PLAN.md       this document
  docker/                              frepple.compose.yaml + Makefile + README
  scripts/migrate_phase2.sh            idempotent Phase 2 copy + transform
  .github/workflows/ci.yml             bench run-tests
  .github/workflows/linter.yml         ruff + prettier + pip-audit
  NOTICE                               msf4-0 attribution + GPLv3 chain
  pyproject.toml                       + responses~=0.25.0

Still to come (Phase 7):
  §6.5 status-sync round-trip (WO submit → frepple PATCH;
       frepple PO receipt → ERPNext Purchase Receipt)
```

Added by Phase 6:

```
  fact_frepple/tests/e2e/
    fixtures.py                        ERPNext fixture builder (idempotent)
    helpers.py                         config, reset, frepple purge
    test_e2e_two_way.py                9 tests: transfer, failure modes, iframe
  fact_frepple/commands/__init__.py    bench fact-frepple-e2e
  docker/Makefile                      + configure-plan (plan.webservice=false)
```

---

## 14. References

- **Active spec:** [`specs/migrate-v17.md`](./specs/migrate-v17.md)
- Source repository: https://github.com/msf4-0/ERPNext-Frepple-Integration
- frepple repository: https://github.com/frePPLe/frepple
- frepple docs (community): https://frepple.com (the frepple.org domain is hijacked; use frepple.com)
- frepple REST API: https://github.com/frePPLe/frepple/blob/master/doc/integration-guide/rest-api/
- frepple embedding (JWT webtoken): https://github.com/frePPLe/frepple/blob/master/doc/integration-guide/embedding.rst
- frepple Docker install: https://github.com/frePPLe/frepple/blob/master/doc/installation-guide/docker-container.rst
- frepple ERPNext connector note (upstream endorsement): https://github.com/frePPLe/frepple/blob/master/doc/erp-integration/erpnext-connector.rst
- Frappe v17 migration wiki: https://github.com/frappe/frappe/wiki/Migrating-to-version-17
- Frappe deprecations wiki: https://github.com/frappe/frappe/wiki/Deprecations
- ERPNext v17 release notes: https://frappe.io/releases/version-17
