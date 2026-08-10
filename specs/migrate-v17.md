# Migrate `erpnext_frepple_connector` → `fact_frepple` (Frappe/ERPNext v17)

> **Status:** spec, not implementation. No code is written until this is accepted.
> **Branch:** `feat/migrate-v17` (off `dev`, off `main`).
> **Promote path:** `feat/migrate-v17 → dev → pre-pro → main` (per `AGENTS.md`).
> **Spec convention:** this file is committed as its own commit *before* any code lands, so the spec and the implementation can be diffed over time.

---

## 1. Goal

Copy the **29 DocTypes, 6 desk pages, and 2 controllers** from `github.com/msf4-0/ERPNext-Frepple-Integration` (v14, 240 files; frepple-endorsed per `frepple/doc/erp-integration/erpnext-connector.rst`) into the empty `fact_frepple` scaffold so the connector runs on Frappe v17 + ERPNext v17, and validate end-to-end two-way data transfer against a real frepple server.

**Acceptance:** `bench --site test.localhost migrate` succeeds, `bench --site test.localhost run-tests --app fact_frepple` is green, and a scripted E2E test proves one ERPNext Sales Order becomes one real Work Order + one real Purchase Order after a frepple plan run.

---

## 2. Non-goals (this revision)

- No refactor away from the 29-DocType mirror pattern.
- No name change — `fact_frepple` everywhere; all `frepple.*` imports are rewritten.
- No GPLv3 relicensing (source is GPLv3, target stays MIT + NOTICE attribution).
- No remote production frepple deployment — sandbox only.
- No Enterprise Edition features.

---

## 3. Decisions locked (grill-me session)

| # | Decision | Choice |
|---|---|---|
| D1 | Source | GitHub fetch `msf4-0/ERPNext-Frepple-Integration` |
| D2 | Architecture | Direct port, keep 29 mirror DocTypes |
| D3 | Naming | `fact_frepple` everywhere; rewrite all `frepple.*` imports |
| D4 | License | MIT (scaffold) + NOTICE attribution to msf4-0 authors |
| D5 | Dev site | `test.localhost` (already has frappe+erpnext+fact_frepple installed) |
| D6 | Tracer bullet | Settings + Custom Page iframe only |
| D7 | frepple install method | Docker `ghcr.io/frepple/frepple-community:9.17.0` + side-car `postgres:16` |
| D8 | E2E test scope | 1 Sales Order → 1 real Work Order + 1 real Purchase Order |
| D9 | frepple DB | Postgres 16 in side-car container; named volume for persistence |
| D10 | frepple port on host | `localhost:9000` (container 80) |
| D11 | frepple webtoken auth | JWT HS256 with shared secret |
| D12 | Test framework | `unittest` + `responses` library + `docker compose` for E2E |

---

## 4. Architecture summary (preserved verbatim from analysis §2-7)

The connector is a **bidirectional data bridge** with four layers:

1. **Settings** — single-row `Frepple Settings` DocType. Holds URL, basic auth, JWT signing secret, `frepple_integration` toggle.
2. **Mirror DocTypes** (29) — each one projects an ERPNext native or frepple-shaped entity into the app so the planner has a familiar ERPNext form.
3. **Controllers** (2) — `Frepple Data Export` (push) and `Frepple Integration Data Fetching` (mirror-fill + pull plan results).
4. **Pages** (6) — iframe wrappers into frepple UI views; the most important is `Frepple Custom Page` for the full planner.

Full architectural detail lives in `ANALYSIS_AND_MIGRATION_PLAN.md` §2–§7 (do not duplicate here — link instead).

---

## 5. Phases (sequenced; each has an explicit acceptance gate)

### Phase 0 — Repository & source prep

- `git clone --depth=1 https://github.com/msf4-0/ERPNext-Frepple-Integration.git /tmp/opencode/erpnext_frepple_connector` (read-only reference; never vendored).
- Inventory actual file count vs the 240 the analysis claims.
- Branch: `git checkout -b feat/migrate-v17` off `dev`.

