"use client";

import React from "react";

/** Keeps one Center's failure inside that Center.
 *
 *  Every Center render error observed during local validation escaped upward and
 *  unmounted the whole Cockpit: the sidebar, the topbar and the status bar all
 *  disappeared, leaving a blank page with no way to navigate anywhere else. A
 *  bad response from a single endpoint should cost you that one panel, not the
 *  entire application (R-004).
 *
 *  The boundary also surfaces the error instead of hiding it — a silent
 *  fallback would just be a prettier blank page.
 */
interface Props {
  /** Changing this remounts the boundary, so navigating away clears the error. */
  viewKey: string;
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

export class CenterBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.viewKey !== this.props.viewKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep it in the console for diagnosis; the panel below is for the operator.
    console.error(`Center "${this.props.viewKey}" failed to render`, error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="rounded-lg border border-hermes-red/40 bg-hermes-red/5 p-5">
        <div className="text-sm font-bold text-hermes-red font-mono mb-2">
          This panel failed to render
        </div>
        <div className="text-xs text-hermes-text font-mono mb-3">
          <span className="text-hermes-muted">Center:</span> {this.props.viewKey}
        </div>
        <pre className="text-[11px] text-hermes-muted font-mono whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
          {this.state.error.message}
        </pre>
        <div className="text-[11px] text-hermes-muted font-mono mt-3">
          The rest of the Cockpit is unaffected — pick another Center in the
          sidebar.
        </div>
      </div>
    );
  }
}
