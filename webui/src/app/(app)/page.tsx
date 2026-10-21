"use client";
import Link from "next/link";
import { useMemo } from "react";
import Feed from "@/components/Feed";
import Panel from "@/components/Panel";
import Reactor from "@/components/Reactor";
import Readout from "@/components/Readout";
import { Message } from "@/components/fields";
import { get, post } from "@/lib/api";
import { useLive } from "@/lib/events";
import { STATE_LABEL, dateTime, duration } from "@/lib/format";
import { useAction, usePolling, useStatus } from "@/lib/hooks";
import type { PipelineState, Turn } from "@/lib/types";

const HINT: Record<PipelineState, string> = {
  idle: "Say “Hey Jarvis”.",
  wake: "Wake word heard.",
  listening: "I’m listening.",
  speech: "Hearing you.",
  thinking: "Working on it…",
  speaking: "Speaking. Say “stop” to interrupt.",
  stopped: "Stopped.",
  followup: "Waiting for your answer. Just speak.",
};

function Dashboard() {
  const live = useLive();
  const { data: status } = useStatus();
  const { data: turns } = usePolling<Turn[]>(() => get<Turn[]>("/api/turns", true), 15000);
  const listen = useAction(() => post<{ ok: boolean }>("/api/listen-test"), "Listening now");

  const stats = useMemo(() => {
    const list = turns ?? [];
    const first = list.map((t) => t.first_speech_s).filter((n): n is number => typeof n === "number");
    const routed = list.map((t) => t.route?.router_ms ?? 0).filter((n) => n > 0);
    const avg = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
    return { turns: list.length, first: avg(first), router: avg(routed) };
  }, [turns]);

  return (
    <div className="stack">
      {status && !status.onboarding_completed ? (
        <Panel title="Finish setup" accent="amber" sub="A few minutes, guided">
          <div className="row">
            <span>Connect your brain, speech service, voice and device, then try a live test.</span>
            <Link className="btn amber" href="/setup/">Start the setup guide</Link>
          </div>
        </Panel>
      ) : null}

      <div className="dash">
        <Panel title="Core" sub={live.connected ? "live" : "reconnecting…"} className="core-panel">
          <Reactor state={live.state} levelRef={live.levelRef} />
          <div className="core-label" aria-live="polite">
            <div className="core-state" data-state={live.state}>{STATE_LABEL[live.state]}</div>
            <div className="core-hint">{HINT[live.state]}</div>
          </div>
          <div className="row" style={{ justifyContent: "center", marginTop: 14 }}>
            <button className="btn" disabled={!live.device.connected || listen.busy} onClick={() => void listen.run()}>
              Listen now
            </button>
            <Link className="btn ghost" href="/setup/">Setup guide</Link>
          </div>
          <div style={{ textAlign: "center", marginTop: 8 }}><Message ok={listen.ok} error={listen.error} /></div>
        </Panel>

        <div className="stack">
          <Panel title="Live feed" sub="what is being said and done" delay={80}>
            <Feed items={live.feed} empty="Nothing yet. Say “Hey Jarvis” to the device." />
          </Panel>
          <Panel title="Systems" delay={160}>
            <div className="readouts">
              <Readout label="Uptime" value={null} text={status ? duration(status.uptime_s) : "–"} />
              <Readout label="Last voice" value={status?.minutes_since_voice_activity ?? null} unit="min ago" decimals={1} />
              <Readout label="Turns logged" value={stats.turns} />
              <Readout label="First speech" value={stats.first} unit="s" decimals={1} />
              {status?.router_available ? <Readout label="Router" value={stats.router} unit="ms" /> : null}
              <Readout label="Brain" value={null} text={status?.brain.name ?? "–"} />
              <Readout label="Speech to text" value={null} text={status?.stt ?? "–"} />
              <Readout label="Voice" value={null} text={status?.voice?.replace(/^en_/, "").replace(/-medium$/, "") ?? "–"} />
            </div>
            {status ? (
              <div className="row" style={{ marginTop: 12 }}>
                {Object.entries(status.secrets).map(([k, ok]) => (
                  <span key={k} className={`badge ${ok ? "ok" : "bad"}`}>{k} {ok ? "set" : "missing"}</span>
                ))}
              </div>
            ) : null}
          </Panel>
        </div>
      </div>

      <Panel title="Recent turns" sub="newest first" delay={240}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Time</th><th>Heard</th><th>Profile</th><th>Route</th><th>Router</th><th>First speech</th><th>Total</th></tr>
            </thead>
            <tbody>
              {(turns ?? []).slice(0, 12).map((t) => (
                <tr key={t.ts}>
                  <td className="mono">{dateTime(t.ts)}</td>
                  <td>{t.text || <em className="muted">hidden</em>}</td>
                  <td>{t.profile}</td>
                  <td>{t.route?.reason ?? ""}</td>
                  <td className="num">{t.route?.router_ms ? `${t.route.router_ms} ms` : ""}</td>
                  <td className="num">{t.first_speech_s != null ? `${t.first_speech_s} s` : ""}</td>
                  <td className="num">{t.total_s} s</td>
                </tr>
              ))}
            </tbody>
          </table>
          {turns && turns.length === 0 ? <div className="empty">No turns yet.</div> : null}
        </div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return <Dashboard />;
}
