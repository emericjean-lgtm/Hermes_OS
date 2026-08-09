"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";

/**
 * Voice dictation (Assistant v2 feedback round) — the browser's own
 * SpeechRecognition, not a new backend pipeline. Hermes has no STT model
 * wired anywhere; Chrome/Edge already ship one and expose it for free.
 * The button simply doesn't render where the API is absent (Firefox,
 * Safari before 17) rather than appearing and failing silently — the
 * honesty rule that's applied to every other capability in this app
 * applies here too: no control that implies something the browser can't
 * actually do.
 */

interface MinimalSpeechRecognition extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtor = new () => MinimalSpeechRecognition;

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function VoiceButton({
  onResult, onError,
}: {
  onResult: (text: string) => void;
  onError?: (message: string) => void;
}) {
  const [available, setAvailable] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<MinimalSpeechRecognition | null>(null);

  // Checked in an effect, not at module scope: SpeechRecognition reads
  // `window`, which doesn't exist during Next's server render.
  useEffect(() => setAvailable(getRecognitionCtor() !== null), []);

  useEffect(() => () => recRef.current?.stop(), []);

  const toggle = useCallback(() => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = "fr-FR";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (event) => {
      const text = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (text) onResult(text);
    };
    rec.onerror = (event) => {
      setListening(false);
      if (event.error === "no-speech") return;
      onError?.(`Reconnaissance vocale : ${event.error}`);
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [listening, onResult, onError]);

  if (!available) return null;

  return (
    <button
      onClick={toggle}
      title={listening ? "Arrêter la dictée" : "Dicter (reconnaissance vocale du navigateur)"}
      className={`relative flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-all
        ${listening
          ? "border-hermes-red/50 bg-hermes-red/15 text-hermes-red"
          : "border-hermes-border text-hermes-muted hover:border-hermes-cyan/40 hover:text-hermes-cyan"}`}
    >
      {listening ? <Square size={11} fill="currentColor" /> : <Mic size={13} />}
      {listening && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-pulse rounded-full bg-hermes-red" />
      )}
    </button>
  );
}
