# Isolated server deployment

The backend, engine, SMS worker, and maintenance worker run in the separate
`blood-dispatch` Docker Compose project. GitHub Pages continues to host the frontend.
The API binds only to `127.0.0.1:25001`; an HTTPS reverse proxy exposes its own hostname.
No existing application's containers, networks, or databases are reused.

## Deployed endpoints

- Frontend: https://sharlmon.github.io/blood-dispatch-network/
- API: https://blood-dispatch.169.58.141.254.sslip.io
- Readiness: https://blood-dispatch.169.58.141.254.sslip.io/api/ready

The API hostname uses IP-based wildcard DNS and a public ACME certificate. Caddy's
existing routes remain unchanged; only this hostname's route was added and gracefully
loaded. Existing project containers retained their IDs and uptimes during deployment.

## Current public synthetic demo

The deployed demo deliberately uses `APP_ENV=demo` and `AUTH_DISABLED=1`, as requested.
`DEMO_AUTH=bypass` also skips the browser-local demo account screen.
Web visitors share the demo operator identity and can change synthetic requests and
inventory. It is not an authenticated clinical deployment. SMS remains in Africa's
Talking **sandbox**, with registered simulator senders only. The historical clock is
31 October 2026, 00:58:20 EAT, and stock is from 30 October.

For authenticated use, configure Clerk, actual organization-to-facility mappings,
`APP_ENV=production`, and `AUTH_DISABLED=0`; the existing production startup checks
remain enforced. Rebuild Pages with the corresponding Clerk publishable key and
without `DEMO_AUTH`. Do not put real patient data into the public demo.

## Files and storage

- Application: `/opt/blood-dispatch-network`.
- Workflow and engine SQLite: `/srv/blood-dispatch/state` (UID/GID 10001).
- Synthetic CSVs and fitted arrival model: `/srv/blood-dispatch/dataset` (mounted read-only).
- Private environment: `backend/deploy/private.env` (0600; ignored by Git).
- Compose definition: `backend/deploy/compose.yaml`.

Use separate absolute paths for the two databases:

```dotenv
DB_PATH=/var/lib/blood-dispatch/workflow.sqlite
ENGINE_DB_PATH=/var/lib/blood-dispatch/engine.sqlite
DATA_DIR=/dataset
SETTINGS_FILE=/app/backend/config/settings.sms-demo.yaml
RESULTS_DIR=/app/results
CORS_ORIGINS=https://sharlmon.github.io
```

Set sandbox keys and sender registrations privately using the SMS guide. The image
excludes `.env`, source datasets, local databases, and development environments.
Containers run as UID 10001 with a read-only root filesystem, bounded memory/CPU,
rotated logs, and persistent storage belonging only to this project.

## Start and inspect

From `/opt/blood-dispatch-network/backend/deploy`:

```sh
docker compose build api
# First initialization only. This refuses to overwrite an imported stock snapshot.
docker compose run --rm api python -m flask --app wsgi ingest-data
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:25001/api/ready
docker compose exec api python -m flask --app wsgi sms-status
```

Provide `eta_model.json` in the dataset directory before startup. API readiness must
report both engine and inventory loaded. The worker containers wait for the API's
readiness health check. Never run `docker compose down` in another project's directory.

Add only this project's hostname to the HTTPS gateway, validate its complete candidate
configuration, back up the previous file, and gracefully reload. Existing hostname
routes must be preserved. Do not restart the existing gateway or change its ports.

After HTTPS and CORS pass, deploy Pages with its API address:

```sh
DEMO_AUTH=bypass NUXT_PUBLIC_API_BASE=https://YOUR_API_HOST scripts/deploy-pages.sh
```

Check the served page's `apiBase` and execute a golden request through the public API.
The homepage's explicitly labelled example may still use mock data; submitted live
requests must use the backend. Keep Africa's Talking callback secrets out of public documentation.

## SMS callback compatibility tunnel

The sandbox dashboard rejected the alternate hostname update, so the original saved
ngrok hostname is now served from the VPS by `blood-dispatch-tunnel`. It forwards to
`http://api:5000` on this project's Docker network. The laptop ngrok agent was stopped;
SMS no longer relies on the laptop. Keep the existing inbound and delivery callback
URLs and tokens unchanged in the sandbox dashboard.

The optional overlay is `backend/deploy/compose.tunnel.yaml`. Store the ngrok token
in private `backend/deploy/tunnel.env` as `NGROK_AUTHTOKEN` (0600; ignored by Git).

```sh
docker compose -f compose.yaml -f compose.tunnel.yaml up -d --no-deps tunnel
```

Only one agent can own this saved endpoint. Do not restart a laptop agent with the
same hostname. The public web frontend continues to use the direct HTTPS API hostname.
The ngrok inspector is disabled and its management port is not published.

## Backups

```sh
docker compose exec api python -m flask --app wsgi backup-db \
  --directory /var/lib/blood-dispatch/backups
```

Copy backups off-host separately. Keep the synthetic source dataset and fitted model.
Switching or restoring workflow files requires stopping only this project's services.
Do not overwrite active SQLite files or reset consumed inventory to repeat a demo.