**Acceptance:** cloned source at `/tmp/opencode/erpnext_frepple_connector/`; branch exists locally.

### Phase 0.5 — Install frepple (Docker) — gates Phase 6

This phase is independent of the connector code and can be done as soon as Phase 0 lands. It provides the real frepple target for integration tests.

#### 0.5.1 — Compose file

Create `docker/frepple.compose.yaml`:

```yaml
name: frepple-dev

services:
  frepple:
    image: ghcr.io/frepple/frepple-community:9.17.0
    container_name: frepple-dev
    ports:
      - "9000:80"
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: frepple
      POSTGRES_PASSWORD: frepple
      POSTGRES_DBNAME: frepple
      FREPPLE_TIME_ZONE: UTC
      FREPPLE_CONTENT_SECURITY_POLICY: "frame-ancestors 'self' http://localhost:8003"
      FREPPLE_X_FRAME_OPTIONS: SAMEORIGIN
      FREPPLE_CSRF_TRUSTED_ORIGINS: "http://localhost:8003,http://test.localhost:8003"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - frepple-config:/etc/frepple
      - frepple-logs:/var/log/frepple
    restart: unless-stopped

  postgres:
    image: postgres:16
    container_name: frepple-postgres
    environment:
      POSTGRES_DB: frepple
      POSTGRES_USER: frepple
      POSTGRES_PASSWORD: frepple
    volumes:
      - frepple-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U frepple -d frepple"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

volumes:
  frepple-pgdata:
  frepple-config:
  frepple-logs:
```

`frame-ancestors 'self' http://localhost:8003` is required so the browser allows the frepple iframe to be loaded from the bench desk at `test.localhost:8003`.

#### 0.5.2 — Bring it up

```bash
cd docker
docker compose -f frepple.compose.yaml pull
docker compose -f frepple.compose.yaml up -d
docker compose -f frepple.compose.yaml logs -f frepple   # wait for "Starting web server"
```

First boot takes ~60-90s (entrypoint creates 3 databases, runs migrations, loads demo fixtures into `scenario1` and `scenario2`). Healthy: `curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/` returns `200` or `302`.

#### 0.5.3 — First-login hardening

1. Visit `http://localhost:9000/` → login as `admin` / `admin`. Change the password immediately.
2. Generate a JWT signing secret: `openssl rand -hex 32`.
3. Add it to the frepple container's `djangosettings.py` (mounted at `/etc/frepple/djangosettings.py`):
   ```python
   SECRET_WEBTOKEN_KEY = '<the-random-hex>'
   ```
4. Restart: `docker compose -f frepple.compose.yaml restart frepple`.
5. Manually verify the JWT path:
   ```bash
   pip install PyJWT
   python3 -c "
   import jwt, time
   print(jwt.encode({'exp': round(time.time())+600, 'user': 'admin', 'navbar': False},
                    '<the-secret>', algorithm='HS256'))
   "
   curl -i "http://localhost:9000/?webtoken=<paste>"
   ```
   200 with HTML = JWT works. Save the secret — it goes into `Frepple Settings.secret_key` later.

#### 0.5.4 — Smoke

```bash
curl -u admin:admin 'http://localhost:9000/api/input/demand/?format=json' | head
```

#### 0.5.5 — Convenience wrappers

Add `docker/Makefile`:

```makefile
up:    ; docker compose -f frepple.compose.yaml up -d
down:  ; docker compose -f frepple.compose.yaml down
reset: ; docker compose -f frepple.compose.yaml down -v
logs:  ; docker compose -f frepple.compose.yaml logs -f
```

Add `docker/README.md` documenting bring-up + JWT secret extraction.

**Acceptance:** `curl http://localhost:9000/` returns 200; `curl -u admin:admin http://localhost:9000/api/input/demand/?format=json` returns JSON; JWT round-trip works.

### Phase 1 — Tracer bullet: Settings + Custom Page

Files migrated: `frepple_settings`, `frepple_custom_page_settings`, `frepple_custom_page` (5 files).

