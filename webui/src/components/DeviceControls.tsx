"use client";
import { get, post } from "@/lib/api";
import { useAction, usePolling } from "@/lib/hooks";
import type { DeviceControl } from "@/lib/types";
import { Message } from "./fields";

type Props = { only?: string[] };

/** The device's own controls: wake word sensitivity, mute, wake sound. Applied immediately. */
export default function DeviceControls({ only }: Props) {
  const { data, reload } = usePolling(() => get<{ connected: boolean; controls: DeviceControl[] }>("/api/device", true), 6000);
  const send = useAction(async (name: string, value: string) => {
    await post("/api/device", { name, value });
    await reload();
  }, "Applied");

  if (!data) return <div className="empty">Loading…</div>;
  if (!data.connected) return <div className="empty">The device is not connected. Controls appear when it is.</div>;
  const controls = data.controls.filter((c) => !only || only.includes(c.name));
  return (
    <div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Control</th><th>Value</th></tr></thead>
          <tbody>
            {controls.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>
                  {c.kind === "select" ? (
                    <select aria-label={c.name} value={String(c.state ?? "")} onChange={(e) => void send.run(c.name, e.target.value)}>
                      {(c.options ?? []).map((o) => <option key={o}>{o}</option>)}
                    </select>
                  ) : c.kind === "switch" ? (
                    <input type="checkbox" aria-label={c.name} checked={Boolean(c.state)} onChange={(e) => void send.run(c.name, e.target.checked ? "on" : "off")} />
                  ) : c.kind === "number" ? (
                    <input type="number" aria-label={c.name} min={c.min} max={c.max} step={c.step || "any"} defaultValue={Number(c.state ?? 0)} onBlur={(e) => void send.run(c.name, e.target.value)} />
                  ) : (
                    <button className="btn ghost" onClick={() => void send.run(c.name, "press")}>Press</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Message ok={send.ok} error={send.error} />
    </div>
  );
}
