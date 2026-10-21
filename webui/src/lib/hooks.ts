"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, get, put } from "./api";
import type { Settings, Status } from "./types";

/** Calls `fn` now and every `ms` while the tab is visible. Polling never keeps a session alive (background header). */
export function usePolling<T>(fn: (signal: AbortSignal) => Promise<T>, ms: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const load = useCallback(async () => {
    try {
      setData(await fnRef.current(new AbortController().signal));
      setError("");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    let alive = true;
    const tick = () => {
      if (alive && document.visibilityState === "visible") void load();
    };
    void load(); // the first load happens even if the tab opened in the background
    const id = window.setInterval(tick, ms);
    document.addEventListener("visibilitychange", tick); // refresh as soon as the tab comes back
    return () => {
      alive = false;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, load, ...deps]);
  return { data, error, reload: load };
}

export function useStatus(ms = 15000) {
  return usePolling<Status>(() => get<Status>("/api/status", true), ms);
}

export type ActionState = { busy: boolean; ok: string; error: string };

/** Wraps an async button action with busy/success/error state. */
export function useAction<A extends unknown[], R>(fn: (...a: A) => Promise<R>, okText = "") {
  const [state, setState] = useState<ActionState>({ busy: false, ok: "", error: "" });
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const run = useCallback(
    async (...a: A): Promise<R | undefined> => {
      setState({ busy: true, ok: "", error: "" });
      try {
        const r = await fnRef.current(...a);
        setState({ busy: false, ok: okText, error: "" });
        return r;
      } catch (e) {
        setState({ busy: false, ok: "", error: e instanceof ApiError ? e.message : (e as Error).message });
        return undefined;
      }
    },
    [okText],
  );
  const reset = useCallback(() => setState({ busy: false, ok: "", error: "" }), []);
  return { ...state, run, reset };
}

/** Loads all settings, and saves a subset with the server's validation errors passed through. */
export function useSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    get<Settings>("/api/settings")
      .then((s) => {
        if (!alive) return;
        setSettings(s);
        setLoadError("");
      })
      .catch((e: Error) => {
        if (alive) setLoadError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [version]);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const save = useCallback(
    async (partial: Partial<Settings>) => {
      const r = await put<{ changed: string[] }>("/api/settings", partial);
      reload();
      return r.changed;
    },
    [reload],
  );
  return { settings, loadError, reload, save };
}
