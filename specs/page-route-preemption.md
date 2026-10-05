# Desk Page vs singleton DocType — slug-collision fix

> **Status:** Reconciled 2026-08-13. The shim-and-table approach was the original
> fix; it has since been replaced by renaming the colliding singletons. See
> "Resolution — rename the singletons" below for what superseded this design.
>
> **Re-reconciled 2026-08-13 (post-rename):** the rename pass moved the DocType
> folders, JSON, controllers, patches, and the desk `routes[]` map, but left the
> four page-side `.js` files pointing at the *old* whitelisted-method path
> (`…doctype.supply_path_page.supply_path_page.get_iframe_url`). The pages load
> and the iframe never appears, with Frappe logging
> `Failed to get method for command … with No module named '…doctype.supply_path_page'`.
> See "Post-rename follow-up — page JS method paths" below.

## The problem

v17's router (`apps/frappe/frappe/public/js/frappe/router.js:115`) auto-populates
`frappe.router.routes[slug(doctype)] = { doctype }` for every DocType the user can
read. Several frepple connector singletons (Supply Path Page, Manufacturing
Order Page, Purchase Order Page, Resource Report Page) collide with the slug of
the matching Desk Page — the router opens the DocType form, the page's
`on_page_load` is never reached, no iframe is rendered.

## Why the v14 / Phase 1 / Phase 3 specs missed it

B6 in `ANALYSIS_AND_MIGRATION_PLAN.md §8` lists this as a verified non-issue
("`frappe.pages['x'].on_page_load` … still works in v17"). The non-issue audit
confirmed the *page-script loading* contract (it does load — the script body
runs from disk at every boot, see `apps/frappe/frappe/core/doctype/page/page.py:145`).
It did NOT exercise the *routing* contract.

The bug surface is small (4 of 6 pages) and the fix had to be admin-controlled
to survive future slug collisions without an app release.

## Original solution — three layers (shim)

This was implemented on 2026-08-11 and ran in production for two days:

1. **Schema** — new child-table DocType `Frepple Page Route Override`
   (`fact_frepple/fact_frepple/doctype/frepple_page_route_override/`). Admin
   adds a row per slug they want to protect, with a `preempt_doctype` check.
2. **Boot payload** — `fact_frepple/fact_frepple/startup/boot.py::boot_session`
   reads `Frepple Settings.route_overrides` and stamps the resulting
   `{slug: bool}` map onto `frappe.boot.frepple_route_overrides`. Wired via
   `boot_session = "fact_frepple.fact_frepple.startup.boot.boot_session"` in
   `hooks.py`.
3. **Client filter** — `fact_frepple/fact_frepple/public/js/frepple_route_overrides.js`,
   loaded via `app_include_js`, monkey-patches `frappe.router.setup` to drop
   the offending keys from the auto-populated `routes[]` map.

A migration patch (`patches.txt` → `fact_frepple.patches.v17_route_overrides`)
seeds the four known collisions on every site with the app installed.
Re-running the patch is a no-op; admin edits survive re-runs.

### Why the shim was retired

The shim works but adds three moving parts (a child DocType, a boot hook, a
client filter) just to mask a slug naming collision. The collision is
self-inflicted — four singletons whose labels happen to equal the labels of
the Desk Pages they drive. Renaming the singletons eliminates the collision,
after which no shim, hook, or admin table is needed.

The fifth connector singleton, `Frepple Demand Page`, already had a different
slug (`frepple-demand-page` ≠ `demand-page`) and was never affected.

## Resolution — rename the singletons

The four colliding singletons were renamed on 2026-08-13:

| Old | New |
|---|---|
| `Supply Path Page` | `Frepple Supply Path Page` |
| `Manufacturing Order Page` | `Frepple Manufacturing Order Page` |
| `Purchase Order Page` | `Frepple Purchase Order Page` |
| `Resource Report Page` | `Frepple Resource Report Page` |

After the rename `/desk/<slug>` (e.g. `/desk/supply-path-page`) only matches
the Desk Page — v17's router naturally routes there, no client surgery needed.

### Files removed

- `fact_frepple/fact_frepple/public/js/frepple_route_overrides.js` — client filter
- `fact_frepple/fact_frepple/startup/boot.py` (+ `test_boot.py`) — boot hook
- `fact_frepple/fact_frepple/doctype/frepple_page_route_override/` — child DocType
- `fact_frepple/patches/v17_route_overrides.py` (+ test) — seed migration

### Files added

- `fact_frepple/fact_frepple/patches/v17_rename_collision_doctypes.py` —
  one-shot `RENAME TABLE` migration. Idempotent; safe to re-run on sites
  that already have the new names.

### Files edited

- Each renamed DocType's `name` field in `doctype/<slug>/<slug>.json`
- Each controller's `frappe.get_doc("Supply Path Page")` call to the new name
- Each `.js` form hook's `frappe.ui.form.on(...)` registration
- Each page record's `page_name` (display title)
- `patches.txt` — replaces the seed with the rename
- `hooks.py` — drops `app_include_js` and `boot_session`
- `frepple_settings/frepple_settings.json` — drops `route_overrides` table field