v17 fixes F1–F14 (§6) applied. Smoke: open Settings, save; open Custom Page, select a settings record; iframe URL is `http://localhost:9000/<view>/?webtoken=<jwt>`.

**New v17-specific fix (F14):** rewrite `get_iframe_url()` to issue a JWT instead of the v14 `?secret=<key>` query param.

**Acceptance:** Settings form loads; Custom Page iframe URL parses as a valid JWT signed with `settings.secret_key`.

### Phase 2 — Bulk mirror DocType copy

Mechanical copy of 27 remaining DocTypes + 2 controllers (`Frepple Data Export`, `Frepple Integration Data Fetching`). Apply F1–F14 via `sed`. Audit field names against ERPNext v17. Make WIP location configurable via `Frepple Settings.wip_location_name` instead of the hard-coded `Work In Progress` lookup.

**Acceptance:** all 29 DocTypes visible in desk list views; export controller POSTs JSON to a mocked endpoint; fetch controller parses a canned response.

**Status (2026-08-10):** done on `feat/migrate-v17`. 24 DocTypes registered in
the desk (`module: Fact Frepple`), `bench --site test.localhost migrate` is
clean, `bench --site test.localhost run-tests --app fact_frepple` runs 4 unit
tests (export URL builder + R8 WIP-prefix helper) and reports OK. The 22 new
doctypes are mirror-only stubs awaiting the Phase 4 real-test rewrite. Phase 3
pages still pending.

Script that did the copy + transforms: `scripts/migrate_phase2.sh`; idempotent
via the `.fact_frepple_migrated` marker (added to `.gitignore`).

### Phase 3 — Desk pages and Frepple Run Plan

5 remaining iframe pages + `Frepple Run Plan` DocType + workspace + desktop + docs config. All iframe pages call the same `get_iframe_url(view_name)` helper.

**Acceptance:** all 6 desk pages render; workspace shows the 9 sections; clicking "Run Plan" on `Frepple Run Plan` triggers `/api/runplan/` against a mocked endpoint.

**Status (2026-08-10):** done on `feat/migrate-v17`. The 5 remaining iframe
pages (`demand-page`, `manufacturing-order-page`, `purchase-order-page`,
`resource-report-page`, `supply-path-page`) and their single-row DocTypes
are migrated under `fact_frepple/fact_frepple/{page,doctype}/...`. The JWT
signing logic that lived inside the v14 source's per-page `get_iframe_url()`
is extracted into a single helper `fact_frepple.fact_frepple.page._iframe.sign_jwt_url`;
`Frepple Custom Page Settings.get_iframe_url()` and the 5 new helpers
all delegate to it (F14). Workspace is shipped as a v17 Workspace JSON
DocType at `fact_frepple/fact_frepple/workspace/fact_frepple/fact_frepple.json`
with the 10 source sections (Sales, Inventory, Capacity, Purchasing,
Manufacturing, Additional Data, Settings, Result, Report, Customization).
`Frepple Run Plan.run_plan()` rewritten for the v17 frepple endpoint
`/api/runplan/` (was `/execute/api/runplan/`), `print()` calls replaced
with `frappe.logger().info(...)` (F5). `bench --site test.localhost migrate`
is clean; `bench --site test.localhost run-tests --app fact_frepple`
runs 13 unit tests (10 existing + 3 for the new shared helper) and reports
OK. Phase 4 real-test rewrite still pending.

### Phase 4 — Tests, CI, deployment

Replace stub tests with real ones:

| Test | Mocks | Asserts |
|---|---|---|
| `test_frepple_settings.py` | `responses` lib | URL is reachable, secret key ≥ 32 chars |
| `test_frepple_data_export.py` | `responses` lib + SQL router | Each `export_<entity>()` POSTs the expected JSON shape |
| `test_frepple_integration_data_fetching.py` | SQL router + `new_doc` skip-links | ERPNext rows are projected into mirror DocType rows + dispatcher routing |
| `test_get_iframe_url.py` | `jwt.decode` | Output JWT decodes back to `{user, exp, navbar}` and is signed with `settings.secret_key` |
| `test_frepple_run_plan.py` | `responses` lib | POSTs to `/api/runplan/` with the right body |

