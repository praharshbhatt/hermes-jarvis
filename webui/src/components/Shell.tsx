"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { LiveProvider, useLive } from "@/lib/events";
import { STATE_LABEL, mmss } from "@/lib/format";
import { useStatus } from "@/lib/hooks";
import { IDLE_WARN_SECONDS, SessionProvider, useSession } from "@/lib/session";
import Boot from "./Boot";
import { BrandMark } from "./Brand";

const NAV = [
  { href: "/", label: "Core" },
  { href: "/setup/", label: "Setup" },
  { href: "/settings/", label: "Settings" },
];

function Gate({ children }: { children: ReactNode }) {
  const { session, loading } = useSession();
  if (loading || !session?.authenticated) {
    return (
      <div className="login-wrap" aria-busy="true">
        <p className="upper muted" role="status">Authenticating…</p>
      </div>
    );
  }
  return <>{children}</>;
}

function Frame({ children }: { children: ReactNode }) {
  const path = usePathname();
  const live = useLive();
  const { session, logout, idleLeft, keepAlive } = useSession();
  const { data: status } = useStatus();
  const connected = live.device.connected;
  const warn = idleLeft !== null && idleLeft <= IDLE_WARN_SECONDS && idleLeft > 0;

  return (
    <div className="shell">
      <Boot device={live.device.name || status?.device_name || ""} brain={status?.brain.name ?? ""} />
      {warn ? (
        <div className="idle-banner" role="alert">
          <span>Session ends in {mmss(idleLeft)} for inactivity.</span>
          <button className="btn amber" onClick={() => void keepAlive()}>Stay signed in</button>
        </div>
      ) : null}
      <header className="topbar">
        <Link href="/" className="brand" aria-label="Hermes JARVIS home">
          <BrandMark />
          <span>Hermes JARVIS</span>
        </Link>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={path === n.href || path === n.href.replace(/\/$/, "") ? "page" : undefined}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="chips">
          <span className="chip" title="Voice device">
            <span className={`dot ${connected ? "ok live" : "bad"}`} />
            {connected ? live.device.name || "Device online" : "Device offline"}
          </span>
          <span className="chip" title="Live link to the service">
            <span className={`dot ${live.connected ? "ok" : "warn live"}`} />
            {live.connected ? STATE_LABEL[live.state] : "Reconnecting"}
          </span>
          <span className="chip">{session?.user}</span>
          <button className="btn ghost" onClick={() => void logout()}>Sign out</button>
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}

/** Every signed-in page: session, auth gate, live event stream, top bar. */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <Gate>
        <LiveProvider>
          <Frame>{children}</Frame>
        </LiveProvider>
      </Gate>
    </SessionProvider>
  );
}
