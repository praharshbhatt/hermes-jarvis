"use client";
import { useEffect, useRef, type MutableRefObject } from "react";
import { useReducedMotion } from "@/lib/motion";
import { STATE_LABEL } from "@/lib/format";
import type { PipelineState } from "@/lib/types";

type RGB = readonly [number, number, number];
const CYAN: RGB = [61, 225, 255];
const WHITE: RGB = [225, 250, 255];
const AMBER: RGB = [255, 179, 71];
const RED: RGB = [255, 93, 93];

const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const STATES: PipelineState[] = ["idle", "wake", "listening", "speech", "thinking", "speaking", "stopped", "followup"];

export type Weights = Record<PipelineState, number>;
export const emptyWeights = (): Weights =>
  Object.fromEntries(STATES.map((s) => [s, s === "idle" ? 1 : 0])) as Weights;

/** Ease each state's weight toward 1 (the current state) or 0, so one look melts into the next. */
export function stepWeights(w: Weights, current: PipelineState, dt: number): Weights {
  const k = 1 - Math.exp(-dt * 7);
  const next = { ...w };
  for (const s of STATES) next[s] = w[s] + ((s === current ? 1 : 0) - w[s]) * k;
  return next;
}

/** One frame of the core. Pure drawing: everything it needs is passed in. */
export function drawFrame(
  ctx: CanvasRenderingContext2D,
  S: number,
  t: number,
  w: Weights,
  level: number,
  sinceState: number,
) {
  const c = S / 2;
  ctx.clearRect(0, 0, S, S);

  const think = w.thinking;
  const stop = w.stopped;
  const talk = w.speaking;
  const hear = Math.max(w.listening, w.speech, w.wake, w.followup);
  const hue = mix(mix(CYAN, AMBER, think), RED, Math.min(1, stop * 1.3)); // main colour of this moment
  const energy = 0.35 + 0.5 * Math.max(think, talk, w.speech) + level * 0.6;

  // ---- soft halo
  const halo = ctx.createRadialGradient(c, c, S * 0.05, c, c, S * 0.5);
  halo.addColorStop(0, rgba(hue, 0.22 * energy + 0.06));
  halo.addColorStop(0.6, rgba(hue, 0.06 + 0.05 * energy));
  halo.addColorStop(1, rgba(hue, 0));
  ctx.fillStyle = halo;
  ctx.fillRect(0, 0, S, S);

  ctx.lineCap = "round";
  const spin = 0.07 + think * 0.9 + talk * 0.18;

  // ---- outer tick ring (72 ticks)
  const rTick = S * 0.455;
  for (let i = 0; i < 72; i++) {
    const a = (i / 72) * Math.PI * 2 + t * spin * 0.35;
    const long = i % 6 === 0;
    const len = S * (long ? 0.028 : 0.014);
    ctx.strokeStyle = rgba(hue, long ? 0.55 : 0.26);
    ctx.lineWidth = Math.max(1, S * (long ? 0.004 : 0.0025));
    ctx.beginPath();
    ctx.moveTo(c + Math.cos(a) * rTick, c + Math.sin(a) * rTick);
    ctx.lineTo(c + Math.cos(a) * (rTick - len), c + Math.sin(a) * (rTick - len));
    ctx.stroke();
  }
  ctx.strokeStyle = rgba(hue, 0.22);
  ctx.lineWidth = Math.max(1, S * 0.003);
  ctx.beginPath();
  ctx.arc(c, c, S * 0.475, 0, Math.PI * 2);
  ctx.stroke();

  // ---- slow counter-rotating arcs
  const rArc = S * 0.415;
  ctx.lineWidth = S * 0.006;
  for (let k = 0; k < 3; k++) {
    const start = -t * spin * (0.6 + k * 0.25) + (k * Math.PI * 2) / 3;
    ctx.strokeStyle = rgba(hue, 0.45 + 0.25 * think);
    ctx.beginPath();
    ctx.arc(c, c, rArc, start, start + 0.55 + think * 0.5);
    ctx.stroke();
  }

  // ---- follow-up: a dashed ring that asks for an answer
  if (w.followup > 0.02) {
    ctx.save();
    ctx.setLineDash([S * 0.012, S * 0.02]);
    ctx.lineDashOffset = -t * S * 0.05;
    ctx.strokeStyle = rgba(mix(CYAN, AMBER, 0.5 + 0.5 * Math.sin(t * 3)), 0.8 * w.followup);
    ctx.lineWidth = S * 0.007;
    ctx.beginPath();
    ctx.arc(c, c, S * 0.39, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  // ---- the twelve light segments (the device's own LED ring)
  const rSeg = S * 0.335;
  const segW = S * 0.034;
  for (let i = 0; i < 12; i++) {
    const a0 = (i / 12) * Math.PI * 2 - Math.PI / 2;
    const span = (Math.PI * 2) / 12 - 0.16;
    let on = 0.2 + 0.1 * Math.sin(t * 1.3 + i * 0.5) * w.idle;
    on += w.wake * (0.7 + 0.3 * Math.sin(t * 22));
    on += (w.listening + w.followup) * (0.28 + 0.25 * Math.sin(t * 2.6 - i * 0.52));
    on += w.speech * (0.3 + level * 1.3);
    // thinking: three comets chasing round the ring
    for (let k = 0; k < 3; k++) {
      const head = (t * 2.3 + (k * Math.PI * 2) / 3) % (Math.PI * 2);
      const here = (a0 + Math.PI / 2 + span / 2 + Math.PI * 2) % (Math.PI * 2);
      const behind = (head - here + Math.PI * 2) % (Math.PI * 2);
      if (behind < 1.4) on += think * (1 - behind / 1.4) * 1.1;
    }
    on += talk * (0.22 + 0.2 * Math.sin(t * 9 + i));
    on *= 1 - 0.65 * stop;
    ctx.strokeStyle = rgba(hue, on);
    ctx.lineWidth = segW * (1 + 0.5 * Math.min(1, level) * w.speech);
    ctx.shadowColor = rgba(hue, 0.9);
    ctx.shadowBlur = on > 0.6 ? S * 0.025 : 0;
    ctx.beginPath();
    ctx.arc(c, c, rSeg, a0 + 0.08, a0 + 0.08 + span);
    ctx.stroke();
  }
  ctx.shadowBlur = 0;

  // ---- speaking: radial waveform bars
  if (talk > 0.02) {
    const n = 72;
    const base = rSeg + segW * 0.9;
    ctx.lineWidth = Math.max(1.5, S * 0.006);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const wave = (Math.sin(t * 7.2 + i * 0.9) + Math.sin(t * 3.1 - i * 0.37) + Math.sin(t * 11 + i * 2.1) * 0.5 + 2.5) / 5;
      const len = S * (0.012 + 0.06 * wave) * talk;
      ctx.strokeStyle = rgba(mix(CYAN, WHITE, wave), 0.35 + 0.6 * wave * talk);
      ctx.beginPath();
      ctx.moveTo(c + Math.cos(a) * base, c + Math.sin(a) * base);
      ctx.lineTo(c + Math.cos(a) * (base + len), c + Math.sin(a) * (base + len));
      ctx.stroke();
    }
  }

  // ---- listening: ripples spreading from the core, louder when you are
  const rip = Math.max(w.listening, w.speech, w.wake, w.followup * 0.7);
  if (rip > 0.02) {
    const speed = 0.55 + level * 1.6;
    for (let k = 0; k < 3; k++) {
      const p = (t * speed + k / 3) % 1;
      ctx.strokeStyle = rgba(hue, (1 - p) * 0.55 * rip);
      ctx.lineWidth = S * 0.005;
      ctx.beginPath();
      ctx.arc(c, c, S * (0.1 + p * 0.22), 0, Math.PI * 2);
      ctx.stroke();
    }
  }

  // ---- stop: a red ring collapsing onto the core
  if (stop > 0.02) {
    const p = Math.min(1, sinceState / 1.0);
    ctx.strokeStyle = rgba(RED, (1 - p) * 0.9 * Math.min(1, stop * 1.4));
    ctx.lineWidth = S * 0.012;
    ctx.beginPath();
    ctx.arc(c, c, S * (0.38 - p * 0.28), 0, Math.PI * 2);
    ctx.stroke();
  }

  // ---- inner coils and the core
  const rIn = S * 0.235;
  ctx.strokeStyle = rgba(hue, 0.5);
  ctx.lineWidth = S * 0.006;
  ctx.beginPath();
  ctx.arc(c, c, rIn, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = S * 0.018;
  for (let k = 0; k < 3; k++) {
    const a = t * (0.5 + think * 2.2) * (k % 2 ? -1 : 1) + (k * Math.PI * 2) / 3;
    ctx.strokeStyle = rgba(hue, 0.65);
    ctx.beginPath();
    ctx.arc(c, c, rIn * 0.84, a, a + 0.95);
    ctx.stroke();
  }
  ctx.strokeStyle = rgba(hue, 0.28);
  ctx.lineWidth = S * 0.004;
  for (let k = 0; k < 6; k++) {
    const a = (k / 6) * Math.PI * 2 + t * 0.12;
    ctx.beginPath();
    ctx.moveTo(c + Math.cos(a) * rIn * 0.3, c + Math.sin(a) * rIn * 0.3);
    ctx.lineTo(c + Math.cos(a) * rIn * 0.72, c + Math.sin(a) * rIn * 0.72);
    ctx.stroke();
  }
  const pulse = 1 + 0.07 * Math.sin(t * (1.6 + think * 4)) + level * 0.35 * hear + talk * 0.12 * Math.sin(t * 9);
  const core = ctx.createRadialGradient(c, c, 0, c, c, S * 0.11 * pulse);
  core.addColorStop(0, rgba(WHITE, 0.98));
  core.addColorStop(0.35, rgba(mix(hue, WHITE, 0.35), 0.9));
  core.addColorStop(1, rgba(hue, 0));
  ctx.fillStyle = core;
  ctx.beginPath();
  ctx.arc(c, c, S * 0.11 * pulse, 0, Math.PI * 2);
  ctx.fill();
}

type Props = {
  state: PipelineState;
  /** Live microphone loudness, 0 to 1 (a ref so updates do not re-render). */
  levelRef?: MutableRefObject<number>;
  className?: string;
};

export default function Reactor({ state, levelRef, className }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  const stateRef = useRef<PipelineState>(state);
  const entered = useRef(0);

  useEffect(() => {
    stateRef.current = state;
    entered.current = performance.now();
  }, [state]);

  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const ctx = el.getContext("2d");
    if (!ctx) return; // no canvas support (or a test environment): the label below still tells the state

    let size = 0;
    let weights = emptyWeights();
    let raf = 0;
    let last = performance.now();
    const t0 = last;

    const resize = () => {
      const w = Math.max(120, Math.round(box.clientWidth));
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      size = w;
      el.width = Math.round(w * dpr);
      el.height = Math.round(w * dpr);
      el.style.width = `${w}px`;
      el.style.height = `${w}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (reduced) still();
    };
    const still = () => {
      weights = emptyWeights();
      weights = { ...weights, idle: 0, [stateRef.current]: 1 };
      drawFrame(ctx, size, 0.6, weights, levelRef?.current ?? 0, 0.3);
    };
    const frame = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      weights = stepWeights(weights, stateRef.current, dt);
      drawFrame(ctx, size, (now - t0) / 1000, weights, levelRef?.current ?? 0, (now - entered.current) / 1000);
      raf = requestAnimationFrame(frame);
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    if (reduced) still();
    else raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [reduced, levelRef]);

  // a state change under reduced motion redraws one still frame
  useEffect(() => {
    if (!reduced) return;
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const size = el.clientWidth || 300;
    drawFrame(ctx, size, 0.6, { ...emptyWeights(), idle: 0, [state]: 1 }, 0, 0.3);
  }, [state, reduced]);

  return (
    <div ref={wrap} className={`reactor ${className ?? ""}`} data-state={state}>
      <canvas ref={canvas} role="img" aria-label={`Voice core: ${STATE_LABEL[state] ?? state}`} />
    </div>
  );
}