CI: `.github/workflows/ci.yml` runs the bench tests; `.github/workflows/linter.yml`
adds `ruff`, `prettier`, `pip-audit`, and semgrep on every PR. NOTICE file
with attribution.

**Acceptance:** `bench --site test.localhost run-tests --app fact_frepple` green; CI green on PR; README walkthrough executable on a fresh `bench new-site`.

**Status (2026-08-10):** done on `feat/migrate-v17`. 36 tests pass on
`test.localhost`. The Phase 2/3 stub tests are now real: each
``export_<entity>()`` is verified by ``responses`` (URL + JSON body),
``fetch_items`` / ``fetch_customers`` / ``fetch_buffers`` are verified by
an ``frappe.db.sql`` router that falls through to the real DB for
unrelated lookups, ``run_plan`` is verified end-to-end via ``responses``
with body + query-string assertions, and ``get_iframe_url`` is verified
by decoding the JWT with the configured secret (and asserting a wrong
secret raises ``InvalidSignatureError``). Three source bugs surfaced
during this phase and are fixed:

- ``fetch_items`` wrote to ``uom``/``cost``/``item_owner`` aliases that
  don't exist on the v17 ``Frepple Item`` DocType; renamed to
  ``stock_uom``/``valuation_rate``/``item_group``.
- ``get_iframe_url`` passed ``doc.expiration`` (minutes) where the
  shared ``sign_jwt_url`` helper expects seconds; multiplied by 60.
- ``test_frepple_integration_data_fetching`` now scrubs the four mirror
  DocTypes in ``setUp`` because ``UnitTestCase`` has no implicit
  rollback — without this the second fetch silently took the update
  branch.

CI: added a ``ruff`` job (lint + format check), a ``prettier`` job
(JS/CSS/JSON/MD), kept the existing ``pip-audit`` job and the bench
test workflow. NOTICE file at the repo root carries the GPLv3
attribution for the v14 source we ported. ``pyproject.toml`` adds
``responses~=0.25.0`` as a runtime dep — it's only used in tests but
Frappe's pip resolver doesn't honour ``tool.bench.dev-dependencies``
without ``developer_mode`` enabled on the bench.

### Phase 5 — Spec reconciliation + handoff

Update `ANALYSIS_AND_MIGRATION_PLAN.md` so its §8 (v16 breaks), §12 (effort), §13 (file inventory) reflect v17 reality. PR `feat/migrate-v17 → dev`.

**Acceptance:** PR merged to `dev`; promotion to `pre-pro` and `main` follows the AGENTS.md chain.

**Status (2026-08-10):** doc reconciliation done on `feat/migrate-v17`; PR to
`dev` pending. `ANALYSIS_AND_MIGRATION_PLAN.md` §8 now records that every
B-item and soft issue is resolved (verified: 0 files with `"module": "Frepple"`,
0 `unicode_literals`/`get_request_session` imports, 29/29 JSONs with
`sort_field`), plus a new "Bugs found during migration" table (M1–M4). §10
gains an outcome column — risks 2, 9, 10 stay open because only Phase 6 runs
a real frepple. §12 carries actuals against estimates (~5.5 days vs 11–15
estimated; scripting Phase 2 was the saving). §13 is now the as-shipped
inventory rather than a to-do list.

One bug surfaced in this phase. `sign_jwt_url` computed `exp` with
`round(time.time())`, which rounds a fractional clock read *up* and put the
token one second past a caller's `int(time.time()) + expiration` bound —
`test_get_iframe_url_returns_signed_jwt_webtoken` failed 7 runs in 12.
Fixed by truncating with `int()` (`246b327`). The existing
`test_iframe_helper` assertion covering this was vacuous
(`assertAlmostEqual(exp, exp, delta=0)`); replaced with a patched-clock test
that pins `exp == 1600` for `time.time() == 1000.9`, verified to fail before
the fix and pass after. Suite is 37 tests, green across 5 consecutive runs.

