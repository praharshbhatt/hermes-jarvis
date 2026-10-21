"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Panel from "@/components/Panel";
import Reactor from "@/components/Reactor";
import { Field } from "@/components/fields";
import { ApiError, get, post, setCsrf } from "@/lib/api";
import { useSearchParam } from "@/lib/browser";
import { SessionProvider, useSession } from "@/lib/session";
import type { PipelineState, SessionInfo, Status } from "@/lib/types";

function Login() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [user, setUser] = useState("admin");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [granted, setGranted] = useState(false);
  const expired = useSearchParam("expired") === "1";
  const pwRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    pwRef.current?.focus();
  }, []);

  const goHome = async () => {
    let target = "/";
    try {
      const s = await get<Status>("/api/status");
      if (!s.onboarding_completed) target = "/setup/";
    } catch {
      /* the dashboard will show the problem */
    }
    router.replace(target);
  };

  useEffect(() => {
    if (!loading && session?.authenticated) void goHome();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, session?.authenticated]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !password) return;
    setBusy(true);
    setError("");
    try {
      const s = await post<SessionInfo>("/api/login", { username: user, password });
      if (s.csrf) setCsrf(s.csrf);
      setGranted(true);
      setPassword("");
      window.setTimeout(() => void goHome(), 700);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      setPassword("");
      pwRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const state: PipelineState = granted ? "wake" : busy ? "thinking" : error ? "stopped" : "idle";

  return (
    <div className="login-wrap">
      <div className="login-card">
        <Reactor state={state} className="login-reactor" />
        <Panel title="Secure access" accent={error ? "amber" : "cyan"}>
          <h1 className="login-title">Hermes JARVIS</h1>
          <p className="login-sub">Identify yourself to continue.</p>
          {expired ? <p className="msg bad" role="status">Your session ended. Sign in again.</p> : null}
          <form onSubmit={submit} className="stack" noValidate>
            <Field label="User">
              {(id) => <input id={id} type="text" value={user} autoComplete="username" onChange={(e) => setUser(e.target.value)} />}
            </Field>
            <Field label="Password">
              {(id) => (
                <div className="pw">
                  <input
                    id={id}
                    ref={pwRef}
                    type={show ? "text" : "password"}
                    value={password}
                    autoComplete="current-password"
                    onChange={(e) => setPassword(e.target.value)}
                    aria-invalid={Boolean(error)}
                    aria-describedby="login-error"
                  />
                  <button type="button" className="btn ghost" onClick={() => setShow((v) => !v)} aria-pressed={show}>
                    {show ? "Hide" : "Show"}
                  </button>
                </div>
              )}
            </Field>
            <div id="login-error" role="alert" aria-live="assertive" className="msg bad">{error}</div>
            <button className="btn primary" type="submit" disabled={busy || !password}>
              {granted ? "Access granted" : busy ? "Verifying…" : "Authenticate"}
            </button>
          </form>
        </Panel>
        <p className="login-sub" style={{ marginTop: 16 }}>
          The password is the ADMIN_PASSWORD (or its hash) in your hermes-jarvis <code>.env</code>.
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <SessionProvider requireAuth={false}>
      <Login />
    </SessionProvider>
  );
}
