"use client";
import { useState } from "react";
import { get, post } from "@/lib/api";
import { useAction, usePolling } from "@/lib/hooks";
import { Message } from "./fields";

type VoiceList = { current: string; voices: { name: string; description: string; installed: boolean; current: boolean }[] };

/** Choose a speech voice, and hear it on the device first. Voices download from the Piper voice repository on first use. */
export default function VoicePicker({ onChanged }: { onChanged?: (voice: string) => void }) {
  const { data, reload } = usePolling<VoiceList>(() => get<VoiceList>("/api/voices", true), 60000);
  const [busy, setBusy] = useState("");
  const preview = useAction(async (voice: string) => {
    setBusy(voice);
    try {
      await post("/api/voices/preview", { voice });
    } finally {
      setBusy("");
    }
  }, "Playing on the device");
  const select = useAction(async (voice: string) => {
    setBusy(voice);
    try {
      await post("/api/voices/select", { voice });
      await reload();
      onChanged?.(voice);
    } finally {
      setBusy("");
    }
  }, "Voice changed");

  if (!data) return <div className="empty">Loading voices…</div>;
  return (
    <div>
      <div className="voice-list" role="list">
        {data.voices.map((v) => (
          <div key={v.name} role="listitem" className={`voice-row ${v.current ? "current" : ""}`}>
            <div>
              <div>{v.name} {v.current ? <span className="badge ok">in use</span> : null} {!v.installed ? <span className="badge">downloads on first use</span> : null}</div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>{v.description}</div>
            </div>
            <div className="row">
              <button className="btn ghost" disabled={busy !== ""} onClick={() => void preview.run(v.name)}>
                {busy === v.name && preview.busy ? "Loading…" : "Preview"}
              </button>
              <button className="btn" disabled={busy !== "" || v.current} onClick={() => void select.run(v.name)}>
                {busy === v.name && select.busy ? "Loading…" : "Use"}
              </button>
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 10 }}>
        <Message ok={preview.ok || select.ok} error={preview.error || select.error} />
      </div>
      <p className="muted" style={{ marginTop: 10, fontSize: "0.85rem" }}>
        Any Piper voice works: set <code>tts.voice</code> in config.yaml to its .onnx file. Check each voice’s license before use beyond personal use.
      </p>
    </div>
  );
}
