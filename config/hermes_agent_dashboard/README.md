# Hermes Ollama dashboard plugin

A Hermes Agent dashboard plugin (see
[Extending the Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard))
that surfaces this backend's projects, tasks, hardware telemetry, and
HSE progression inside Hermes Agent's own web UI, instead of building a
separate Next.js frontend for it.

Built against the plugin contract verified from NousResearch's own
[example plugin](https://github.com/NousResearch/hermes-example-plugins/tree/main/example-dashboard)
(manifest.json shape, `window.__HERMES_PLUGIN_SDK__`/`window.__HERMES_PLUGINS__`
globals, `plugin_api.py`'s `router = APIRouter()` convention) — **confirmed
working end-to-end on real hardware** (RX 6800, native Windows Ollama,
Hermes Agent v0.19.0): the tab renders, and all four cards show real,
correct data (a real project, a real task with its full history, real
HSE stats, real GPU/CPU/RAM figures).

Two real bugs were found and fixed getting there — see "Install" below
for the one that affects you, and "Troubleshooting" for the one that's
on Hermes Agent's own web build, not this plugin.

## Install

```bash
mkdir -p ~/.hermes/plugins/hermes-ollama
cp -r config/hermes_agent_dashboard ~/.hermes/plugins/hermes-ollama/dashboard
```

**Then, critically, add this to `~/.hermes/config.yaml`** — copying the
files alone is *not* enough:

```yaml
plugins:
  enabled:
    - hermes-ollama
```

Without it, the plugin still shows up on the `/plugins` page under
"dashboard-only extensions" with a working-looking "Open" link, but every
API route it needs 404s (`"Plugin not found"`) and the tab silently falls
back to the Sessions page when clicked. Hermes Agent's own
`_is_active()` gate (`hermes_cli/web_server.py`) requires a `"user"`-source
plugin like this one to be explicitly opted in — found by capturing the
real browser request and tracing the 404 back to that gate.

If the Hermes Ollama backend isn't running on the default
`http://127.0.0.1:8000`, set `HERMES_OLLAMA_BACKEND_URL` in the
environment Hermes Agent itself runs in before starting it — `plugin_api.py`
reads it at import time.

**Restart** `hermes dashboard` afterwards — both the plugin-enable change
and (the first time) the web build are picked up once, at process start,
not re-checked per request.

## Troubleshooting

**`hermes dashboard` fails to build** (`tsc`/`vite build` errors,
`Cannot find module '...\node_modules\typescript\bin\tsc'`): this is
Hermes Agent's own npm workspace, not this plugin — its `typescript`
package was installed with a missing `bin/` directory on a fresh
install. Fix from `~/.hermes/hermes-agent`:
`npm install typescript --workspace web` (or delete
`node_modules/typescript` first, then reinstall, if a version is already
present but broken).

**`/system-status` card times out (502)**: the Windows GPU/CPU/RAM
telemetry path (`backend/monitoring/gpu_monitor.py`) shells out to
PowerShell per metric, which took ~5s in testing — right at
`plugin_api.py`'s `_get_json()` timeout. Bumped to 10s here; raise it
further if your machine is slower.

## What it shows

Four read-only cards, refreshed on tab open:

- **System** — GPU VRAM/temperature/load (or "not detected" without
  ROCm), CPU/RAM/disk, loaded Ollama models, active threshold alerts.
- **Projects** — every project and its status (active/archived).
- **Tasks** — task counts grouped by status.
- **Self-Evolution (HSE)** — task success rate, skills validated /
  in review / total.

## Why a proxy (`plugin_api.py`), not a direct browser fetch

`dist/index.js` runs in the browser, inside Hermes Agent's own web app —
a different origin than the Hermes Ollama backend, whose CORS is
deliberately locked to `http://localhost:3000` (see `backend/main.py`).
`plugin_api.py` runs server-side, inside Hermes Agent's own process, and
proxies each request to the real backend — no CORS involved, and no
need to widen this backend's CORS policy just for the plugin.

## Testing

The proxy logic in `plugin_api.py` is unit tested directly against a
fake HTTP backend, not the real Hermes Ollama server — see
`backend/tests/test_hermes_dashboard_plugin.py`. `dist/index.js` itself
has no automated test: it depends on `window.__HERMES_PLUGIN_SDK__`,
which only exists inside a running Hermes Agent dashboard.