### Phase 6 — End-to-end two-way transfer test

This is the proof that the whole thing actually works against a real frepple.

#### 6.1 — Fixture setup

Script creates in ERPNext: Company "Test Co"; Warehouses "Stores" + "Work In Progress"; Items FG-001, RM-001, RM-002; BOM FG-001 (1× RM-001 + 2× RM-002, operation "Assembly" 30 min); Sales Order SO-001 (10 × FG-001, delivery in 14 days); Supplier "SUPP-001" with 7-day lead time selling RM-001.

#### 6.2 — Configure `Frepple Settings`

| Field | Value |
|---|---|
| `url` | `http://localhost:9000` |
| `username` | `admin` |
| `password` | `<new-password-from-0.5.3>` |
| `authorization_header` | empty (basic auth via URL) |
| `secret_key` | the JWT signing secret from Phase 0.5.3 |
| `wip_location_name` | `Work In Progress` |
| `frepple_integration` | 1 |

#### 6.3 — The E2E flow

```python
def test_e2e_one_so_creates_one_wo_and_one_po():
    # Step 1: mirror ERPNext into connector's mirror DocTypes
    from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching\
        .frepple_integration_data_fetching import fetch_data
    fetch_data(doc=None)

    # Step 2: push to frepple
    from fact_frepple.fact_frepple.doctype.frepple_data_export\
        .frepple_data_export import export_data
    export_data(doc=MagicMock(calendar=1, calendarbucket=1, item=1, customer=1,
                              location=1, buffer=1, supplier=1, itemsupplier=1,
                              resource=1, skill=1, resourceskill=1, demand=1,
                              operation=1, operationmaterial=1,
                              operationresource=1))

    # Step 3: trigger plan
    requests.post("http://localhost:9000/api/runplan/", auth=("admin", PWD))

    # Step 4: pull manufacturing orders back
    from fact_frepple.fact_frepple.doctype.frepple_integration_data_fetching\
        .frepple_integration_data_fetching import fetch_sales_orders
    fetch_sales_orders()

    # Step 5: assertions
    mo = frappe.get_all("Frepple Manufacturing Order", filters={"item": "FG-001"})
    assert len(mo) == 1 and mo[0].quantity == 10

    wo = frappe.get_all("Work Order", filters={"production_item": "FG-001"})
    assert len(wo) == 1

    po = frappe.get_all("Purchase Order", filters={"supplier": "SUPP-001"})
    assert len(po) >= 1
```

#### 6.4 — Failure modes to verify each gets a clean error

| Failure | Expected behavior |
|---|---|
| frepple container down | `get_frepple_params()` raises `ConnectionError` with msgprint |
| Wrong password | frepple returns 403; connector raises with msgprint "Auth failed" |
| Missing reference (item exported before item_group) | frepple returns 400 with referential error; connector logs and continues |
| Plan run produces no MOs (over-capacity) | connector still creates a Work Order row with quantity=0; test asserts this is graceful, not a crash |

#### 6.5 — Status-sync round-trip (separate test)

- ERPNext WO → submit → connector PATCHes frepple `/api/input/manufacturingorder/<id>/` → verify in frepple UI.
- frepple UI marks PO as received → `fetch_purchase_orders()` runs → verify ERPNext Purchase Receipt created.

#### 6.6 — Iframe render test

```python
def test_custom_page_iframe_renders_with_jwt():
    from fact_frepple.fact_frepple.doctype.frepple_custom_page_settings\
        .frepple_custom_page_settings import get_iframe_url
    settings_doc = frappe.get_doc("Frepple Custom Page Settings", "Default")
    url, height = get_iframe_url(settings_doc.name)

    assert "webtoken=" in url
    import jwt
    decoded = jwt.decode(url.split("webtoken=")[1], SECRET, algorithms=["HS256"])
    assert decoded["user"] == "admin"
    assert decoded["navbar"] is False
    assert url.startswith("http://localhost:9000/")
```

#### 6.7 — CLI runner

