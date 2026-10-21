import type { RouteResult } from "@/lib/types";

function Bars({ title, probs, names }: { title: string; probs: Record<string, number>; names?: Record<string, string> }) {
  const rows = Object.entries(probs).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <div className="upper muted" style={{ marginBottom: 6 }}>{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "grid", gridTemplateColumns: "44px 1fr 2fr", gap: 10, alignItems: "center", marginBottom: 4 }}>
          <span className="mono">{v.toFixed(2)}</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{names?.[k] ?? k}</span>
          <div className="bar" aria-hidden="true"><i style={{ width: `${Math.round(v * 100)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

/** The router's decision with its probabilities, as bars. */
export default function RouteResultView({ r }: { r: RouteResult }) {
  const names: Record<string, string> = {};
  r.candidates.forEach((c) => (names[c.id] = `[${c.profile}] ${c.title}`));
  const target = r.session_id ? `resume ${names[r.session_id] ?? r.session_id}` : "start a new conversation";
  return (
    <div className="stack" aria-live="polite">
      <div>
        <span className="badge ok">{r.reason}</span>{" "}
        <b>{r.profile}</b> · {target} · <span className="mono">{r.router_ms} ms</span>
      </div>
      {Object.keys(r.profile_probs).length ? <Bars title="Profile" probs={r.profile_probs} /> : null}
      {Object.keys(r.session_probs).length ? <Bars title="Conversation" probs={r.session_probs} names={names} /> : null}
    </div>
  );
}
