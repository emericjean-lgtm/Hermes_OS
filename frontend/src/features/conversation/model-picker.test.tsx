import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ContextMeter, ModelPicker } from "./model-picker";
import type { SystemModelRoleDTO } from "@/services/client";

/**
 * Assistant v2 feedback round: ContextMeter used to render only the bare
 * "XX%" text. This checks the replacement fill bar actually reflects the
 * real used/window ratio in its width, not just that some markup renders.
 */

describe("ContextMeter", () => {
  it("renders nothing when there is no real window (role not yet resolved)", () => {
    const { container } = render(<ContextMeter used={100} window={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("sizes the fill bar to the real used/window ratio", () => {
    const { container } = render(<ContextMeter used={8192} window={32768} />);
    const fill = container.querySelector(".rounded-full.bg-hermes-cyan");
    expect(fill).not.toBeNull();
    // framer-motion's `animate` prop is applied via style once mounted.
    expect(fill?.getAttribute("style")).toContain("25%");
  });

  it("switches tone to red past 90% usage", () => {
    const { container } = render(<ContextMeter used={30000} window={32768} />);
    expect(container.querySelector(".bg-hermes-red")).not.toBeNull();
    expect(container.querySelector(".text-hermes-red")).not.toBeNull();
  });

  it("caps the bar at 100% when usage exceeds the window", () => {
    const { container } = render(<ContextMeter used={40000} window={32768} />);
    const fill = container.querySelector(".rounded-full.bg-hermes-red");
    expect(fill?.getAttribute("style")).toContain("100%");
  });
});

/**
 * Operator request: the picker only ever listed the 12 benchmarked
 * roles from config/models.yaml — every other model Ollama actually has
 * installed was invisible. `roles` now also carries uncatalogued models
 * (`benchmarked: false`, `role: ""`), which is the same empty string
 * "Auto" already uses — the picker must not confuse the two.
 */
describe("ModelPicker — modèles hors catalogue", () => {
  const roles: SystemModelRoleDTO[] = [
    { role: "standard", model: "ornith-9b-256k", tier: "standard", vram_gb: 13.5,
      always_loaded: false, loaded: false, installe: true, description: "",
      benchmarked: true },
    { role: "", model: "qwen3.5-9b-256k:latest", tier: "", vram_gb: null,
      always_loaded: false, loaded: false, installe: true,
      description: "Installé, hors catalogue.", benchmarked: false },
  ];

  it("lists an uncatalogued model under its own section", async () => {
    render(<ModelPicker roles={roles} value={{ role: "" }} onChange={() => {}} />);
    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText("qwen3.5-9b-256k:latest")).toBeTruthy();
    expect(screen.getByText(/non benchmarkés/)).toBeTruthy();
  });

  it("selecting it sends the model tag, never the empty string Auto uses", async () => {
    const onChange = vi.fn();
    render(<ModelPicker roles={roles} value={{ role: "" }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button"));

    fireEvent.click(await screen.findByText("qwen3.5-9b-256k:latest"));

    expect(onChange).toHaveBeenCalledWith({ role: "qwen3.5-9b-256k:latest" });
  });

  it("does not confuse the active uncatalogued model with Auto", async () => {
    render(
      <ModelPicker roles={roles} value={{ role: "qwen3.5-9b-256k:latest" }}
        onChange={() => {}} />,
    );

    // The button label reflects the selected model, not "Auto".
    expect(screen.queryByText("Auto")).toBeNull();
    expect(screen.getByText("qwen3.5-9b-256k:latest")).toBeTruthy();
  });
});