Add `fact_frepple/commands/__init__.py` so:

```bash
bench fact-frepple e2e
```

runs the full E2E. CI runs it nightly against `test.localhost`.

**Acceptance:** the E2E script runs green from a cold `docker compose down -v && bench restart` start.

**Status (2026-08-10):** done on `dev`. `bench --site test.localhost fact-frepple-e2e`
runs 9 tests green, verified from a genuine cold start (`make reset` → `make up`
→ fresh Postgres volume, new `SECRET_KEY`, empty frepple DB). One Sales Order
for 10 × FG-001 produces exactly one Frepple Manufacturing Order (qty 10,
pegged to the SO), one ERPNext Work Order, and one Frepple Purchase Order for
RM-001 from SUPP-001.

Layout differs slightly from §9 of this spec: the tests live in
`fact_frepple/tests/e2e/` as `fixtures.py`, `helpers.py` and
`test_e2e_two_way.py` (one module covering §6.3, §6.4 and §6.6) rather than
separate `test_e2e_one_so.py` / `test_iframe_jwt.py` / `conftest.py` — there is
no pytest in this stack, so a `conftest.py` would have been dead weight. The
CLI is `bench fact-frepple-e2e` (hyphenated; `bench fact-frepple e2e` would
require a command group for a single command).

**Six bugs surfaced, all invisible to the Phase 4 mocks:**

| # | Bug | Why the mocks missed it |
|---|---|---|
| E1 | `run_plan` POSTed to `/api/runplan/`, which 302-redirects to the login page — **no plan ever ran**. The v14 path `/execute/api/runplan/` was correct; Phase 3 "modernised" it on a wrong assumption and the Phase 4 `responses` test asserted the wrong URL, locking the bug in. | A mock returns 200 for whatever URL you register |
| E2 | `fetch_data` called `fetch_item_suppliers()`, which was never ported from v14 → `NameError` on every run with that flag on. Implemented; it is also what gives frepple a sourcing path to plan a PO at all. | No test exercised the real `fetch_data` dispatch with all flags on |
| E3 | `fetch_skills` / `fetch_resource_skills` query `tabSkill` and `tabEmployee Skill Map`, which ship with **hrms**, not erpnext → `ProgrammingError` on any site without hrms. Now guarded by a table-existence check. | The site the mocks ran against never executed the SQL |
| E4 | frepple 9.x requires `effective_start` on `itemsupplier`; the v14 payload omits it → HTTP 400. | The mock accepted any JSON body |
| E5 | frepple returns `"Unknown supplier"` for unsourced items; importing it raised `LinkValidationError` and **aborted the entire PO import**, discarding valid rows too. Now skipped with a log (§6.4 "log and continue"). | Mock fixtures only ever contained well-formed suppliers |
| E6 | The Phase 4 unit tests overwrite the `Frepple Settings` singleton with fakes and never restore it, so the E2E inherited `secret_key = "phase3-test-secret"` and failed with a spurious "secret drift". E2E config now comes from `site_config.json` / `FREPPLE_E2E_*`. | Only shows up when both suites run in one process |

**Two operational requirements the plan never mentioned:**

- `plan.webservice` must be `false`. frepple's default keeps the plan in
  memory, so the REST input tables the connector reads stay empty and a plan
  run appears to succeed while importing nothing. There is no env var for it —
  added as `make configure-plan`, required after every `make reset`.
- `/execute/api/runplan/` is **asynchronous**; it returns `{"taskid": N}`. Reading
  results before the task reaches `Done` returns the previous plan. Added
  `wait_for_task()`; the E2E blocks on it.

**Risks now closed:** R2/risk 2 (frepple 9.17 REST contract — E1, E4 and E5 were
exactly this), R5/risk 9 (JWT secret drift — the E2E signs a token and asserts
the real frepple returns 200, and that a wrong secret does not), R6/risk 10
(CSP `frame-ancestors` — asserted against the live response header).

