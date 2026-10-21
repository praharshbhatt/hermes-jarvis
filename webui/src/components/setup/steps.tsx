"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import DeviceControls from "@/components/DeviceControls";
import Reactor from "@/components/Reactor";
import VoicePicker from "@/components/VoicePicker";
import { Message } from "@/components/fields";
import { get, post, put } from "@/lib/api";
import { useLive } from "@/lib/events";
import type { StepStatus } from "@/lib/fixes";
import { useAction } from "@/lib/hooks";
import type { DoctorRow } from "@/lib/types";
import { CheckList, StepFrame, type Check } from "./parts";

type StepProps = { onStatus: (s: StepStatus) => void; next: () => void };

export function Welcome({ next, onStatus }: StepProps) {
  return (
    <StepFrame
      title="Welcome aboard"
      intro="This guide connects the pieces one at a time and checks each with a real test, so you know it works before you rely on it."
      footer={<button className="btn primary" onClick={() => { onStatus("done"); next(); }}>Begin</button>}
    >
      <ol className="muted" style={{ lineHeight: 1.9 }}>
        <li>Your <b>brain</b>: the agent or model that writes the answers.</li>
        <li><b>Speech to text</b>: turning your voice into words.</li>
        <li>A <b>voice</b> for the answers, played on your device so you can hear it.</li>
        <li>Your <b>device</b>: find it and give it a private key.</li>
        <li><b>Wake word</b> and device controls.</li>
        <li>A <b>live test</b>: say “Hey Jarvis” and watch the core react.</li>
      </ol>
    </StepFrame>
  );
}

type BrainResult = { ok: boolean; checks: Check[]; reply: string; error: string; seconds: number };
export function BrainStep({ onStatus, next }: StepProps) {
  const [res, setRes] = useState<BrainResult | null>(null);
  const run = useAction(async () => {
    const r = await post<BrainResult>("/api/check/brain");
    setRes(r);
    onStatus(r.ok ? "done" : "fail");
  });
  return (
    <StepFrame
      title="Your brain"
      intro="We ask it for a five-word greeting. That proves the address, the key and the model, and shows how it sounds."
      footer={
        <>
          <button className="btn primary" disabled={run.busy} onClick={() => void run.run()}>{run.busy ? "Asking…" : res ? "Test again" : "Test the brain"}</button>
          <button className="btn ghost" onClick={next}>{res?.ok ? "Continue" : "Skip for now"}</button>
          <Message error={run.error} />
        </>
      }
    >
      {res ? (
        <>
          <CheckList checks={res.checks} />
          {res.reply ? <div className="check-row"><span className="dot ok" style={{ marginTop: 7 }} /><div><div className="t">It answered in {res.seconds} s</div><div className="d">“{res.reply}”</div></div></div> : null}
          {res.error ? <CheckList checks={[{ label: "Test call", ok: false, detail: res.error }]} /> : null}
        </>
      ) : null}
    </StepFrame>
  );
}

type SttResult = { ok: boolean; providers: { name: string; ok: boolean; detail: string }[]; transcript: string; seconds: number };
export function SttStep({ onStatus, next }: StepProps) {
  const [res, setRes] = useState<SttResult | null>(null);
  const run = useAction(async () => {
    const r = await post<SttResult>("/api/check/stt");
    setRes(r);
    onStatus(r.ok ? "done" : "fail");
  });
  return (
    <StepFrame
      title="Speech to text"
      intro="We speak a sentence with the current voice and send it through your speech-to-text service, then compare what comes back."
      footer={
        <>
          <button className="btn primary" disabled={run.busy} onClick={() => void run.run()}>{run.busy ? "Listening…" : res ? "Test again" : "Test speech to text"}</button>
          <button className="btn ghost" onClick={next}>{res?.ok ? "Continue" : "Skip for now"}</button>
          <Message error={run.error} />
        </>
      }
    >
      {res ? (
        <>
          <CheckList checks={res.providers.map((p) => ({ label: `Provider: ${p.name}`, ok: p.ok, detail: p.detail }))} />
          {res.providers.every((p) => p.ok) ? (
            <CheckList checks={[{ label: res.ok ? `Heard it correctly in ${res.seconds} s` : "It did not hear the sentence correctly", ok: res.ok, detail: res.transcript ? `“${res.transcript}”` : "No text came back. Check the key, the network, and the provider’s status." }]} />
          ) : null}
        </>
      ) : null}
    </StepFrame>
  );
}

