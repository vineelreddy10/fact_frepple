# Desktop icon, workspace, and sidebar for `fact_frepple`

> **Status:** spec, not implementation. No code is written until this is accepted.
> **Branch:** `feat/desktop-workspace-sidebar` (off `dev`).
> **Promote path:** `feat/desktop-workspace-sidebar → dev → pre-pro → main` (per `AGENTS.md`).
> **Drives:** this finishes the desk-side onboarding of the v17 port (Phase 5.5) so the connector is reachable from the desk without typing URLs.

---

## 1. Goal

Give `fact_frepple` a desk presence on par with stock ERPNext sub-modules: an apps-screen logo, a workspace tile in the app dock, and an in-page sidebar that lists every DocType and desk page the connector ships. Mirror the structure used by `erpnext/accounts/workspace/accounting/accounting.json` and the `workspace_sidebar` fixtures in `erpnext`, so future contributors recognise the shape.

**Acceptance:** with `test.localhost` on the new branch, an Administrator logs in and sees:

1. A red/teal `Fact Frepple` round-icon tile on the apps screen, alongside the `Frappe` and `ERPNext` tiles.
2. A `Fact Frepple` workspace in the left app dock (rail), with the calendar icon and the blue indicator dot.
3. Opening the workspace shows (a) the same shortcut cards the user already has, and (b) a left sidebar listing the 10 groups from `config/frepple.py` (`Frepple Sales`, `Frepple Inventory`, `Frepple Capacity`, `Frepple Purchasing`, `Frepple Manufacturing`, `Additional Data`, `Settings`, `Frepple Result`, `Frepple Report`, `Customization`), each collapsible, with the correct DocType / Page link underneath.

---

## 2. Non-goals (this revision)

- No new DocTypes, no new pages, no new fields — only desk-side wiring.
- No theme / colour restyling beyond the brand red (`#e74c3c`) — it matches ERPNext's accent by convention, not by requirement.
- No `add_to_workspace_dock` redirect — we keep the standalone app icon (see D-13).
- No removal of the legacy `config/frepple.py` `get_data()` helper in this revision; it is left as a fallback for patches and manual runs, but the JSON is the canonical source.

---

## 3. Decisions locked (grill-me session)

