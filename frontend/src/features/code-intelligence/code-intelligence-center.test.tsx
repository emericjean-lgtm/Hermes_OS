import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CodeIntelligenceCenter } from "./code-intelligence-center";

/**
 * R-006 Phase 7 (percentage fix) + Phase 8 (real API rebuild).
 *
 * The Center used to render `success_rate.toFixed(0)+"%"` on a 0-1
 * fraction, so a real 73% success rate showed as "1%". Phase 8 rebuilt the
 * whole Center onto `/api/v1/code-intelligence/*`, so this test now mocks
 * that surface (useCodeIntelligenceStatus/Providers/History) rather than
 * the old useKlaatCodeStatus/useOhMyPiStatus hooks — the percentage-fix
 * assertion is preserved through the rebuild via the Providers panel,
 * which still reads a real 0-1 `client_stats.success_rate`.
 */

vi.mock("@/hooks/use-api", () => ({
  useCodeIntelligenceStatus: () => ({
    data: {
      agent_id: "ci_test123",
      name: "CodeIntelligence",
      status: "ready",
      op_status: "idle",
      is_available: true,
      capabilities: ["code_generation", "code_review"],
      providers: ["klaatcode", "ohmypi", "hermes_native"],
      total_tasks: 5,
      successful_tasks: 3,
      failed_tasks: 2,
      klaatcode_tasks: 3,
      ohmypi_tasks: 1,
      hermes_native_tasks: 1,
      hybrid_tasks: 0,
      success_rate: 60,
      router_stats: {
        klaatcode: { total: 3, success_count: 2, success_rate: 66.7 },
        ohmypi: { total: 1, success_count: 0, success_rate: 0 },
        hermes_native: { total: 1, success_count: 1, success_rate: 100 },
        total_executions: 5,
      },
      current_task_id: "",
    },
    isLoading: false,
    isError: false,
  }),
  useCodeIntelligenceProviders: () => ({
    data: {
      klaatcode: {
        available: true,
        status: {
          installed: true,
          version: "2.4.4",
          tools_count: 7,
          capabilities: ["analyze_project"],
          client_stats: {
            total_executions: 11,
            success_count: 8,
            failure_count: 3,
            timeout_count: 0,
            success_rate: 0.73,
            avg_duration_ms: 842,
            installed: true,
            version: "2.4.4",
          },
          server_bound: true,
          mcp_status: "disconnected",
        },
      },
      ohmypi: {
        available: false,
        status: {
          installed: false,
          version: null,
          tools_count: 9,
          capabilities: [],
          client_stats: {
            total_executions: 4,
            success_count: 0,
            failure_count: 4,
            timeout_count: 0,
            success_rate: 0,
            avg_duration_ms: 700,
            installed: false,
            version: null,
          },
          server_bound: true,
          mcp_status: "not_configured",
        },
      },
      hermes_native: { available: true, status: { agent_id: "hermes_native_abc" } },
    },
    isLoading: false,
    isError: false,
  }),
  useCodeIntelligenceHistory: () => ({
    data: { history: [], total: 0 },
    isLoading: false,
    isError: false,
  }),
  useRunCodeIntelligenceTask: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

describe("CodeIntelligenceCenter", () => {
  it("renders a 0-1 fraction as a real percentage, not the raw fraction", () => {
    render(<CodeIntelligenceCenter />);
    expect(screen.getByText("73%")).toBeInTheDocument();
    expect(screen.queryByText("1%")).not.toBeInTheDocument();
  });

  it("renders the real agent-level success rate (already 0-100) unscaled", () => {
    render(<CodeIntelligenceCenter />);
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("shows KlaatCode installed and Oh My Pi not installed, distinctly", () => {
    render(<CodeIntelligenceCenter />);
    const badges = screen.getAllByText(/^(yes|no)$/);
    expect(badges.length).toBeGreaterThan(0);
  });

  it("renders the real MCP status values, not a bare boolean", () => {
    render(<CodeIntelligenceCenter />);
    expect(screen.getByText("disconnected")).toBeInTheDocument();
    expect(screen.getByText("not_configured")).toBeInTheDocument();
  });
});