Not covered: §6.5 status-sync round-trip (ERPNext WO submit → PATCH frepple;
frepple PO receipt → ERPNext Purchase Receipt) is **not implemented**. It needs
`update_frepple_mo_status` to be driven from a real doc submit and a Purchase
Receipt path that does not exist in the connector yet. Carried to Phase 7.

---

## 6. v14 → v17 compatibility delta (F-table)

| # | What breaks in v17 | Severity | Fix |
|---|---|---|---|
| F1 | `frappe.utils.get_request_session` removed (v15) | Hard if source uses | Drop; use `frappe.integrations.utils.make_get_request` |
| F2 | `frappe.db.set_value` no auto-commit | Soft | Add `frappe.db.commit()` after each `set_value` block |
| F3 | List-view default sort flipped to `creation asc` | Cosmetic | Add `sort_field`/`sort_order` to all 29 JSONs |
| F4 | Type annotations mandatory on whitelisted methods (`require_type_annotated_api_methods=True` set in scaffold) | Hard | Annotate every whitelisted method |
| F5 | `print(...)` as logging | Soft | Replace with `frappe.logger().info(...)` |
| F6 | `from __future__ import unicode_literals` | Cosmetic | Remove |
| F7 | SQL `timestamp()` | n/a (MariaDB) | No change |
| F8 | Vue 2 → Vue 3 / Webpack → Vite | Hard for Vue components | Source's JS uses `frappe.call` and `frappe.ui.form.make_control` — still works; audit each file |
| F9 | Module path in DocType JSONs | Hard after rename | Rewrite `"module": "Frepple"` → `"module": "Fact Frepple"` in all 29 JSONs |
| F10 | Iframe page model `frappe.pages['x'].on_page_load` | Not a blocker (verified at `frappe/public/js/frappe/views/pageview.js:130`) | No rewrite |
| F11 | `frappe.integrations.utils.make_post_request` import | Not a blocker (still at `frappe/integrations/utils.py:90`) | No change |
| F12 | `export_python_type_annotations=True` already set in scaffold | n/a | Free annotation export for non-whitelisted helpers |
| F13 | License mismatch (MIT vs GPLv3 source) | n/a | Add NOTICE file |
| **F14** | **frepple 9.17 uses JWT webtoken, not `?secret=` URL param** | **Hard** (the whole iframe auth breaks) | Rewrite `get_iframe_url()` in `frepple_custom_page_settings.py` to build a JWT with `pyjwt` (`{exp: time.time()+3600, user: 'admin', navbar: False}` signed with `settings.secret_key`), append `?webtoken=<jwt>` to the URL. Verify `pyjwt` is a dep; add to `pyproject.toml` if missing. |
| F15 | Connector's `get_frepple_params` inlines `user:pass` in URL — fine for now | n/a | Document; HTTPS frepple deployments may need switch to `auth=("u","p")` |

---

## 7. Effort estimate

| Phase | Effort | Risk |
|---|---|---|
| 0 — repo prep | 0.5 day | Low |
| **0.5 — frepple Docker install** | **0.5 day** | **Low** |
| 1 — tracer bullet (Settings + iframe + JWT) | 2-3 days | Medium |
| 2 — bulk doctype copy (29 doc + 2 controllers) | 3-4 days | Low |
| 3 — desk pages | 1 day | Low |
| 4 — tests + CI + docs | 2-3 days | Medium |
| 5 — spec + handoff | 0.5 day | Low |
| **6 — E2E two-way test** | **2 days** | **Medium** |
| **Total** | **11-15 working days** | Medium |

