import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { VoiceButton } from "./voice-input";

/**
 * Assistant v2 feedback round: voice dictation via the browser's own
 * SpeechRecognition, not a fabricated control. The button must not render
 * at all on a browser that doesn't implement the API (Firefox, older
 * Safari) — a visible mic icon that silently does nothing on click would
 * be exactly the kind of lying UI this whole engagement has been removing.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("VoiceButton", () => {
  it("renders nothing when the browser has no SpeechRecognition API", async () => {
    vi.stubGlobal("SpeechRecognition", undefined);
    vi.stubGlobal("webkitSpeechRecognition", undefined);
    const { container } = render(<VoiceButton onResult={() => {}} />);
    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("renders the dictation button when SpeechRecognition is available", async () => {
    class FakeRecognition {
      lang = "";
      interimResults = false;
      continuous = false;
      onresult: unknown = null;
      onerror: unknown = null;
      onend: (() => void) | null = null;
      start = vi.fn();
      stop = vi.fn();
    }
    vi.stubGlobal("SpeechRecognition", FakeRecognition);

    render(<VoiceButton onResult={() => {}} />);
    await waitFor(() =>
      expect(screen.getByTitle("Dicter (reconnaissance vocale du navigateur)")).toBeInTheDocument());
  });
});
