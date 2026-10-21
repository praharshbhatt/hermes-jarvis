export function duration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function dateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function short(value: unknown, n = 60): string {
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function mmss(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const STATE_LABEL: Record<string, string> = {
  idle: "Standing by",
  wake: "Wake word",
  listening: "Listening",
  speech: "Hearing you",
  thinking: "Thinking",
  speaking: "Speaking",
  stopped: "Stopped",
  followup: "Awaiting your answer",
};
