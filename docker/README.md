# frepple-dev (Docker)

Local frepple server for `fact_frepple` integration testing.

## Bring-up

```bash
cd apps/fact_frepple/docker
sudo make up             # docker compose -f frepple.compose.yaml up -d
sudo make logs           # tail logs; wait for "Starting web server"
sudo make configure-plan # REQUIRED — see "Persisting the plan" below
```

First boot takes ~60-90s: entrypoint creates three databases
(default + two scenarios), runs all migrations, then loads demo data
into `scenario1` and `scenario2`.

## Smoke

```bash
curl -u admin:admin http://localhost:9000/api/input/demand/?format=json
# expect: []   (no demands yet, but 200 OK)
```

Web UI: <http://localhost:9000/> (default `admin` / `admin`).

## First-login hardening

### 1. Change the admin password

The default `admin` / `admin` is well-known. Change it from the
frepple Web UI *or* via `frepplectl` inside the container:

```bash
sudo docker exec -it frepple-dev frepplectl changepassword admin
```

### 2. Generate a JWT signing secret

frepple 9.17 uses JWT webtokens for iframe auth (the v14 connector's
`?secret=<key>` URL param is dead — see migration spec F14). The
secret is the Django `SECRET_KEY`, stored at
`/etc/frepple/djangosettings.py` inside the container:

```bash
NEW_SECRET=$(openssl rand -hex 32)
sudo docker exec frepple-dev sed -i "s|^SECRET_KEY = .*|SECRET_KEY = \"$NEW_SECRET\"|" /etc/frepple/djangosettings.py
sudo docker compose -f frepple.compose.yaml restart frepple
```

> The same secret must be pasted into `Frepple Settings.secret_key`
> in the ERPNext site — they must match or the iframe returns 401.

### 3. Verify the JWT round-trip

```bash
sudo apt-get install -y python3-jwt   # or: pip install PyJWT
SECRET=$(sudo docker exec frepple-dev grep '^SECRET_KEY' /etc/frepple/djangosettings.py | cut -d'"' -f2)
TOKEN=$(python3 -c "import jwt, time; print(jwt.encode({'exp': round(time.time())+600, 'user':'admin', 'navbar':False}, '$SECRET', algorithm='HS256'))")
curl -i "http://localhost:9000/?webtoken=$TOKEN" | head -1
# expect: HTTP/1.1 200 OK
```

A 200 here means the secret is correctly shared between the container
and your shell — the same value will be valid in the Frappe iframe.

## Persisting the plan (required)

frepple defaults `plan.webservice` to `true`, which keeps the computed
plan **in memory**. The connector reads results from the REST input
tables (`/api/input/manufacturingorder/`, `/api/input/purchaseorder/`),
so in that mode a plan run appears to succeed and imports nothing —
`generate_result()` returns zero rows with no error anywhere. This cost
a full debugging pass during Phase 6.

There is no environment variable for it (the value lives in frepple's
`common_parameter` table), so it must be set after every `make reset`:

```bash
sudo make configure-plan   # sets plan.webservice = false
```

## The task API is asynchronous

`POST /execute/api/runplan/` **queues** a task and returns immediately:

```json
{"taskid": 5, "message": "Successfully launched task"}
```

Reading the plan before that task reaches `Done` returns the *previous*
plan, or nothing at all. `run_plan()` returns the payload above; use
`fact_frepple...frepple_run_plan.wait_for_task(taskid)` to block.

Note the endpoint is `/execute/api/runplan/`, **not** `/api/runplan/` —
the latter 302-redirects to the login page, so a plan silently never
runs.

## E2E credentials

`bench fact-frepple-e2e` and the Phase 6 tests read their connection
details from `site_config.json` rather than from `Frepple Settings`
(the unit tests overwrite that singleton with fakes):

```json
"frepple_e2e": {
  "url": "http://localhost:9000",
  "username": "admin",
  "password": "<your admin password>",
  "secret_key": "<the container's SECRET_KEY>",
  "wip_location_name": "Work In Progress"
}
```

`FREPPLE_E2E_URL` / `_USERNAME` / `_PASSWORD` / `_SECRET_KEY` environment
variables override the site config, so CI never has to write secrets to
disk.

## Reset (nuke volumes)

```bash
sudo make reset    # docker compose -f frepple.compose.yaml down -v
sudo make up
```

Use this whenever fixtures drift and the plan runs produce garbage
results. The `frepple-pgdata` volume holds the Postgres data, so a
reset wipes all scenarios, users, and uploaded CSVs.

## Why the port 8003 in `frame-ancestors`

The `bench` dev server listens on `:8003` by default (see
`/home/frappeuser/fact/planing/sites/common_site_config.json` →
`webserver_port`). The iframe is loaded from
`http://test.localhost:8003/desk/...`, so `frame-ancestors` must
explicitly allow that origin or the browser refuses to render the
frepple page.

## Files

| File | Purpose |
|---|---|
| `frepple.compose.yaml` | Two-service stack: `frepple` (community 9.17) + `postgres:16` side-car. Named volumes for config, logs, and pgdata. |
| `Makefile` | Convenience wrappers (`up`, `down`, `reset`, `logs`, `pull`). |
| `README.md` | This file. |
