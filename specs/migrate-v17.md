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
| `test_frepple_settings.py` | n/a | URL is reachable, secret key ≥ 32 chars |
| `test_frepple_data_export.py` | `responses` lib | Each `export_<entity>()` POSTs the expected JSON shape |
| `test_frepple_integration_data_fetching.py` | `responses` lib | Pulled JSON is parsed into mirror DocType rows |
| `test_get_iframe_url.py` | `jwt.encode` | Output JWT decodes back to `{user, exp, navbar}` and is signed with `settings.secret_key` |
| `test_frepple_run_plan.py` | `responses` lib | POSTs to `/api/runplan/` with the right body |

CI: `.github/workflows/ci.yml` adds `bench --site test.localhost run-tests --app fact_frepple` + `ruff` + `prettier` + `pip-audit`. NOTICE file with attribution.

**Acceptance:** `bench --site test.localhost run-tests --app fact_frepple` green; CI green on PR; README walkthrough executable on a fresh `bench new-site`.

### Phase 5 — Spec reconciliation + handoff

Update `ANALYSIS_AND_MIGRATION_PLAN.md` so its §8 (v16 breaks), §12 (effort), §13 (file inventory) reflect v17 reality. PR `feat/migrate-v17 → dev`.

**Acceptance:** PR merged to `dev`; promotion to `pre-pro` and `main` follows the AGENTS.md chain.

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

| Phase | Pass criterion |
|---|---|
| 0.5 | `curl http://localhost:9000/` returns 200; basic-auth + JWT round-trip works |
| 1 | Settings form loads; Custom Page iframe URL parses as valid JWT |
| 2 | All 29 DocTypes visible in desk list views; export/fetch controllers mocked |
| 3 | All 6 desk pages render; workspace shows 9 sections |
| 4 | `bench --site test.localhost run-tests --app fact_frepple` green; CI green |
| 5 | `ANALYSIS_AND_MIGRATION_PLAN.md` rewritten; PR merged to `dev` |
| **6** | **`bench fact-frepple e2e` exits 0; ERPNext has 1 WO + ≥1 PO after one SO went through frepple** |

---

## 11. Out-of-scope (Phase 7+)

- Refactor away from mirror DocTypes.
- Adding new frepple entities (setup-matrix, sequenced manufacturing).
- Replacing the connector with direct SAP or other ERP integration.
- Performance work (mirror DocType queries are N+1).
- i18n of UI strings.
- Production deployment (only dev/sandbox on `test.localhost`).
- Enterprise Edition features.
