# Hermes Ollama dashboard plugin

A Hermes Agent dashboard plugin (see
[Extending the Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard))
that surfaces this backend's projects, tasks, hardware telemetry, and
HSE progression inside Hermes Agent's own web UI, instead of building a
separate Next.js frontend for it.

Built against the plugin contract verified from NousResearch's own
[example plugin](https://github.com/NousResearch/hermes-example-plugins/tree/main/example-dashboard)
(manifest.json shape, `window.__HERMES_PLUGIN_SDK__`/`window.__HERMES_PLUGINS__`
globals, `plugin_api.py`'s `router = APIRouter()` convention) — **not**
exercised end-to-end against a real Hermes Agent install from this
sandbox (same caveat as `config/hermes_agent_hooks/aegis_gate.py`:
`hermes-agent.nousresearch.com` is unreachable here). `manifest.json`'s
`tab.position` value (`"after:memory"`) is a plausible anchor modeled on
the one example available, not a verified list of valid tab ids —
adjust it if the tab doesn't land where you expect.

## Install

```bash
mkdir -p ~/.hermes/plugins/hermes-ollama
cp -r config/hermes_agent_dashboard ~/.hermes/plugins/hermes-ollama/dashboard
```

If the Hermes Ollama backend isn't running on the default
`http://127.0.0.1:8000`, set `HERMES_OLLAMA_BACKEND_URL` in the
environment Hermes Agent itself runs in before starting it — `plugin_api.py`
reads it at import time.

Restart Hermes Agent's dashboard; a "Hermes Ollama" tab should appear.

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