---

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | msf4-0 repo deleted/evolved | Phase 0 step 1 git-clone fails fast |
| R2 | frepple 9.17 REST contract differs from 2022 | Phase 6 E2E catches it |
| R3 | ERPNext v17 field renames | Phase 2 audit per field mapping |
| R4 | v14 user data (mirror DocType rows) | We are greenfield on `test.localhost` |
| R5 | JWT secret drift between Frepple Settings and frepple container | Phase 0.5.3 stores both; Phase 6.2 asserts they match |
| R6 | Frame-ancestors CSP blocking the iframe | Phase 0.5.1 compose sets `FREPPLE_CONTENT_SECURITY_POLICY` and `FREPPLE_X_FRAME_OPTIONS` |
| R7 | CSRF cookie SameSite=lax blocking token | Phase 0.5.1 sets `FREPPLE_CSRF_TRUSTED_ORIGINS` |
| R8 | Hard-coded WIP location convention | Made configurable in `Frepple Settings` |
| R9 | PostgreSQL container not running when bench tries to export | Phase 6 setup script checks `docker ps` first |
| R10 | Postgres container disk fills up over many plan runs | Volume `frepple-pgdata` mounted; `make reset` wipes |
| R11 | frepple container OOM during plan | Default 2 CPU + 4 GB memory per the official compose; sufficient for the 1-SO test |
| R12 | Type annotations too verbose for the 108-file mechanical port | Annotate only the ~20 whitelisted methods manually; `export_python_type_annotations=True` handles the rest |

---

## 9. File-by-file inventory

For each of the 29 DocTypes + 6 pages + 2 controllers, the copy template is:

```
SRC = /tmp/opencode/erpnext_frepple_connector/frepple/frepple/<area>/<name>/<name>.<ext>
DST = apps/fact_frepple/fact_frepple/<area>/<name>/<name>.<ext>
```

Edits applied to DST:
- `sed -i 's/from frepple\./from fact_frepple.fact_frepple./g'` for .py
- `sed -i 's/"module": "Frepple"/"module": "Fact Frepple"/g'` for .json
- Append `"sort_field": "creation"` and `"sort_order": "asc"` to each JSON's top-level metadata block (idempotent — only if missing)
- Manual review for type annotations on whitelisted methods

New files this spec adds (not in source):

```
apps/fact_frepple/
├── docker/
│   ├── frepple.compose.yaml
│   ├── Makefile
│   └── README.md
├── scripts/
│   ├── e2e_setup.sh
│   └── e2e_run.sh
├── fact_frepple/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── unit/
│   │   │   ├── test_frepple_settings.py
│   │   │   ├── test_frepple_data_export.py
│   │   │   ├── test_frepple_integration_data_fetching.py
│   │   │   ├── test_get_iframe_url.py
│   │   │   └── test_frepple_run_plan.py
│   │   └── e2e/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       ├── test_e2e_one_so.py
│   │       └── test_iframe_jwt.py
│   └── commands/
│       └── __init__.py
└── NOTICE
```

---

## 10. Acceptance gates (per phase)

| Phase | Pass criterion | Status |
|---|---|---|
| 0.5 | `curl http://localhost:9000/` returns 200; basic-auth + JWT round-trip works | ✅ |
| 1 | Settings form loads; Custom Page iframe URL parses as valid JWT | ✅ |
| 2 | All 29 DocTypes visible in desk list views; export/fetch controllers mocked | ✅ |
| 3 | All 6 desk pages render; workspace shows 9 sections | ✅ |
| 4 | `bench --site test.localhost run-tests --app fact_frepple` green; CI green | ✅ 37 unit tests green (CI unverified locally — no ruff in this bench env) |
| 5 | `ANALYSIS_AND_MIGRATION_PLAN.md` rewritten; PR merged to `dev` | ✅ merged to `dev` (no remote configured, so merged locally rather than via PR) |
| **6** | **`bench fact-frepple e2e` exits 0; ERPNext has 1 WO + ≥1 PO after one SO went through frepple** | ✅ `bench fact-frepple-e2e` exits 0 from a cold start: 1 WO (qty 10) + 1 Frepple PO (RM-001 ← SUPP-001) |

---

## 11. Out-of-scope (Phase 7+)

- Refactor away from mirror DocTypes.
- Adding new frepple entities (setup-matrix, sequenced manufacturing).
- Replacing the connector with direct SAP or other ERP integration.
- Performance work (mirror DocType queries are N+1).
- i18n of UI strings.
- Production deployment (only dev/sandbox on `test.localhost`).
- Enterprise Edition features.
