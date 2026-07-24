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
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { Card, CardHeader, CardTitle, CardContent, Badge } = SDK.components;
  const { useState, useEffect } = SDK.hooks;
  const { cn } = SDK.utils;

  const API_BASE = "/api/plugins/hermes-ollama";

  function useBackendResource(path) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(function () {
      let cancelled = false;
      setLoading(true);
      SDK.fetchJSON(API_BASE + path)
        .then(function (json) {
          if (!cancelled) { setData(json); setError(null); }
        })
        .catch(function (err) {
          if (!cancelled) { setError(String((err && err.message) || err)); }
        })
        .finally(function () {
          if (!cancelled) { setLoading(false); }
        });
      return function () { cancelled = true; };
    }, []);

    return { data: data, error: error, loading: loading };
  }

  function StatusLine(props) {
    return React.createElement("div", { className: "flex items-center justify-between text-sm" },
      React.createElement("span", { className: "text-muted-foreground" }, props.label),
      React.createElement("span", { className: "font-courier" }, props.value),
    );
  }

  function CardError(message) {
    return React.createElement("p", { className: "text-sm text-muted-foreground" }, message);
  }

  function SystemStatusCard() {
    const { data, error, loading } = useBackendResource("/system-status");

    let body;
    if (loading) {
      body = CardError("Loading...");
    } else if (error) {
      body = CardError("Backend unreachable: " + error);
    } else {
      const gpu = data.gpu;
      body = React.createElement("div", { className: "flex flex-col gap-2" },
        gpu
          ? React.createElement(React.Fragment, null,
              React.createElement(StatusLine, { label: "GPU VRAM", value: gpu.vram_used_gb + " / " + gpu.vram_total_gb + " GB (" + gpu.vram_used_pct + "%)" }),
              React.createElement(StatusLine, { label: "GPU temp", value: gpu.temp_c + "°C" }),
              React.createElement(StatusLine, { label: "GPU load", value: gpu.load_pct + "%" }),
            )
          : React.createElement(StatusLine, { label: "GPU", value: "not detected (no rocm-smi)" }),
        React.createElement(StatusLine, { label: "CPU load", value: data.cpu_load_pct + "%" }),
        React.createElement(StatusLine, { label: "RAM", value: data.ram_used_gb + " / " + data.ram_total_gb + " GB" }),
        React.createElement(StatusLine, { label: "Disk free", value: data.disk_free_gb + " GB" }),
        React.createElement(StatusLine, { label: "Models loaded", value: data.loaded_models.length }),
        data.alerts && data.alerts.length > 0
          ? React.createElement("div", { className: "flex flex-col gap-1 mt-1" },
              data.alerts.map(function (alert, i) {
                return React.createElement(Badge, { key: i, variant: "destructive", className: "w-fit" }, alert);
              }),
            )
          : null,
      );
    }

    return React.createElement(Card, null,
      React.createElement(CardHeader, null, React.createElement(CardTitle, { className: "text-base" }, "System")),
      React.createElement(CardContent, null, body),
    );
  }

  function ProjectsCard() {
    const { data, error, loading } = useBackendResource("/projects");

    let body;
    if (loading) {
      body = CardError("Loading...");
    } else if (error) {
      body = CardError("Backend unreachable: " + error);
    } else if (data.length === 0) {
      body = CardError("No projects yet.");
    } else {
      body = React.createElement("div", { className: "flex flex-col gap-2" },
        data.map(function (project) {
          return React.createElement("div", { key: project.id, className: "flex items-center justify-between text-sm" },
            React.createElement("span", null, project.name),
            React.createElement(Badge, { variant: project.status === "active" ? "outline" : "secondary" }, project.status),
          );
        }),
      );
    }

    return React.createElement(Card, null,
      React.createElement(CardHeader, null, React.createElement(CardTitle, { className: "text-base" }, "Projects")),
      React.createElement(CardContent, null, body),
    );
  }

  function TasksCard() {
    const { data, error, loading } = useBackendResource("/tasks");

    let body;
    if (loading) {
      body = CardError("Loading...");
    } else if (error) {
      body = CardError("Backend unreachable: " + error);
    } else {
      const counts = {};
      data.forEach(function (task) { counts[task.status] = (counts[task.status] || 0) + 1; });
      const statuses = Object.keys(counts);
      body = statuses.length === 0
        ? CardError("No tasks yet.")
        : React.createElement("div", { className: "flex flex-col gap-2" },
            statuses.map(function (status) {
              return React.createElement(StatusLine, { key: status, label: status, value: counts[status] });
            }),
            React.createElement(StatusLine, { label: "Total", value: data.length }),
          );
    }

    return React.createElement(Card, null,
      React.createElement(CardHeader, null, React.createElement(CardTitle, { className: "text-base" }, "Tasks")),
      React.createElement(CardContent, null, body),
    );
  }

  function ProgressionCard() {
    const { data, error, loading } = useBackendResource("/progression");

    let body;
    if (loading) {
      body = CardError("Loading...");
    } else if (error) {
      body = CardError("Backend unreachable: " + error);
    } else {
      body = React.createElement("div", { className: "flex flex-col gap-2" },
        React.createElement(StatusLine, {
          label: "Success rate",
          value: data.success_rate === null ? "n/a" : Math.round(data.success_rate * 100) + "%",
        }),
        React.createElement(StatusLine, { label: "Tasks succeeded", value: data.tasks_succeeded + " / " + data.tasks_terminal }),
        React.createElement(StatusLine, { label: "Skills validated", value: data.skills_validated }),
        React.createElement(StatusLine, { label: "Skills in review", value: data.skills_in_review }),
        React.createElement(StatusLine, { label: "Skills total", value: data.skills_total }),
      );
    }

    return React.createElement(Card, null,
      React.createElement(CardHeader, null, React.createElement(CardTitle, { className: "text-base" }, "Self-Evolution (HSE)")),
      React.createElement(CardContent, null, body),
    );
  }

  function HermesOllamaDashboard() {
    return React.createElement("div", { className: cn("grid gap-4", "sm:grid-cols-2") },
      React.createElement(SystemStatusCard, null),
      React.createElement(ProjectsCard, null),
      React.createElement(TasksCard, null),
      React.createElement(ProgressionCard, null),
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-ollama", HermesOllamaDashboard);
})();
