"use client";

import { useEffect, useRef } from "react";

/** The signature element: a live trace, drawn the way an instrument draws.
 *
 *  This is a real oscilloscope, not an ambient decoration — it plots the
 *  values it is given, on a fixed rolling window, and it is honest about
 *  having no data (a flat baseline, not an invented waveform). Feeding it
 *  `Math.random()` would have made a prettier picture and a dishonest one.
 *
 *  Drawn on canvas rather than as an SVG path because the buffer updates on
 *  a timer and re-rendering ~120 path points through React every second is
 *  work for nothing. */
export function TelemetryTrace({
  value,
  width = 132,
  height = 26,
  color = "#ff9436",
  /** How often a sample is pushed. The cockpit's own polling is far slower
   *  than this, so between real values the trace holds its last reading —
   *  a held line, not an interpolated invention. */
  intervalMs = 420,
  points = 68,
  className = "",
  label,
}: {
  value: number | null | undefined;
  width?: number;
  height?: number;
  color?: string;
  intervalMs?: number;
  points?: number;
  className?: string;
  label?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const bufRef = useRef<(number | null)[]>(Array(points).fill(null));
  // Kept in a ref so the sampling interval doesn't need re-creating on every
  // value change — the timer reads the latest value when it fires.
  const latest = useRef<number | null | undefined>(value);
  latest.current = value;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const draw = () => {
      const buf = bufRef.current;
      ctx.clearRect(0, 0, width, height);

      // Baseline — always drawn, so an empty trace still reads as an
      // instrument that is on rather than a broken panel.
      ctx.strokeStyle = "rgba(133,149,166,0.18)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height - 0.5);
      ctx.lineTo(width, height - 0.5);
      ctx.stroke();

      const step = width / (buf.length - 1);
      const y = (v: number) => height - 1 - (Math.max(0, Math.min(100, v)) / 100) * (height - 2);

      // Fill under the curve first, so the stroke sits on top of it.
      ctx.beginPath();
      let started = false;
      buf.forEach((v, i) => {
        if (v === null) return;
        const px = i * step;
        if (!started) { ctx.moveTo(px, y(v)); started = true; }
        else ctx.lineTo(px, y(v));
      });
      if (started) {
        const grad = ctx.createLinearGradient(0, 0, 0, height);
        grad.addColorStop(0, `${color}44`);
        grad.addColorStop(1, `${color}00`);
        ctx.lineTo(width, height);
        ctx.lineTo(0, height);
        ctx.closePath();
        ctx.fillStyle = grad;
        ctx.fill();
      }

      ctx.beginPath();
      started = false;
      buf.forEach((v, i) => {
        if (v === null) return;
        const px = i * step;
        if (!started) { ctx.moveTo(px, y(v)); started = true; }
        else ctx.lineTo(px, y(v));
      });
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.lineJoin = "round";
      ctx.stroke();

      // Leading dot — the write head. Only drawn when there is a real
      // reading to write.
      const last = buf[buf.length - 1];
      if (last !== null && last !== undefined) {
        ctx.beginPath();
        ctx.arc(width - 1, y(last), 1.9, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.shadowBlur = 7;
        ctx.shadowColor = color;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    };

    const tick = () => {
      const v = latest.current;
      bufRef.current = [
        ...bufRef.current.slice(1),
        typeof v === "number" && Number.isFinite(v) ? v : null,
      ];
      draw();
    };

    draw();
    const id = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(id);
  }, [width, height, color, intervalMs, points]);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {label && <span className="tech-label shrink-0">{label}</span>}
      <canvas
        ref={canvasRef}
        style={{ width, height }}
        aria-hidden="true"
        className="block shrink-0"
      />
      <span
        className="num text-[10.5px] tabular-nums shrink-0 w-9 text-right"
        style={{ color }}
      >
        {typeof value === "number" && Number.isFinite(value) ? `${Math.round(value)}%` : "––"}
      </span>
    </div>
  );
}
