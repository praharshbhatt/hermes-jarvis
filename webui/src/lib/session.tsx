"use client";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { get, post, setCsrf, setUnauthorizedHandler } from "./api";
import type { SessionInfo } from "./types";

type SessionCtx = {
  session: SessionInfo | null;
  loading: boolean;
  /** Seconds until the server ends the session for inactivity (null until known). */
  idleLeft: number | null;
  logout: () => Promise<void>;
  keepAlive: () => Promise<void>;
};

const Ctx = createContext<SessionCtx | null>(null);
const WARN_AT = 60;
const TOUCH_EVERY_MS = 60_000;

export function useSession(): SessionCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useSession must be used inside <SessionProvider>");
  return c;
}

/** Loads the session once, keeps the CSRF token for the API client, and sends the user to /login/ when it ends. */
export function SessionProvider({ children, requireAuth = true }: { children: ReactNode; requireAuth?: boolean }) {
  const router = useRouter();
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [idleLeft, setIdleLeft] = useState<number | null>(null);
  const lastActive = useRef(0);
  const lastTouch = useRef(0);
  const idleTotal = useRef(0);

  const toLogin = useCallback(
    (expired: boolean) => {
      setCsrf("");
      router.replace(expired ? "/login/?expired=1" : "/login/");
    },
    [router],
  );

  useEffect(() => {
    let alive = true;
    get<SessionInfo>("/api/session")
      .then((s) => {
        if (!alive) return;
        if (s.authenticated && s.csrf) {
          setCsrf(s.csrf);
          idleTotal.current = s.idle_seconds ?? 0;
          lastTouch.current = lastActive.current = Date.now();
        }
        setSession(s);
        if (!s.authenticated && requireAuth) toLogin(false);
      })
      .catch(() => {
        if (alive) setSession({ authenticated: false, user: "" });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [requireAuth, toLogin]);

  useEffect(() => {
    setUnauthorizedHandler(() => toLogin(true));
    return () => setUnauthorizedHandler(null);
  }, [toLogin]);

  const keepAlive = useCallback(async () => {
    try {
      await get<SessionInfo>("/api/session"); // a normal (non-background) request counts as activity
      lastTouch.current = lastActive.current = Date.now();
    } catch {
      /* a failure here means the service is unreachable; the next real call will say so */
    }
  }, []);

  // Count real interaction as activity and tell the server about it at most once a minute.
  const authed = Boolean(session?.authenticated);
  useEffect(() => {
    if (!authed) return;
    const on = () => {
      lastActive.current = Date.now();
      if (Date.now() - lastTouch.current > TOUCH_EVERY_MS) void keepAlive();
    };
    const events = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, on, { passive: true }));
    const timer = window.setInterval(() => {
      if (!idleTotal.current) return;
      const left = idleTotal.current - (Date.now() - Math.max(lastActive.current, lastTouch.current)) / 1000;
      setIdleLeft(left);
      if (left <= 0) toLogin(true);
    }, 1000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, on));
      window.clearInterval(timer);
    };
  }, [authed, keepAlive, toLogin]);

  const logout = useCallback(async () => {
    try {
      await post("/api/logout");
    } catch {
      /* already signed out */
    }
    toLogin(false);
  }, [toLogin]);

  const value = useMemo(() => ({ session, loading, idleLeft, logout, keepAlive }), [session, loading, idleLeft, logout, keepAlive]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const IDLE_WARN_SECONDS = WARN_AT;
