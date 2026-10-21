"use client";
import { useState, type ReactNode } from "react";
import DeviceControls from "@/components/DeviceControls";
import RouteResultView from "@/components/RouteResult";
import VoicePicker from "@/components/VoicePicker";
import { LinesField, Message, NumberField, TextArea, TextField, Toggle } from "@/components/fields";
import { get, post } from "@/lib/api";
import { dateTime, short } from "@/lib/format";
import { useAction, usePolling } from "@/lib/hooks";
import type { HistoryEntry, Profile, RouteResult, Settings, Status } from "@/lib/types";

type TabProps = { settings: Settings; save: (p: Partial<Settings>) => Promise<string[]>; status: Status | null };

/** Local copy of some settings that is saved together. */
function useDraft<K extends keyof Settings>(settings: Settings, keys: K[]) {
  const pick = () => Object.fromEntries(keys.map((k) => [k, settings[k]])) as Pick<Settings, K>;
  const [draft, setDraft] = useState(pick);
  const [base, setBase] = useState(settings);
  if (base !== settings) {
    // new values arrived from the server (after a save): start the form again from them
    setBase(settings);
    setDraft(pick());
  }
  const set = <P extends K>(k: P, v: Settings[P]) => setDraft((d) => ({ ...d, [k]: v }));
  return { draft, set };
}

function SaveRow({ onSave, label = "Save" }: { onSave: () => Promise<unknown>; label?: string }) {
  const a = useAction(async () => {
    await onSave();
  }, "Saved");
  return (
    <div className="row" style={{ marginTop: 16 }}>
      <button className="btn primary" disabled={a.busy} onClick={() => void a.run()}>{a.busy ? "Saving…" : label}</button>
      <Message ok={a.ok} error={a.error} />
    </div>
  );
}

export function RoutingTab({ settings, save, status }: TabProps) {
  const { draft: d, set } = useDraft(settings, ["session_window_minutes", "recent_sessions_count", "match_sources", "router_enabled", "router_model", "router_url", "router_timeout_s", "session_threshold", "profile_threshold", "router_profile_instructions", "router_session_instructions"]);
  return (
    <div className="stack">
      <p className="muted">
        Within the window a conversation simply continues, with no model call. After it, the router matches your request to a recent conversation or starts a new one.
        {status && !status.router_available ? " The router is off: it needs OPENROUTER_API_KEY and a Hermes brain." : ""}
      </p>
      <div className="grid">
        <NumberField label="Window (minutes)" value={d.session_window_minutes} step={0.5} onChange={(v) => set("session_window_minutes", v)} />
        <NumberField label="Recent conversations considered" value={d.recent_sessions_count} step={1} min={1} max={50} onChange={(v) => set("recent_sessions_count", v)} />
        <NumberField label="Resume threshold (0 to 1)" value={d.session_threshold} step={0.01} onChange={(v) => set("session_threshold", v)} />
        <NumberField label="Profile threshold (0 to 1)" value={d.profile_threshold} step={0.01} onChange={(v) => set("profile_threshold", v)} />
        <NumberField label="Router timeout (s)" value={d.router_timeout_s} step={0.5} onChange={(v) => set("router_timeout_s", v)} />
        <Toggle label="Router enabled" checked={d.router_enabled} onChange={(v) => set("router_enabled", v)} />
        <TextField label="Router model id" value={d.router_model} onChange={(v) => set("router_model", v)} />
        <TextField label="Router endpoint" value={d.router_url} onChange={(v) => set("router_url", v)} hint="OpenRouter’s experimental decisions API" />
      </div>
      <LinesField label="Sources that may be resumed (one per line)" value={d.match_sources} onChange={(v) => set("match_sources", v)} rows={2} />
      <TextArea label="Profile question (instructions to the router)" value={d.router_profile_instructions} onChange={(v) => set("router_profile_instructions", v)} rows={3} />
      <TextArea label="Conversation question (instructions to the router)" value={d.router_session_instructions} onChange={(v) => set("router_session_instructions", v)} rows={3} />
      <SaveRow onSave={() => save({ ...d, match_sources: d.match_sources.filter((x) => x.trim()) })} />
    </div>
  );
}