## Properties (after rename)

- **Zero runtime work** — the slug no longer collides, the router wins
  without any custom code path.
- **Static** — the names of the four singletons are fixed in their JSON. If a
  future collision appears, the same patch pattern (`v17_rename_...`) handles
  it as a one-off rather than as ongoing administrative state.
- **Idempotent** — the rename patch re-running on a clean site is a no-op
  (the table-rename step skips if the source table is gone; the DocType-row
  UPDATE skips if the row no longer has the old name).

## Verification

See the commit that introduced this spec for the original shim verification
(removed files' tests can no longer be run; the rename has its own verifier
in the migration docs). The rename's correctness is checked by:

- `bench --site test.localhost run-tests --module
  "fact_frepple.fact_frepple.doctype.frepple_supply_path_page"`
- `bench --site test.localhost run-tests --module
  "fact_frepple.fact_frepple.doctype.frepple_manufacturing_order_page"`
- `bench --site test.localhost run-tests --module
  "fact_frepple.fact_frepple.doctype.frepple_purchase_order_page"`
- `bench --site test.localhost run-tests --module
  "fact_frepple.fact_frepple.doctype.frepple_resource_report_page"`

And the live URL test (after migration):

```
$ curl http://localhost:8003/desk/supply-path-page → 200, desk Page renders
$ curl http://localhost:8003/api/method/fact_frepple.fact_frepple.doctype.
  frepple_supply_path_page.frepple_supply_path_page.get_iframe_url → 91.107.206.65:9000/...
$ curl '<frepple url>' → 200 with the supply-path tree
```

## Post-rename follow-up — page JS method paths

### The bug

The 2026-08-13 rename pass renamed:

- DocType folders: `doctype/supply_path_page/` → `doctype/frepple_supply_path_page/`
  (same for `manufacturing_order_page`, `purchase_order_page`,
  `resource_report_page`).
- Python controllers: `supply_path_page.py` → `frepple_supply_path_page.py`
  with `class FreppleSupplyPathPage(Document)` and `@frappe.whitelist()`
  `get_iframe_url()`.
- `.json` `name` fields: `Supply Path Page` → `Frepple Supply Path Page`.
- Database tables: `tabSupply Path Page` → `tabFrepple Supply Path Page`
  (one-shot patch `fact_frepple.patches.v17_rename_collision_doctypes`).
- `frappe.get_doc("Supply Path Page")` calls inside each controller.
- Form `.js` `frappe.ui.form.on("Supply Path Page", …)` registrations.

It missed the four Desk Page `.js` files in `fact_frepple/fact_frepple/page/`
that invoke the whitelisted method via `frappe.call`:

- `page/supply_path_page/supply_path_page.js` calls
  `fact_frepple.fact_frepple.doctype.supply_path_page.supply_path_page.get_iframe_url`.
- `page/manufacturing_order_page/manufacturing_order_page.js` calls
  `fact_frepple.fact_frepple.doctype.manufacturing_order_page.manufacturing_order_page.get_iframe_url`.
- `page/purchase_order_page/purchase_order_page.js` calls
  `fact_frepple.fact_frepple.doctype.purchase_order_page.purchase_order_page.get_iframe_url`.
- `page/resource_report_page/resource_report_page.js` calls
  `fact_frepple.fact_frepple.doctype.resource_report_page.resource_report_page.get_iframe_url`.

`page/demand_page/demand_page.js` was unaffected because its singleton
(`Frepple Demand Page`) already had the `frepple_` prefix.

### Symptom

Loading any of the four renamed pages renders an empty app shell (the
`on_page_load` hook runs, but `getSettings()` rejects with
`Failed to get method for command fact_frepple.fact_frepple.doctype.<slug>.<slug>.get_iframe_url with No module named 'fact_frepple.fact_frepple.doctype.<slug>'`).
The iframe is never injected because `r.message` is `undefined`.

### The fix

Each of the four JS files must call the renamed module path:

- `…doctype.supply_path_page.supply_path_page.get_iframe_url`
  → `…doctype.frepple_supply_path_page.frepple_supply_path_page.get_iframe_url`
- `…doctype.manufacturing_order_page.manufacturing_order_page.get_iframe_url`
  → `…doctype.frepple_manufacturing_order_page.frepple_manufacturing_order_page.get_iframe_url`
- `…doctype.purchase_order_page.purchase_order_page.get_iframe_url`
  → `…doctype.frepple_purchase_order_page.frepple_purchase_order_page.get_iframe_url`
- `…doctype.resource_report_page.resource_report_page.get_iframe_url`
  → `…doctype.frepple_resource_report_page.frepple_resource_report_page.get_iframe_url`

### Regression coverage

The four affected doctypes already have unit tests that exercise
`get_iframe_url` end-to-end against a real Frappe site
(`doctype/frepple_supply_path_page/test_frepple_supply_path_page.py`, …).
Those tests verify the *Python* side; they cannot catch a typo in the JS path
on their own. The client side is covered by a static-content test
(`fact_frepple/fact_frepple/page/test_page_iframe_methods.py`) that asserts
each of the four page `.js` files references the renamed module path —
added in the same fix commit.