| #   | Decision                                          | Choice                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D-1 | Icon style                                        | Single circular SVG, two-layer (background tint + foreground glyph). Re-used for both the apps-screen logo and the desk module tile. Mirrors `erpnext/public/desktop_icons/erpnext.svg` style.                                                                                                                                                                                                                                                                      |
| D-2 | Icon glyph                                        | A stylised `F` inside a calendar grid (the connector plans work orders — the calendar signals "scheduling"; the `F` makes it identifiable as fact-frepple, not the generic `calendar` lucide icon). 54×54 viewBox, matches `frappe/public/icons/desktop_icons/alphabets.svg` style.                                                                                                                                                                          |
| D-3 | App brand colour                                  | `#e74c3c` (red — same as ERPNext's `app_color`). Keeps the apps-screen rail visually consistent.                                                                                                                                                                                                                                                                                                                                                                   |
| D-4 | App icon (FA class)                               | `fa fa-calendar` (kept from the v14 scaffold; the SVG is what users see, the FA class is the fallback for places that still render text icons).                                                                                                                                                                                                                                                                                                                   |
| D-5 | Apps-screen entry                                 | `add_to_apps_screen` enabled with `logo = "/assets/fact_frepple/icons/fact_frepple.svg"`, `title = "Fact Frepple"`, `route = "/app/fact-frepple"` (the workspace). `has_permission` is omitted (defaults to "always visible").                                                                                                                                                                                                                                    |
| D-6 | Workspace                                         | Use the existing `fact_frepple/fact_frepple/workspace/fact_frepple/fact_frepple.json` (title=`Fact Frepple`, label=`Fact Frepple`, icon=`calendar`, sequence_id=50, app=`fact_frepple`, module=`Fact Frepple`, public=1, standard=1). Re-export after changes so the JSON is the source of truth.                                                                                                                                                                  |
| D-7 | Sidebar source of truth                           | The `Workspace.sidebar_items` JSON child table. The legacy `config/frepple.py` `get_data()` is left in place but its output is treated as fallback only; the JSON is what bench migrate imports.                                                                                                                                                                                                                                                                   |
| D-8 | Sidebar items taxonomy                            | Top-level direct `Link` rows (no group header) for the planner entry pages (`Frepple Demand Page`, `Frepple Supply Path Page`, `Frepple Custom Page`). `Section Break` rows for the 7 logical groups; `Link` rows with `child=1` underneath each section. Lucide icons chosen per group (see §5).                                                                                                                                                              |
| D-9 | Sidebar types — old vs new                        | The existing JSON uses `type: "Group"` which is **not** a valid `Workspace Sidebar Item` type (`Link` / `Section Break` / `Spacer` / `Sidebar Item Group` are the only options). All `Group` rows are rewritten to `Section Break` with `child=0`, `icon=<lucide>`, `indent=1`, `keep_closed=1`. Existing `Link` rows keep their `child=1` flag and get their icons refreshed to match the dest doctype/page theme.                              |
| D-10 | `links` field                                     | Left as `[]` (empty). The workspace bodies (shortcut cards, charts) are managed per-workspace in the future; the sidebar is the navigation. The legacy `config/frepple.py` `get_data()` is the only place that writes the v14-style `links` shape, and it remains dormant.                                                                                                                                                                                          |
| D-11 | Active module desktop icon                        | `config/desktop.py` updated to point at the new SVG (`/assets/fact_frepple/desktop_icons/fact_frepple.svg`) instead of the FA class fallback. Keep `type: "module"`, `module_name: "Fact Frepple"`, `color: "blue"` (matched to the existing workspace `indicator_color`).                                                                                                                                                                                       |
| D-12 | Permissions                                       | No new roles added. The workspace stays public (no `roles` table) so every authenticated desk user can see it. DocType-level permissions on the 29 mirror DocTypes are unchanged (the existing `if_permitted` check still gates sidebar links via `is_item_allowed`).                                                                                                                                                                                              |
| D-13 | Companion-app pin (`add_to_workspace_dock`)       | **Not used.** ERPNext itself does not use it for its own sub-modules; staging the connector as a standalone app keeps the door open for non-ERPNext installs (e.g. plain Frappe with a custom Item doctype). The hooks.py comment block explaining the trade-off is kept.                                                                                                                                                                                            |
| D-14 | Compatibility                                    | `developer_mode=1` is on (`sites/common_site_config.json`); saving the workspace from the desk will re-export to JSON automatically and the spec's JSON changes will survive site restart.                                                                                                                                                                                                                                                                          |

---

## 4. Architecture summary (what changes where)

The connector's desk surface is three layers deep. This revision touches exactly the outer two layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Desk (chrome)                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Apps screen   ──►  app_logo_url  +  add_to_apps_screen (D-5)     │  │
│  │                       apps/fact_frepple/public/icons/             │  │
│  │                       fact_frepple.svg                            │  │
│  │                                                                  │  │
│  │ App dock      ──►  Workspace doc (D-6)                           │  │
│  │ (rail)              name=Fact Frepple, icon=calendar,           │  │
│  │                     app=fact_frepple, sequence_id=50             │  │
│  │                                                                  │  │
│  │ Workspace     ──►  Workspace.sidebar_items  (D-7, D-9)          │  │
│  │ sidebar            apps/fact_frepple/fact_frepple/workspace/    │  │
│  │                     fact_frepple/fact_frepple.json               │  │
│  │                                                                  │  │
│  │ Module icon   ──►  config/desktop.py                   (D-11)   │  │
│  │ (filter chip)       apps/fact_frepple/public/desktop_icons/      │  │
│  │                     fact_frepple.svg                             │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

No layer-three wiring (per-Doctype list views, default filters, dashboard charts) is touched.

---

## 5. Sidebar layout (lock down before code)

The sidebar lives entirely inside `Workspace.sidebar_items`. Rows are emitted in this exact order; downstream imports accept the order verbatim — re-ordering in the desk UI just gets clobbered on the next `bench migrate`.

| # | Row                | Type             | child | icon                | indent | link_to / link_type                                       | source (lucide / reason)           |
| - | ------------------ | ---------------- | ----- | ------------------- | ------ | --------------------------------------------------------- | ---------------------------------- |
| 1 | Home               | Link             | 0     | `house`             | 0      | Workspace → `Fact Frepple`                                | standard ERPNext "home" pattern    |
| 2 | Dashboard          | Link             | 0     | `chart-column`      | 0      | Dashboard → `Fact Frepple`                                | standard ERPNext "dashboard" pattern |
| 3 | Frepple Demand Page | Link           | 0     | `external-link`     | 0      | Page → `demand-page`                                      | planner entry, top-level           |
| 4 | Frepple Custom Page | Link           | 0     | `external-link`     | 0      | Page → `frepple-custom-page`                              | planner entry, top-level           |
| 5 | Frepple Supply Path Page | Link       | 0     | `external-link`     | 0      | Page → `supply-path-page`                                 | planner entry, top-level           |
| 6 | **Frepple Sales**  | Section Break    | 0     | `trending-up`       | 1      | —                                                         | (was "Group"; redesign)            |
| 7 | Frepple Demand     | Link             | 1     | `list`              | 0      | DocType → `Frepple Demand`                                |                                    |
| 8 | Frepple Item       | Link             | 1     | `box`               | 0      | DocType → `Frepple Item`                                  |                                    |
| 9 | Frepple Customer   | Link             | 1     | `users`             | 0      | DocType → `Frepple Customer`                              |                                    |
| 10 | Frepple Location  | Link             | 1     | `map-pin`           | 0      | DocType → `Frepple Location`                              |                                    |
| 11 | **Frepple Inventory** | Section Break | 0     | `package`           | 1      | —                                                         |                                    |
| 12 | Frepple Buffer     | Link             | 1     | `layers`            | 0      | DocType → `Frepple Buffer`                                |                                    |
| 13 | Frepple Item Distribution | Link     | 1     | `truck`             | 0      | DocType → `Frepple Item Distribution`                     |                                    |
| 14 | **Frepple Capacity** | Section Break | 0     | `gauge`             | 1      | —                                                         |                                    |
| 15 | Frepple Resource   | Link             | 1     | `factory`           | 0      | DocType → `Frepple Resource`                              |                                    |
| 16 | Frepple Skill      | Link             | 1     | `wrench`            | 0      | DocType → `Frepple Skill`                                 |                                    |
| 17 | Frepple Resource Skill | Link        | 1     | `link`              | 0      | DocType → `Frepple Resource Skill`                        |                                    |
| 18 | **Frepple Purchasing** | Section Break | 0   | `shopping-cart`     | 1      | —                                                         |                                    |
| 19 | Frepple Supplier   | Link             | 1     | `truck`             | 0      | DocType → `Frepple Supplier`                              |                                    |
| 20 | Frepple Item Supplier | Link         | 1     | `link-2`            | 0      | DocType → `Frepple Item Supplier`                         |                                    |
| 21 | **Frepple Manufacturing** | Section Break | 0 | `hammer`     | 1      | —                                                         |                                    |
| 22 | Frepple Operation  | Link             | 1     | `cog`               | 0      | DocType → `Frepple Operation`                             |                                    |
| 23 | Frepple Operation Material | Link      | 1     | `package-2`         | 0      | DocType → `Frepple Operation Material`                    |                                    |
| 24 | Frepple Operation Resource | Link      | 1     | `person-standing`   | 0      | DocType → `Frepple Operation Resource`                    |                                    |
| 25 | **Additional Data** | Section Break    | 0     | `database`          | 1      | —                                                         |                                    |
| 26 | Frepple Calendar   | Link             | 1     | `calendar`          | 0      | DocType → `Frepple Calendar`                              |                                    |
| 27 | Frepple Calendar Bucket | Link       | 1     | `calendar-clock`    | 0      | DocType → `Frepple Calendar Bucket`                       |                                    |
| 28 | **Settings**       | Section Break    | 0     | `cog`               | 1      | —                                                         |                                    |
| 29 | Frepple Settings   | Link             | 1     | `cog`               | 0      | DocType → `Frepple Settings`                              |                                    |
| 30 | Frepple Integration Data Fetching | Link | 1 | `download`     | 0      | DocType → `Frepple Integration Data Fetching`             |                                    |
| 31 | Frepple Data Export | Link           | 1     | `upload`            | 0      | DocType → `Frepple Data Export`                           |                                    |
| 32 | Frepple Run Plan   | Link             | 1     | `play`              | 0      | DocType → `Frepple Run Plan`                              |                                    |
| 33 | **Frepple Result** | Section Break    | 0     | `list-checks`       | 1      | —                                                         |                                    |
| 34 | Frepple Manufacturing Order Page | Link | 1 | `external-link`    | 0      | Page → `manufacturing-order-page`                         |                                    |
| 35 | Frepple Manufacturing Order | Link     | 1     | `clipboard-list`    | 0      | DocType → `Frepple Manufacturing Order`                   |                                    |
| 36 | Frepple Purchase Order Page | Link    | 1     | `external-link`     | 0      | Page → `purchase-order-page`                              |                                    |
| 37 | Frepple Purchase Order | Link       | 1     | `file-text`         | 0      | DocType → `Frepple Purchase Order`                        |                                    |
| 38 | **Frepple Report** | Section Break    | 0     | `chart-column`      | 1      | —                                                         |                                    |
| 39 | Resource Report    | Link             | 1     | `external-link`     | 0      | Page → `resource-report-page`                             |                                    |
| 40 | **Customization**  | Section Break    | 0     | `sliders-horizontal`| 1      | —                                                         |                                    |
| 41 | Frepple Custom Page Settings | Link   | 1     | `settings`          | 0      | DocType → `Frepple Custom Page Settings`                  |                                    |

Forty-one rows. Each Section Break carries `keep_closed=1` so the sidebar opens tidy.

---

## 6. Implementation phases (sequenced; each has an explicit gate)

### Phase 1 — Spec (this file)

- `specs/desktop-workspace-sidebar.md` written; nothing else touched.
- **Gate:** spec reviewed; commit it as its own commit.

### Phase 2 — Icon assets

- `fact_frepple/public/icons/fact_frepple.svg` — apps-screen logo (54×54).
- `fact_frepple/public/desktop_icons/fact_frepple.svg` — module desktop icon (54×54, same artwork).
- Both share the same artwork so the icon is consistent in every chrome slot.
- **Gate:** `bench --site test.localhost execute 'frappe.db.get_value("File", ...)` confirms the SVG exists at `/assets/fact_frepple/...` after `bench build` (or just `bench --site test.localhost clear-cache`).

### Phase 3 — `hooks.py` wiring

- Add `app_icon`, `app_color`, `app_logo_url`, `app_home` (mirror ERPNext).
- Uncomment `add_to_apps_screen` block; fill it (D-5).
- Add `app_include_icons` so the SVG is bundled for the desk.
- **Gate:** `bench --site test.localhost console` shows `fact_frepple` in `frappe.get_hooks("add_to_apps_screen")`.

### Phase 4 — `config/desktop.py` rewrite

- `logo` field pointing at the new SVG (D-11).
- Keep `module_name`, `type`, `color`, `label` unchanged.
- **Gate:** `bench --site test.localhost execute "frappe.client.get_list" --kwargs '{"doctype":"Desktop Icon", "filters":{"module_name":"Fact Frepple"}, ...}'` returns the icon.

### Phase 5 — Workspace JSON rewrite

- Replace every `Group` row in `sidebar_items` with a `Section Break` row (D-9).
- Refresh icons on every `Link` row per §5.
- Add the three top-level planner-entry links (rows 3, 4, 5).
- Add Home and Dashboard rows (rows 1, 2) so the workspace matches ERPNext's standard chrome.
- Leave `links: []`, `content: "[]"`, `charts: []`, `number_cards: []`, `shortcuts: []`, `quick_lists: []`, `custom_blocks: []` empty.
- **Gate:** `bench --site test.localhost execute "frappe.client.get" --kwargs '{"doctype":"Workspace", "name":"Fact Frepple"}'` returns 41 sidebar rows (no `Group` rows).

### Phase 6 — `bench migrate` + verify

- `bench --site test.localhost migrate --skip-failing` (or just `migrate`).
- `bench clear-cache` and `bench build --app fact_frepple` to publish the SVG.
- Spot-check: `frappe.get_all("Workspace Sidebar Item", filters={"parent": "Fact Frepple"}, fields=["type"])` (via `bench console`) — expect `{"Link": 31, "Section Break": 10}` (no `Group`).
- **Gate:** admin logs in, sees the icon, opens the workspace, sees the sidebar with all 10 collapsible groups.

---

## 7. Acceptance criteria (recap)

| #   | Criterion                                                                                                                   | How verified                                                                                                                          |
| --- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| A-1 | `fact_frepple` appears in the apps screen alongside `frappe` and `erpnext`.                                                 | Manual login as Administrator → apps screen → find the tile.                                                                           |
| A-2 | `Fact Frepple` is a tile in the desk app dock (rail).                                                                       | Manual login → left rail → find the tile.                                                                                             |
| A-3 | The workspace JSON has 41 `sidebar_items` with 10 `Section Break` rows and 31 `Link` rows. (`Group` count is 0.)             | `bench console` count query.                                                                                                          |
| A-4 | Every DocType and Page the connector ships has a sidebar entry (no DocType is silently missing).                            | `diff` between `frappe.get_all("DocType", filters={"module":"Fact Frepple"}, pluck="name")` and the `link_to` values in sidebar Links. |
| A-5 | The SVG renders without console errors at the apps screen and at the rail.                                                   | Manual login → DevTools → no `404` for `/assets/fact_frepple/...`.                                                                    |
| A-6 | `bench --site test.localhost run-tests --app fact_frepple` stays green (no regression on Phase 0-6 tests).                   | `bench run-tests`.                                                                                                                    |

A-1 through A-6 must all pass before merging to `dev`.

---

## 8. Risk register

- **R-1 (low).** The `frappe.patches.v16_0.migrate_workspace_sidebar_to_workspace` patch already ran on `test.localhost` (the `Workspace Sidebar` DocType is deprecated). Sidebar items live on `Workspace.sidebar_items` for both ERPNext and fact_frepple, so the pattern matches.
- **R-2 (medium).** If a site had site-level customizations on the `Fact Frepple` workspace (e.g. hidden sections), the `bench migrate` re-export will clobber them. Mitigate: read `Workspace Customization` rows before the export; only the new branch install is in scope, so the site has no customizations yet.
- **R-3 (low).** Lucide icon names change between releases. The chosen names (`house`, `chart-column`, `cog`, `calendar`, `package`, `gauge`, `factory`, `truck`, `trending-up`, `users`, `map-pin`, `layers`, `wrench`, `link`, `shopping-cart`, `link-2`, `cog`, `package-2`, `person-standing`, `database`, `calendar`, `calendar-clock`, `download`, `upload`, `play`, `list-checks`, `clipboard-list`, `file-text`, `external-link`, `sliders-horizontal`, `settings`, `box`, `list`) are stable across the v17 line — same set ERPNext uses today.
- **R-4 (low).** The `demand-page` etc. page records exist on the site (verified via `bench console`); the `link_to` names match the page slug. Re-verified at Phase 6.

---

## 9. Follow-ups (out of scope)

- Per-workspace listing filters (e.g. "show only items with the `frepple_integration` flag on").
- Dashboard charts on the workspace body (currently `charts: []`).
- Per-Doctype dashboard data for the 29 mirror DocTypes.
- A "first-run" interactive onboarding step (the workspace shortcut cards are blank today).
- Localisation of the section labels — `_(...)` wrapping is added in the JSON's link `label` (consistent with `config/frepple.py`); the sidebar group labels in this revision stay English to mirror the existing `_(...)` literal strings.