export function ProfilesTab({ settings, save, status }: TabProps) {
  const [rows, setRows] = useState<Profile[]>(settings.profiles);
  const [base, setBase] = useState(settings.profiles);
  if (base !== settings.profiles) {
    setBase(settings.profiles);
    setRows(settings.profiles);
  }
  const patch = (i: number, p: Partial<Profile>) => setRows((r) => r.map((x, n) => (n === i ? { ...x, ...p } : x)));
  return (
    <div className="stack">
      <p className="muted">
        Hermes profiles only. The description is what the router reads to decide where a request belongs. Each non-default profile needs its own API key in the environment (for example HERMES_API_KEY_WORK). Adding a profile here does not create it in Hermes.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Description (what goes here)</th><th>Enabled</th><th>Default</th><th>Key</th><th /></tr></thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={i}>
                <td><input type="text" aria-label="Profile name" value={p.name} readOnly={p.is_default && p.name === "default"} onChange={(e) => patch(i, { name: e.target.value })} /></td>
                <td><textarea aria-label="Profile description" rows={2} value={p.description} onChange={(e) => patch(i, { description: e.target.value })} /></td>
                <td><input type="checkbox" aria-label="Enabled" checked={p.enabled} onChange={(e) => patch(i, { enabled: e.target.checked })} /></td>
                <td><input type="radio" name="default-profile" aria-label="Default profile" checked={p.is_default} onChange={() => setRows((r) => r.map((x, n) => ({ ...x, is_default: n === i })))} /></td>
                <td>{status?.profile_keys[p.name] ? <span className="badge ok">set</span> : <span className="badge bad">missing</span>}</td>
                <td><button className="btn danger" disabled={p.is_default} onClick={() => setRows((r) => r.filter((_, n) => n !== i))}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row">
        <button className="btn ghost" onClick={() => setRows((r) => [...r, { name: "", description: "", enabled: true, is_default: false }])}>Add profile</button>
      </div>
      <SaveRow onSave={() => save({ profiles: rows })} label="Save profiles" />
    </div>
  );
}

export function ListeningTab({ settings, save }: TabProps) {
  const { draft: d, set } = useDraft(settings, ["vad_silence_s", "no_speech_s"]);
  return (
    <div className="stack">
      <p className="muted">How the device decides you have finished speaking, and how long it waits for you to start.</p>
      <div className="grid">
        <NumberField label="End of speech after quiet for (s)" value={d.vad_silence_s} step={0.1} onChange={(v) => set("vad_silence_s", v)} />
        <NumberField label="Wait for the first word for (s)" value={d.no_speech_s} step={0.5} onChange={(v) => set("no_speech_s", v)} />
      </div>
      <SaveRow onSave={() => save(d)} />
    </div>
  );
}

export function FollowupTab({ settings, save, status }: TabProps) {
  const { draft: d, set } = useDraft(settings, ["followup_enabled", "followup_window_minutes", "followup_no_speech_s", "followup_ignore_phrases"]);
  const listen = useAction(() => post<{ ok: boolean }>("/api/listen-test"), "The device should be listening now");
  return (
    <div className="stack">
      <p className="muted">
        When the last thing JARVIS says is a question, the device starts listening by itself once the reply has finished playing. It does not listen if you said stop, or if the question comes from a request older than the window (a long job that finished later).
      </p>
      <div className="grid">
        <Toggle label="Listen after a question" checked={d.followup_enabled} onChange={(v) => set("followup_enabled", v)} />
        <NumberField label="Only if the request was within (minutes)" value={d.followup_window_minutes} step={0.5} onChange={(v) => set("followup_window_minutes", v)} />
        <NumberField label="Wait for an answer for (s)" value={d.followup_no_speech_s} step={0.5} onChange={(v) => set("followup_no_speech_s", v)} />
      </div>
      <LinesField label="Closing phrases that do not need an answer (one per line)" value={d.followup_ignore_phrases} onChange={(v) => set("followup_ignore_phrases", v)} rows={2} />
      <div className="row">
        <button className="btn primary" onClick={() => void save({ ...d, followup_ignore_phrases: d.followup_ignore_phrases.filter((x) => x.trim()) })}>Save</button>
        <button className="btn ghost" disabled={!status?.device_connected || listen.busy} onClick={() => void listen.run()}>Test: make the device listen now</button>
        <Message ok={listen.ok} error={listen.error} />
      </div>
    </div>
  );
}

