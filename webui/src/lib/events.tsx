"use client";
import { createContext, useContext, useEffect, useMemo, useReducer, useRef, type MutableRefObject, type ReactNode } from "react";
import { get } from "./api";
import type { FeedItem, LiveEvent, PipelineState } from "./types";

export type Live = {
  connected: boolean; // the live stream is open
  state: PipelineState;
  device: { connected: boolean; name: string };
  feed: FeedItem[];
  route: { profile: string; reason: string; router_ms: number; resumed: boolean } | null;
  /** When each state was last entered (seconds since the epoch): lets the setup test know the wake word was heard. */
  seen: Partial<Record<PipelineState, number>>;
  /** Microphone loudness 0..1, updated ten times a second. A ref, so it never re-renders the page. */
  levelRef: MutableRefObject<number>;
};

type Store = Omit<Live, "levelRef">;
type Action =
  | { type: "stream"; connected: boolean }
  | { type: "snapshot"; state: PipelineState; device: Store["device"]; recent: LiveEvent[] }
  | { type: "event"; event: LiveEvent };

const MAX_FEED = 60;
const initial: Store = { connected: false, state: "idle", device: { connected: false, name: "" }, feed: [], route: null, seen: {} };

function toFeed(e: LiveEvent): FeedItem | null {
  switch (e.type) {
    case "transcript":
      return { kind: e.role, id: e.id, ts: e.ts, text: e.text, hidden: e.hidden };
    case "tool":
      return { kind: "tool", id: e.id, ts: e.ts, tool: e.tool, label: e.label, status: e.status };
    case "route":
      return { kind: "route", id: e.id, ts: e.ts, profile: e.profile, reason: e.reason, router_ms: e.router_ms, resumed: e.resumed };
    default:
      return null;
  }
}

export function reduce(s: Store, a: Action): Store {
  switch (a.type) {
    case "stream":
      return { ...s, connected: a.connected };
    case "snapshot": {
      const feed = a.recent.map(toFeed).filter((x): x is FeedItem => x !== null).slice(-MAX_FEED);
      const lastRoute = [...a.recent].reverse().find((e) => e.type === "route");
      return {
        ...s,
        connected: true,
        state: a.state,
        device: a.device,
        feed,
        route: lastRoute && lastRoute.type === "route" ? lastRoute : s.route,
      };
    }
    case "event": {
      const e = a.event;
      if (e.type === "state") return { ...s, state: e.state, seen: { ...s.seen, [e.state]: e.ts } };
      if (e.type === "device") return { ...s, device: { connected: e.connected, name: e.name } };
      const item = toFeed(e);
      if (!item) return s;
      // a tool line updates its own earlier line (running -> completed) instead of adding a second one
      let feed = s.feed;
      if (item.kind === "tool") {
        const i = feed.findLastIndex((f) => f.kind === "tool" && f.tool === item.tool && f.status === "running");
        if (i >= 0 && item.status !== "running") {
          feed = feed.map((f, n) => (n === i ? { ...item, label: item.label || (f as typeof item).label } : f));
          return { ...s, feed };
        }
      }
      feed = [...feed, item].slice(-MAX_FEED);
      return { ...s, feed, route: item.kind === "route" ? item : s.route };
    }
  }
}

const Ctx = createContext<Live | null>(null);

export function useLive(): Live {
  const c = useContext(Ctx);
  if (!c) throw new Error("useLive must be used inside <LiveProvider>");
  return c;
}

/** Subscribes to the service's server-sent events and keeps the HUD's state. Reconnects by itself. */
export function LiveProvider({ children, url = "/api/events" }: { children: ReactNode; url?: string }) {
  const [store, dispatch] = useReducer(reduce, initial);
  const levelRef = useRef(0);

  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    let decay = 0;

    const parse = <T,>(ev: MessageEvent): T | null => {
      try {
        return JSON.parse(ev.data as string) as T;
      } catch {
        return null;
      }
    };

    const open = () => {
      es = new EventSource(url);
      es.addEventListener("open", () => dispatch({ type: "stream", connected: true }));
      es.addEventListener("snapshot", (ev) => {
        const d = parse<{ state: PipelineState; device: Store["device"]; recent: LiveEvent[] }>(ev as MessageEvent);
        if (d) dispatch({ type: "snapshot", ...d });
      });
      for (const name of ["state", "transcript", "tool", "route", "device"] as const) {
        es.addEventListener(name, (ev) => {
          const d = parse<LiveEvent>(ev as MessageEvent);
          if (d) dispatch({ type: "event", event: d });
        });
      }
      es.addEventListener("level", (ev) => {
        const d = parse<{ value: number }>(ev as MessageEvent);
        if (d) levelRef.current = d.value;
      });
      es.addEventListener("end", () => es?.close());
      es.addEventListener("error", () => {
        dispatch({ type: "stream", connected: false });
        // EventSource retries by itself; if the reason is an ended session, the API client sends the user to /login/
        void get("/api/session", true).catch(() => undefined);
      });
    };
    open();
    decay = window.setInterval(() => {
      levelRef.current *= 0.82; // loudness falls back to silence between updates
    }, 100);
    return () => {
      closed = true;
      void closed;
      es?.close();
      window.clearInterval(decay);
    };
  }, [url]);

  const value = useMemo<Live>(() => ({ ...store, levelRef }), [store]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
