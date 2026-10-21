import { describe, expect, it, vi } from "vitest";
import { ApiError, api, setCsrf, setUnauthorizedHandler } from "@/lib/api";
import { reduce } from "@/lib/events";
import { fixFor, worst } from "@/lib/fixes";
import { clock, duration, mmss, short } from "@/lib/format";
import type { LiveEvent } from "@/lib/types";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("api client", () => {
  it("sends the CSRF token on changes but not on reads", async () => {
    const fn = mockFetch(200, { ok: true });
    setCsrf("tok123");
    await api("/api/settings", { method: "PUT", body: { a: 1 } });
    await api("/api/status");
    const put = fn.mock.calls[0]![1] as RequestInit & { headers: Record<string, string> };
    const get = fn.mock.calls[1]![1] as RequestInit & { headers: Record<string, string> };
    expect(put.headers["X-CSRF-Token"]).toBe("tok123");
    expect(put.headers["Content-Type"]).toBe("application/json");
    expect(get.headers["X-CSRF-Token"]).toBeUndefined();
    expect(put.credentials).toBe("same-origin");
  });

  it("marks background polling so it cannot keep a session alive", async () => {
    const fn = mockFetch(200, {});
    await api("/api/status", { background: true });
    expect((fn.mock.calls[0]![1] as { headers: Record<string, string> }).headers["X-HJ-Background"]).toBe("1");
  });

  it("turns server errors into ApiError with the server's message", async () => {
    mockFetch(400, { error: "piper_length_scale: must be between 0.3 and 3" });
    await expect(api("/api/settings", { method: "PUT", body: {} })).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      message: "piper_length_scale: must be between 0.3 and 3",
    });
  });

  it("calls the unauthorized handler on 401 but not for a wrong login", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { error: "login required" });
    await expect(api("/api/settings")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
    mockFetch(401, { error: "wrong username or password" });
    await expect(api("/api/login", { body: {} })).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1); // a failed login is not an expired session
    setUnauthorizedHandler(null);
  });

  it("explains an unreachable service", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(api("/api/status")).rejects.toThrow(/Cannot reach/);
  });
});

describe("live event reducer", () => {
  const base: Parameters<typeof reduce>[0] = { connected: true, state: "idle", device: { connected: false, name: "" }, feed: [], route: null, seen: {} };
  const ev = (e: Record<string, unknown>) => ({ id: 1, ts: 100, ...e }) as unknown as LiveEvent;

  it("tracks state and when it was last entered", () => {
    const s = reduce(base, { type: "event", event: ev({ type: "state", state: "thinking", ts: 123 }) });
    expect(s.state).toBe("thinking");
    expect(s.seen.thinking).toBe(123);
  });

  it("adds transcripts and routing to the feed, capped in length", () => {
    let s = base;
    for (let i = 0; i < 80; i++) s = reduce(s, { type: "event", event: ev({ type: "transcript", id: i, role: "user", text: `t${i}`, hidden: false }) });
    expect(s.feed).toHaveLength(60);
    expect(s.feed.at(-1)).toMatchObject({ kind: "user", text: "t79" });
    s = reduce(s, { type: "event", event: ev({ type: "route", id: 99, profile: "work", reason: "jev-resume", router_ms: 250, resumed: true }) });
    expect(s.route).toMatchObject({ profile: "work", resumed: true });
  });

  it("updates a running tool line when it completes instead of adding another", () => {
    let s = reduce(base, { type: "event", event: ev({ type: "tool", id: 1, tool: "terminal", label: "ls", status: "running" }) });
    s = reduce(s, { type: "event", event: ev({ type: "tool", id: 2, tool: "terminal", label: "", status: "completed" }) });
    expect(s.feed).toHaveLength(1);
    expect(s.feed[0]).toMatchObject({ kind: "tool", status: "completed", label: "ls" });
  });

  it("takes everything from a snapshot, including the device", () => {
    const s = reduce(base, {
      type: "snapshot",
      state: "speaking",
      device: { connected: true, name: "voice-1" },
      recent: [ev({ type: "transcript", role: "assistant", text: "Hello", hidden: false }), ev({ type: "route", profile: "default", reason: "window", router_ms: 0, resumed: true })],
    });
    expect(s.state).toBe("speaking");
    expect(s.device).toEqual({ connected: true, name: "voice-1" });
    expect(s.feed).toHaveLength(2);
    expect(s.route?.profile).toBe("default");
  });

  it("keeps hidden transcripts hidden", () => {
    const s = reduce(base, { type: "event", event: ev({ type: "transcript", role: "user", text: "", hidden: true }) });
    expect(s.feed[0]).toMatchObject({ hidden: true, text: "" });
  });
});

describe("fix suggestions", () => {
  it("names the variable to set for a missing key", () => {
    expect(fixFor("speech to text (elevenlabs)", "missing: set ELEVENLABS_API_KEY")).toContain("ELEVENLABS_API_KEY");
  });
  it("explains the Hermes key override", () => {
    expect(fixFor("Hermes profile 'default' key", "HTTP 401 (wrong key?)")).toMatch(/overrides/);
  });
  it("points at brain.base_url when the brain is unreachable", () => {
    expect(fixFor("Hermes gateway reachable", "ClientConnectorError: connection refused")).toContain("brain.base_url");
  });
  it("suggests the local speech package", () => {
    expect(fixFor("speech to text (local)", "faster-whisper is not installed: pip install 'hermes-jarvis[local-stt]'")).toContain("local-stt");
  });
  it("has nothing to say about things it does not know", () => {
    expect(fixFor("something", "odd")).toBeNull();
  });
  it("ranks step statuses by severity", () => {
    expect(worst("done", "warn")).toBe("warn");
    expect(worst("fail", "done")).toBe("fail");
  });
});

describe("formatting", () => {
  it("formats durations and countdowns", () => {
    expect(duration(45)).toBe("45s");
    expect(duration(125)).toBe("2m 5s");
    expect(duration(3 * 3600 + 120)).toBe("3h 2m");
    expect(duration(90_000)).toBe("1d 1h");
    expect(mmss(59.2)).toBe("1:00");
    expect(mmss(5)).toBe("0:05");
    expect(mmss(-3)).toBe("0:00");
  });
  it("shortens long values and formats times", () => {
    expect(short("x".repeat(100), 10)).toBe("xxxxxxxxxx…");
    expect(short({ a: 1 })).toBe('{"a":1}');
    expect(clock(0)).toMatch(/\d/);
  });
});