export function VoiceStep({ onStatus, next }: StepProps) {
  return (
    <StepFrame
      title="A voice"
      intro="Preview each voice on your device, then pick one. The first use of a voice downloads it (about 60 MB)."
      footer={<button className="btn primary" onClick={next}>Continue</button>}
    >
      <VoicePicker onChanged={() => onStatus("done")} />
    </StepFrame>
  );
}

type Found = { name: string; host: string; version: string; adopted: boolean; adoptable: boolean; likely_voice: boolean };
export function DeviceStep({ onStatus, next }: StepProps) {
  const live = useLive();
  const [found, setFound] = useState<Found[] | null>(null);
  const [host, setHost] = useState("");
  const search = useAction(async () => {
    setFound(await get<Found[]>("/api/discover"));
  });
  const adopt = useAction(async (h: string) => {
    const r = await post<{ name: string }>("/api/adopt", { host: h });
    return r;
  }, "Adopted. Connecting…");

  useEffect(() => {
    if (live.device.connected) onStatus("done");
  }, [live.device.connected, onStatus]);

  return (
    <StepFrame
      title="Your device"
      intro="Find the Voice PE on your network and give it a private encryption key. This happens once."
      footer={
        <>
          <button className="btn primary" disabled={search.busy} onClick={() => void search.run()}>{search.busy ? "Searching…" : "Search the network"}</button>
          <button className="btn ghost" onClick={next}>{live.device.connected ? "Continue" : "Skip for now"}</button>
        </>
      }
    >
      <CheckList checks={[{ label: live.device.connected ? `Connected: ${live.device.name}` : "No device connected yet", ok: live.device.connected, detail: live.device.connected ? "The live link shows it online." : "Search below, or enter its address." }]} />
      <Message error={search.error || adopt.error} ok={adopt.ok} />
      {found ? (
        found.length ? (
          <div className="voice-list">
            {found.map((d) => (
              <div className="voice-row" key={d.host}>
                <div>
                  <div>{d.name} {d.likely_voice ? <span className="badge ok">voice device</span> : null}</div>
                  <div className="muted mono" style={{ fontSize: "0.8rem" }}>{d.host} · ESPHome {d.version} · {d.adopted ? "already has a key" : d.adoptable ? "ready to adopt" : "unencrypted"}</div>
                </div>
                <button className="btn" disabled={adopt.busy} onClick={() => void adopt.run(d.host)}>{adopt.busy ? "Adopting…" : d.adopted ? "Use its key" : "Adopt"}</button>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">No devices found. Is it powered on and on the same network? You can enter its address below.</div>
        )
      ) : null}
      <div className="row">
        <input type="text" aria-label="Device address" placeholder="192.168.1.50" value={host} onChange={(e) => setHost(e.target.value)} style={{ maxWidth: 240 }} />
        <button className="btn ghost" disabled={!host.trim() || adopt.busy} onClick={() => void adopt.run(host.trim())}>Adopt this address</button>
      </div>
      <p className="muted" style={{ fontSize: "0.85rem" }}>
        A device that Home Assistant or another install already adopted keeps its key. Flash it again with “Erase device”, or set ESPHOME_API_KEY.
      </p>
    </StepFrame>
  );
}

export function WakeStep({ onStatus, next }: StepProps) {
  useEffect(() => onStatus("done"), [onStatus]);
  return (
    <StepFrame
      title="Wake word and controls"
      intro="Tune how easily the device wakes. If a TV or music sets it off, choose “Slightly sensitive”; if it misses you, choose “Very sensitive”."
      footer={<button className="btn primary" onClick={next}>Continue</button>}
    >
      <DeviceControls />
    </StepFrame>
  );
}

export function LiveTest({ onStatus, next }: StepProps) {
  const live = useLive();
  const [start] = useState(() => Date.now() / 1000 - 1); // only events after this step opened count
  const listen = useAction(() => post<{ ok: boolean }>("/api/listen-test"), "The device is listening");

  const after = (s: keyof typeof live.seen) => (live.seen[s] ?? 0) >= start;
  const heard = live.feed.find((f) => f.kind === "user" && f.ts >= start);
  const wake = after("wake") || after("followup") || after("listening") || after("speech");
  const replied = live.feed.some((f) => f.kind === "assistant" && f.ts >= start) || after("speaking");
  const done = Boolean(heard) && replied;
  useEffect(() => {
    if (done) onStatus("done");
  }, [done, onStatus]);

  const rows: Check[] = [
    { label: "Wake word heard", ok: wake, detail: "" },
    { label: "Your speech detected", ok: after("speech"), detail: "" },
    { label: "Transcribed", ok: Boolean(heard), detail: heard && heard.kind === "user" ? (heard.hidden ? "(text hidden)" : `“${heard.text}”`) : "" },
    { label: "The brain answered and the device spoke", ok: replied, detail: "" },
  ];
  return (
    <StepFrame
      title="Live test"
      intro="Say “Hey Jarvis”, then ask anything. Watch the core, and the checklist, follow along."
      footer={
        <>
          <button className="btn primary" onClick={next}>{done ? "Finish" : "Skip"}</button>
          <button className="btn ghost" disabled={!live.device.connected || listen.busy} onClick={() => void listen.run()}>Make the device listen now</button>
          <Message ok={listen.ok} error={listen.error} />
        </>
      }
    >
      <div className="live-test">
        <div className="big-prompt">{done ? "All systems go" : "Say “Hey Jarvis”"}</div>
        <Reactor state={live.state} levelRef={live.levelRef} />
      </div>
      <div className="check-list" role="list">
        {rows.map((r) => (
          <div className="check-row" role="listitem" key={r.label}>
            <span className={`dot ${r.ok ? "ok" : "warn live"}`} style={{ marginTop: 7 }} aria-label={r.ok ? "done" : "waiting"} />
            <div><div className="t">{r.label}</div>{r.detail ? <div className="d">{r.detail}</div> : null}</div>
          </div>
        ))}
      </div>
      {!live.device.connected ? <p className="msg bad">The device is offline, so there is nothing to hear yet. Go back to the Device step.</p> : null}
    </StepFrame>
  );
}

export function Finish({ onStatus }: StepProps) {
  const [rows, setRows] = useState<DoctorRow[] | null>(null);
  const [done, setDone] = useState(false);
  const check = useAction(async () => {
    setRows(await get<DoctorRow[]>("/api/doctor"));
  });
  const complete = useAction(async () => {
    await put("/api/settings", { onboarding_completed: true });
    setDone(true);
    onStatus("done");
  }, "Setup complete");
  useEffect(() => {
    void check.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const fails = rows?.filter((r) => r.level === "FAIL").length ?? 0;
  return (
    <StepFrame
      title="Final check"
      intro="Everything the doctor looks at, in one list. You can change any of it later from Settings, and run this guide again whenever you like."
      footer={
        <>
          <button className="btn primary" disabled={complete.busy || done} onClick={() => void complete.run()}>{done ? "Done" : "Mark setup complete"}</button>
          {done ? <Link className="btn" href="/">Go to the core</Link> : null}
          <button className="btn ghost" disabled={check.busy} onClick={() => void check.run()}>Check again</button>
          <Message ok={complete.ok} error={complete.error || check.error} />
        </>
      }
    >
      {rows ? (
        <>
          <p className={fails ? "msg bad" : "msg ok"}>{fails ? `${fails} problem${fails > 1 ? "s" : ""} to fix.` : "No problems found."}</p>
          <CheckList checks={rows.map((r) => ({ label: r.label, ok: r.level !== "FAIL", detail: r.detail }))} />
        </>
      ) : (
        <div className="empty">Running the checks…</div>
      )}
    </StepFrame>
  );
}