export function VoiceTab({ settings, save }: TabProps) {
  const { draft: d, set } = useDraft(settings, ["piper_length_scale", "piper_noise_scale", "piper_noise_w_scale", "ack_after_s", "address_as", "canned_acks", "voice_prompt"]);
  return (
    <div className="stack">
      <VoicePicker />
      <hr className="hr" />
      <div className="grid">
        <NumberField label="Speech length scale (bigger is slower)" value={d.piper_length_scale} step={0.05} onChange={(v) => set("piper_length_scale", v)} />
        <NumberField label="Noise scale" value={d.piper_noise_scale} step={0.01} onChange={(v) => set("piper_noise_scale", v)} />
        <NumberField label="Noise width" value={d.piper_noise_w_scale} step={0.01} onChange={(v) => set("piper_noise_w_scale", v)} />
        <NumberField label="Say an acknowledgement after (s without speech)" value={d.ack_after_s} step={0.1} onChange={(v) => set("ack_after_s", v)} />
        <TextField label="Address me as" value={d.address_as} onChange={(v) => set("address_as", v)} hint="fills {address} in the acknowledgements" />
      </div>
      <LinesField label="Canned acknowledgements (one per line)" value={d.canned_acks} onChange={(v) => set("canned_acks", v)} rows={5} />
      <TextArea label="Voice-mode prompt sent to the brain on every turn" value={d.voice_prompt} onChange={(v) => set("voice_prompt", v)} rows={9} />
      <SaveRow onSave={() => save({ ...d, canned_acks: d.canned_acks.filter((x) => x.trim()) })} />
    </div>
  );
}

export function DeviceTab() {
  return (
    <div className="stack">
      <p className="muted">The device’s own controls, as they appear on a Home Assistant device page. Wake word sensitivity is the main fix for false triggers. Changes apply immediately.</p>
      <DeviceControls />
    </div>
  );
}

export function RouterTestTab({ status }: TabProps) {
  const [text, setText] = useState("");
  const [ignore, setIgnore] = useState(true);
  const [result, setResult] = useState<RouteResult | null>(null);
  const run = useAction(async () => {
    setResult(await post<RouteResult>("/api/route-test", { text, ignore_window: ignore }));
  });
  if (status && !status.router_available) return <div className="empty">The router is off, so there is nothing to test. It needs a Hermes brain and an OPENROUTER_API_KEY.</div>;
  return (
    <div className="stack">
      <p className="muted">Runs the routing decision only. Nothing is spoken and nothing is sent to the brain.</p>
      <div className="row">
        <input type="text" aria-label="A request to route" style={{ flex: "1 1 320px" }} value={text} placeholder="e.g. what’s the status of the October invoice" onChange={(e) => setText(e.target.value)} />
        <label className="check"><input type="checkbox" checked={ignore} onChange={(e) => setIgnore(e.target.checked)} /> ignore the window</label>
        <button className="btn primary" disabled={run.busy || !text.trim()} onClick={() => void run.run()}>{run.busy ? "Routing…" : "Route"}</button>
      </div>
      <Message error={run.error} />
      {result ? <RouteResultView r={result} /> : null}
    </div>
  );
}

export function HistoryTab() {
  const { data } = usePolling<HistoryEntry[]>(() => get<HistoryEntry[]>("/api/history", true), 30000);
  if (!data) return <div className="empty">Loading…</div>;
  if (!data.length) return <div className="empty">No changes yet.</div>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Time</th><th>Setting</th><th>Old</th><th>New</th></tr></thead>
        <tbody>
          {data.map((h, i) => (
            <tr key={i}><td className="mono">{dateTime(h.ts)}</td><td>{h.key}</td><td>{short(h.old)}</td><td>{short(h.new)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type Tab = { id: string; label: string; show: (s: Status | null) => boolean; render: (p: TabProps) => ReactNode };
export const TABS: Tab[] = [
  { id: "routing", label: "Routing", show: (s) => !s || s.brain.sessions, render: (p) => <RoutingTab {...p} /> },
  { id: "profiles", label: "Profiles", show: (s) => !s || s.brain.profiles, render: (p) => <ProfilesTab {...p} /> },
  { id: "listening", label: "Listening", show: () => true, render: (p) => <ListeningTab {...p} /> },
  { id: "followup", label: "Follow-up", show: () => true, render: (p) => <FollowupTab {...p} /> },
  { id: "voice", label: "Voice", show: () => true, render: (p) => <VoiceTab {...p} /> },
  { id: "device", label: "Device", show: () => true, render: () => <DeviceTab /> },
  { id: "router-test", label: "Router test", show: (s) => !s || s.brain.sessions, render: (p) => <RouterTestTab {...p} /> },
  { id: "history", label: "History", show: () => true, render: () => <HistoryTab /> },
];
