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
  // `reloadKey` is a plain counter bumped by the Launch panel after a
  // successful create — re-running the effect is how a freshly created
  // project/task shows up without a page reload.
  function useBackendResource(path, reloadKey) {
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
    }, [path, reloadKey]);

    return { data: data, error: error, loading: loading, latencyMs: latencyMs };
  }

  function postJSON(path, body) {
    return SDK.fetchJSON(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
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
  function SystemPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource("/system-status", props.reloadKey);
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

  function ProjectsPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource("/projects", props.reloadKey);
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

  function TasksPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource("/tasks", props.reloadKey);
    let body;
    if (loading) { body = ErrorNote("Reading tasks…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else {
      const counts = {};
      data.forEach(function (task) { counts[task.status] = (counts[task.status] || 0) + 1; });
      const statuses = Object.keys(counts);
      // Newest first, so a task just created (from /tache, the REST API, or
      // an agent) is visible at a glance without scrolling.
      const recent = data.slice().sort(function (a, b) {
        return String(b.created_at).localeCompare(String(a.created_at));
      });
      body = statuses.length === 0
        ? ErrorNote("No tasks yet.")
        : React.createElement("div", { className: "flex flex-col" },
            recent.map(function (task) {
              return React.createElement("div", { key: task.id, className: "ho-row" },
                React.createElement("span", { className: "ho-value", title: task.description || task.title },
                  task.title),
                React.createElement("span", {
                  className: cn("ho-badge", task.status === "done" ? "good" : task.status === "blocked" ? "bad" : "dim"),
                }, task.status),
              );
            }),
            React.createElement(Row, { label: "total", value: data.length }),
          );
    }
    return React.createElement(Panel, { title: "Tasks (Kronos)", right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }) }, body);
  }

  function ProgressionPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource("/progression", props.reloadKey);
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

  function AgentActivityPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource("/messages?limit=25", props.reloadKey);
    let body;
    if (loading) { body = ErrorNote("Reading agent bus…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else if (data.length === 0) { body = ErrorNote("No agent traffic yet."); }
    else {
      // The bus returns newest-first already; render from/to + message type,
      // which is the whole point of this panel — the end state of a task
      // never shows which agent escalated, validated, or refused what.
      body = React.createElement("div", { className: "flex flex-col" },
        data.map(function (msg) {
          const isBad = msg.type === "ESCALATION" || msg.type === "REFUSAL";
          const time = String(msg.timestamp || "").slice(11, 19);
          return React.createElement("div", { key: msg.id, className: "ho-row" },
            React.createElement("span", {
              className: "ho-label",
              title: JSON.stringify(msg.payload || {}, null, 2),
            }, time + "  " + msg.from + " → " + msg.to),
            React.createElement("span", {
              className: cn("ho-badge", isBad ? "bad" : "dim"),
            }, msg.type),
          );
        }),
      );
    }
    return React.createElement(Panel, {
      title: "Agent activity (bus)",
      right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }),
    }, body);
  }

  function SecurityPanel(props) {
    const { data, error, loading, latencyMs } = useBackendResource(
      "/approvals?status=pending",
      props.reloadKey,
    );
    const [busy, setBusy] = useState(null);
    const [note, setNote] = useState(null);

    function decide(approval, approved) {
      setBusy(approval.id);
      setNote(null);
      postJSON("/approvals/" + approval.id, { approved: approved })
        .then(function () {
          setNote({
            ok: approved,
            text: (approved ? "Approved: " : "Refused: ") + approval.action_type,
          });
          props.onChanged();
        })
        .catch(function (err) {
          setNote({ ok: false, text: String((err && err.message) || err) });
        })
        .finally(function () { setBusy(null); });
    }

    const buttonStyle = {
      background: "transparent",
      border: "1px solid var(--ho-amber-dim)",
      color: "var(--ho-amber)",
      font: "inherit",
      fontSize: "10.5px",
      letterSpacing: "0.06em",
      textTransform: "uppercase",
      padding: "2px 8px",
      cursor: "pointer",
      whiteSpace: "nowrap",
    };

    let body;
    if (loading) { body = ErrorNote("Reading approval queue…"); }
    else if (error) { body = ErrorNote("Backend unreachable: " + error); }
    else if (data.length === 0) {
      // Not an error state: an empty queue is the normal, healthy case.
      body = React.createElement("span", { className: "ho-muted" },
        "Nothing awaiting approval.");
    } else {
      body = React.createElement("div", { className: "flex flex-col", style: { gap: "10px" } },
        data.map(function (approval) {
          return React.createElement("div", {
            key: approval.id,
            className: "flex flex-col",
            style: {
              gap: "4px",
              borderLeft: "2px solid var(--ho-bad)",
              paddingLeft: "8px",
            },
          },
            React.createElement("div", { style: { display: "flex", justifyContent: "space-between", gap: "8px" } },
              React.createElement("span", { className: "ho-value", style: { fontSize: "12px" } },
                approval.description),
              React.createElement("span", { className: "ho-badge bad" }, approval.action_type),
            ),
            // The reason Aegis gave. Showing it is the difference between
            // an informed decision and rubber-stamping a prompt.
            React.createElement("span", { className: "ho-muted", style: { fontSize: "11px" } },
              approval.reason),
            React.createElement("div", { style: { display: "flex", gap: "6px", marginTop: "2px" } },
              React.createElement("button", {
                style: buttonStyle,
                disabled: busy === approval.id,
                onClick: function () { decide(approval, true); },
              }, busy === approval.id ? "…" : "approve once"),
              React.createElement("button", {
                style: Object.assign({}, buttonStyle, {
                  borderColor: "var(--ho-line)",
                  color: "var(--ho-text-dim)",
                }),
                disabled: busy === approval.id,
                onClick: function () { decide(approval, false); },
              }, "refuse"),
              React.createElement("span", {
                className: "ho-muted",
                style: { fontSize: "10.5px", alignSelf: "center" },
              }, "asked by " + approval.requesting_agent),
            ),
          );
        }),
        note
          ? React.createElement("span", {
              className: cn("ho-badge", note.ok ? "good" : "dim"),
              style: { alignSelf: "flex-start", textTransform: "none" },
            }, note.text)
          : null,
      );
    }

    return React.createElement(Panel, {
      title: "Security — awaiting you",
      right: React.createElement(LinkBadge, { error: error, latencyMs: latencyMs }),
    }, body);
  }

  function LaunchPanel(props) {
    const { data: projects } = useBackendResource("/projects", props.reloadKey);
    const [projectName, setProjectName] = useState("");
    const [taskTitle, setTaskTitle] = useState("");
    const [taskProject, setTaskProject] = useState("");
    const [busy, setBusy] = useState(false);
    const [note, setNote] = useState(null);

    function run(promise, okMessage) {
      setBusy(true);
      setNote(null);
      promise
        .then(function () {
          setNote({ ok: true, text: okMessage });
          props.onChanged();
        })
        .catch(function (err) {
          setNote({ ok: false, text: String((err && err.message) || err) });
        })
        .finally(function () { setBusy(false); });
    }

    const inputStyle = {
      background: "#1c1509",
      border: "1px solid var(--ho-line)",
      color: "var(--ho-text)",
      font: "inherit",
      fontSize: "12.5px",
      padding: "4px 7px",
      width: "100%",
      outline: "none",
    };
    const buttonStyle = {
      background: "transparent",
      border: "1px solid var(--ho-amber-dim)",
      color: "var(--ho-amber)",
      font: "inherit",
      fontSize: "11px",
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      padding: "3px 10px",
      cursor: busy ? "wait" : "pointer",
      whiteSpace: "nowrap",
    };

    const body = React.createElement("div", { className: "flex flex-col", style: { gap: "10px" } },
      // --- create a project -------------------------------------------
      React.createElement("div", { className: "flex flex-col", style: { gap: "4px" } },
        React.createElement("span", { className: "ho-muted" }, "New project"),
        React.createElement("div", { style: { display: "flex", gap: "6px" } },
          React.createElement("input", {
            style: inputStyle,
            placeholder: "ex. Petite app de suivi",
            value: projectName,
            disabled: busy,
            onChange: function (e) { setProjectName(e.target.value); },
          }),
          React.createElement("button", {
            style: buttonStyle,
            disabled: busy || !projectName.trim(),
            onClick: function () {
              const name = projectName.trim();
              run(postJSON("/projects", { name: name }), "Project created: " + name);
              setProjectName("");
            },
          }, "create"),
        ),
      ),
      // --- create a task, optionally scoped to a project ---------------
      React.createElement("div", { className: "flex flex-col", style: { gap: "4px" } },
        React.createElement("span", { className: "ho-muted" }, "New task (Kronos)"),
        React.createElement("input", {
          style: inputStyle,
          placeholder: "ex. Definir le schema de donnees",
          value: taskTitle,
          disabled: busy,
          onChange: function (e) { setTaskTitle(e.target.value); },
        }),
        React.createElement("div", { style: { display: "flex", gap: "6px" } },
          React.createElement("select", {
            style: inputStyle,
            value: taskProject,
            disabled: busy,
            onChange: function (e) { setTaskProject(e.target.value); },
          },
            React.createElement("option", { value: "" }, "(no project)"),
            (projects || []).map(function (p) {
              return React.createElement("option", { key: p.id, value: p.id }, p.name);
            }),
          ),
          React.createElement("button", {
            style: buttonStyle,
            disabled: busy || !taskTitle.trim(),
            onClick: function () {
              const title = taskTitle.trim();
              run(
                postJSON("/tasks", { title: title, project_id: taskProject || null }),
                "Task created: " + title,
              );
              setTaskTitle("");
            },
          }, "create"),
        ),
      ),
      note
        ? React.createElement("span", {
            className: cn("ho-badge", note.ok ? "good" : "bad"),
            style: { alignSelf: "flex-start", textTransform: "none" },
          }, note.text)
        : null,
    );

    return React.createElement(Panel, { title: "Launch" }, body);
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
    // Single reload counter shared by every panel: creating a project or a
    // task from the Launch panel bumps it, and each panel re-fetches.
    const [reloadKey, setReloadKey] = useState(0);
    function onChanged() { setReloadKey(function (k) { return k + 1; }); }

    return React.createElement("div", { className: "ho-crt" },
      React.createElement(Header, null),
      React.createElement("div", { className: "ho-grid" },
        React.createElement(SecurityPanel, { reloadKey: reloadKey, onChanged: onChanged }),
        React.createElement(SystemPanel, { reloadKey: reloadKey }),
        React.createElement(LaunchPanel, { reloadKey: reloadKey, onChanged: onChanged }),
        React.createElement(ProjectsPanel, { reloadKey: reloadKey }),
        React.createElement(TasksPanel, { reloadKey: reloadKey }),
        React.createElement(ProgressionPanel, { reloadKey: reloadKey }),
        React.createElement(AgentActivityPanel, { reloadKey: reloadKey }),
      ),
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-ollama", HermesOllamaDashboard);
})();
