/**
 * Hermes Ollama Dashboard Plugin
 *
 * Surfaces the Hermes Ollama backend's own state — projects, tasks,
 * hardware telemetry, HSE progression — inside Hermes Agent's dashboard,
 * via the Plugin SDK (window.__HERMES_PLUGIN_SDK__). No build step: a
 * plain IIFE using SDK globals, same structure as NousResearch's own
 * example-dashboard plugin (github.com/NousResearch/hermes-example-plugins).
 *
 * Every SDK.fetchJSON() call below hits this plugin's own backend route
 * (plugin_api.py, mounted at /api/plugins/hermes-ollama/<name>), which in
 * turn proxies to the Hermes Ollama backend itself (default
 * http://127.0.0.1:8000, see plugin_api.py's BACKEND_URL) — the browser
 * never talks to that backend directly.
 *
 * Visual style: amber/CRT terminal console, scoped entirely under
 * `.ho-crt` so it never leaks into the rest of the host dashboard.
 * Every readout on screen is backed by a real value from the endpoints
 * below — no decorative placeholders (no fake waveform, no invented
 * network stats). "Link" latency is measured for real: wall-clock time
 * of this plugin's own fetchJSON round trip to plugin_api.py.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect, useRef } = SDK.hooks;
  const { cn } = SDK.utils;

  const API_BASE = "/api/plugins/hermes-ollama";

  // ---------------------------------------------------------------------
  // Scoped CRT styling — injected once, namespaced under .ho-crt so it
  // never bleeds into the rest of Hermes Agent's own UI.
  // ---------------------------------------------------------------------
  const STYLE_ID = "ho-crt-styles";
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .ho-crt {
        --ho-bg: #0a0805;
        --ho-panel: #120d08;
        --ho-line: #3a2c14;
        --ho-amber: #e8a83d;
        --ho-amber-dim: #8a662a;
        --ho-amber-bright: #ffc966;
        --ho-text: #e9d9b8;
        --ho-text-dim: #a8926a;
        --ho-bad: #e05a4d;
        --ho-good: #8fbf6a;
        position: relative;
        background: var(--ho-bg);
        color: var(--ho-text);
        font-family: "JetBrains Mono", "Cascadia Code", ui-monospace, Menlo, Consolas, monospace;
        padding: 16px;
        border-radius: 4px;
        isolation: isolate;
      }
      .ho-crt::after {
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        z-index: 5;
        background: repeating-linear-gradient(
          to bottom,
          rgba(255, 200, 100, 0.025) 0px,
          rgba(255, 200, 100, 0.025) 1px,
          transparent 1px,
          transparent 3px
        );
        border-radius: inherit;
      }
      @media (prefers-reduced-motion: no-preference) {
        .ho-crt .ho-blink { animation: ho-blink 1.1s steps(1) infinite; }
      }
      @keyframes ho-blink { 50% { opacity: 0.15; } }
      .ho-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 14px;
      }
      .ho-panel {
        position: relative;
        border: 1px solid var(--ho-line);
        background: var(--ho-panel);
        padding: 12px 14px;
      }
      .ho-panel::before, .ho-panel::after,
      .ho-corner-tl::before, .ho-corner-br::after { content: none; }
      .ho-panel .ho-corner {
        position: absolute;
        width: 8px;
        height: 8px;
        border-color: var(--ho-amber-dim);
        z-index: 1;
      }
      .ho-panel .ho-corner.tl { top: -1px; left: -1px; border-top: 1px solid; border-left: 1px solid; }
      .ho-panel .ho-corner.tr { top: -1px; right: -1px; border-top: 1px solid; border-right: 1px solid; }
      .ho-panel .ho-corner.bl { bottom: -1px; left: -1px; border-bottom: 1px solid; border-left: 1px solid; }
      .ho-panel .ho-corner.br { bottom: -1px; right: -1px; border-bottom: 1px solid; border-right: 1px solid; }
      .ho-panel-title {
        font-size: 11px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--ho-amber);
        border-bottom: 1px solid var(--ho-line);
        padding-bottom: 8px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .ho-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-size: 12.5px;
        line-height: 1.7;
        gap: 12px;
      }
      .ho-row .ho-label { color: var(--ho-text-dim); white-space: nowrap; }
      .ho-row .ho-value { color: var(--ho-text); font-variant-numeric: tabular-nums; }
      .ho-bar-track {
        height: 5px;
        background: #1c1509;
        border: 1px solid var(--ho-line);
        width: 100%;
        margin-top: 2px;
        margin-bottom: 6px;
      }
      .ho-bar-fill {
        height: 100%;
        background: var(--ho-amber);
        transition: width 0.4s ease;
      }
      .ho-bar-fill.warn { background: var(--ho-bad); }
      .ho-badge {
        font-size: 10.5px;
        letter-spacing: 0.04em;
        padding: 1px 7px;
        border: 1px solid var(--ho-amber-dim);
        color: var(--ho-amber);
        text-transform: uppercase;
      }
      .ho-badge.dim { color: var(--ho-text-dim); border-color: var(--ho-line); }
      .ho-badge.bad { color: var(--ho-bad); border-color: var(--ho-bad); }
      .ho-badge.good { color: var(--ho-good); border-color: var(--ho-good); }
      .ho-muted { color: var(--ho-text-dim); font-size: 12px; }
      .ho-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        margin-right: 6px;
      }
      .ho-dot.up { background: var(--ho-good); }
      .ho-dot.down { background: var(--ho-bad); }
      .ho-alert-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
    `;
    document.head.appendChild(style);
  }

  // ---------------------------------------------------------------------
  // Data + real link-latency measurement
  // ---------------------------------------------------------------------
  function useBackendResource(path) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const [latencyMs, setLatencyMs] = useState(null);

    useEffect(function () {
      let cancelled = false;
      setLoading(true);
      const t0 = performance.now();
      SDK.fetchJSON(API_BASE + path)
        .then(function (json) {
          if (!cancelled) {
            setLatencyMs(Math.round(performance.now() - t0));
            setData(json);
            setError(null);
          }
        })
        .catch(function (err) {
          if (!cancelled) {
            setLatencyMs(null);
            setError(String((err && err.message) || err));
          }
        })
        .finally(function () {
          if (!cancelled) { setLoading(false); }
        });
      return function () { cancelled = true; };
    }, []);

    return { data: data, error: error, loading: loading, latencyMs: latencyMs };
  }

  function Corners() {
    return React.createElement(React.Fragment, null,
      React.createElement("span", { className: "ho-corner tl" }),
      React.createElement("span", { className: "ho-corner tr" }),
      React.createElement("span", { className: "ho-corner bl" }),
      React.createElement("span", { className: "ho-corner br" }),
    );
  }

  function Panel(props) {
    return React.createElement("div", { className: "ho-panel" },
      React.createElement(Corners, null),
      React.createElement("div", { className: "ho-panel-title" },
        React.createElement("span", null, props.title),
        props.right || null,
      ),
      props.children,
    );
  }

  function Row(props) {
    return React.createElement("div", { className: "ho-row" },
      React.createElement("span", { className: "ho-label" }, props.label),
      React.createElement("span", { className: "ho-value" }, props.value),
    );
  }

  function Bar(props) {
    // props.pct: 0-100 real percentage. warn: true past a real threshold.
    const pct = Math.max(0, Math.min(100, props.pct || 0));
    return React.createElement("div", { className: "ho-bar-track" },
      React.createElement("div", {
        className: cn("ho-bar-fill", props.warn ? "warn" : ""),
        style: { width: pct + "%" },
      }),
    );
  }

  function LinkBadge(props) {
    // Real connectivity + real measured round-trip latency to plugin_api.py.
    if (props.error) {
      return React.createElement("span", { className: "ho-badge bad" },
        React.createElement("span", { className: "ho-dot down ho-blink" }), "link down");
    }
    if (props.latencyMs == null) {
      return React.createElement("span", { className: "ho-badge dim" }, "linking…");
    }
    return React.createElement("span", { className: "ho-badge good" },
      React.createElement("span", { className: "ho-dot up" }), props.latencyMs + "ms");
  }

  function ErrorNote(message) {
    return React.createElement("p", { className: "ho-muted" }, message);
  }

  // ---------------------------------------------------------------------
  // Panels — every field below maps 1:1 to a real backend value.
  // ---------------------------------------------------------------------
  function SystemPanel() {
    const { data, error, loading, latencyMs } = useBackendResource("/system-status");
    let body;
    if (loading) { body = ErrorNote("Reading system status…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else {
      const gpu = data.gpu;
      body = React.createElement("div", { className: "flex flex-col" },
        gpu
          ? React.createElement(React.Fragment, null,
              React.createElement(Row, { label: "GPU VRAM", value: gpu.vram_used_gb + " / " + gpu.vram_total_gb + " GB" }),
              React.createElement(Bar, { pct: gpu.vram_used_pct, warn: gpu.vram_used_pct >= 85 }),
              React.createElement(Row, { label: "GPU temp", value: gpu.temp_c === null ? "n/a (no vendor tool)" : gpu.temp_c + "°C" }),
              React.createElement(Row, { label: "GPU load", value: gpu.load_pct + "%" }),
            )
          : React.createElement(Row, { label: "GPU", value: "not detected" }),
        React.createElement(Row, { label: "CPU load", value: data.cpu_load_pct + "%" }),
        React.createElement(Bar, { pct: data.cpu_load_pct }),
        React.createElement(Row, { label: "RAM", value: data.ram_used_gb + " / " + data.ram_total_gb + " GB" }),
        React.createElement(Bar, { pct: (data.ram_used_gb / data.ram_total_gb) * 100 }),
        React.createElement(Row, { label: "Disk free", value: data.disk_free_gb + " GB" }),
        React.createElement(Row, { label: "Models loaded", value: data.loaded_models.length }),
        data.alerts && data.alerts.length > 0
          ? React.createElement("div", { className: "ho-alert-list" },
              data.alerts.map(function (alert, i) {
                return React.createElement("span", { key: i, className: "ho-badge bad" }, alert);
              }),
            )
          : null,
      );
    }
    return React.createElement(Panel, { title: "System", right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }) }, body);
  }

  function ProjectsPanel() {
    const { data, error, loading, latencyMs } = useBackendResource("/projects");
    let body;
    if (loading) { body = ErrorNote("Reading projects…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else if (data.length === 0) { body = ErrorNote("No projects yet."); }
    else {
      body = React.createElement("div", { className: "flex flex-col" },
        data.map(function (project) {
          return React.createElement("div", { key: project.id, className: "ho-row" },
            React.createElement("span", { className: "ho-value" }, project.name),
            React.createElement("span", { className: cn("ho-badge", project.status === "active" ? "good" : "dim") }, project.status),
          );
        }),
      );
    }
    return React.createElement(Panel, { title: "Projects", right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }) }, body);
  }

  function TasksPanel() {
    const { data, error, loading, latencyMs } = useBackendResource("/tasks");
    let body;
    if (loading) { body = ErrorNote("Reading tasks…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else {
      const counts = {};
      data.forEach(function (task) { counts[task.status] = (counts[task.status] || 0) + 1; });
      const statuses = Object.keys(counts);
      body = statuses.length === 0
        ? ErrorNote("No tasks yet.")
        : React.createElement("div", { className: "flex flex-col" },
            statuses.map(function (status) {
              return React.createElement(Row, { key: status, label: status, value: counts[status] });
            }),
            React.createElement(Row, { label: "total", value: data.length }),
          );
    }
    return React.createElement(Panel, { title: "Tasks", right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }) }, body);
  }

  function ProgressionPanel() {
    const { data, error, loading, latencyMs } = useBackendResource("/progression");
    let body;
    if (loading) { body = ErrorNote("Reading HSE progression…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else {
      const pct = data.success_rate === null ? null : Math.round(data.success_rate * 100);
      body = React.createElement("div", { className: "flex flex-col" },
        React.createElement(Row, { label: "Success rate", value: pct === null ? "n/a" : pct + "%" }),
        pct !== null ? React.createElement(Bar, { pct: pct }) : null,
        React.createElement(Row, { label: "Tasks succeeded", value: data.tasks_succeeded + " / " + data.tasks_terminal }),
        React.createElement(Row, { label: "Skills validated", value: data.skills_validated }),
        React.createElement(Row, { label: "Skills in review", value: data.skills_in_review }),
        React.createElement(Row, { label: "Skills total", value: data.skills_total }),
      );
    }
    return React.createElement(Panel, { title: "Self-Evolution (HSE)", right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }) }, body);
  }

  function Header() {
    const [now, setNow] = useState(new Date());
    useEffect(function () {
      const id = setInterval(function () { setNow(new Date()); }, 1000);
      return function () { clearInterval(id); };
    }, []);
    return React.createElement("div", { className: "flex items-center justify-between", style: { marginBottom: "14px" } },
      React.createElement("div", { style: { fontSize: "13px", letterSpacing: "0.12em", color: "var(--ho-amber-bright)" } }, "HERMES // OLLAMA"),
      React.createElement("div", { className: "ho-muted", style: { fontVariantNumeric: "tabular-nums" } }, now.toLocaleTimeString()),
    );
  }

  function HermesOllamaDashboard() {
    return React.createElement("div", { className: "ho-crt" },
      React.createElement(Header, null),
      React.createElement("div", { className: "ho-grid" },
        React.createElement(SystemPanel, null),
        React.createElement(ProjectsPanel, null),
        React.createElement(TasksPanel, null),
        React.createElement(ProgressionPanel, null),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-ollama", HermesOllamaDashboard);
})();
