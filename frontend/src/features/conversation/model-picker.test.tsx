import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ContextMeter } from "./model-picker";

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
