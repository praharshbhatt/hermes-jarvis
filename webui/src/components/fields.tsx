"use client";
import type { ReactNode } from "react";
import { useId } from "react";

export function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id)}
      {hint ? <span className="hint">{hint}</span> : null}
    </div>
  );
}

export function TextField(p: { label: string; value: string; onChange: (v: string) => void; hint?: string; type?: "text" | "password"; autoComplete?: string }) {
  return (
    <Field label={p.label} hint={p.hint}>
      {(id) => (
        <input id={id} type={p.type ?? "text"} value={p.value} autoComplete={p.autoComplete ?? "off"} onChange={(e) => p.onChange(e.target.value)} />
      )}
    </Field>
  );
}

export function NumberField(p: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; hint?: string }) {
  return (
    <Field label={p.label} hint={p.hint}>
      {(id) => (
        <input
          id={id}
          type="number"
          value={Number.isFinite(p.value) ? p.value : ""}
          step={p.step ?? "any"}
          min={p.min}
          max={p.max}
          onChange={(e) => p.onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        />
      )}
    </Field>
  );
}

export function TextArea(p: { label: string; value: string; onChange: (v: string) => void; rows?: number; hint?: string }) {
  return (
    <Field label={p.label} hint={p.hint}>
      {(id) => <textarea id={id} rows={p.rows ?? 5} value={p.value} spellCheck={false} onChange={(e) => p.onChange(e.target.value)} />}
    </Field>
  );
}

/** One entry per line, stored as a list. */
export function LinesField(p: { label: string; value: string[]; onChange: (v: string[]) => void; rows?: number; hint?: string }) {
  return (
    <TextArea label={p.label} hint={p.hint} rows={p.rows ?? 4} value={p.value.join("\n")} onChange={(v) => p.onChange(v.split("\n"))} />
  );
}

export function Toggle(p: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <Field label={p.label} hint={p.hint}>
      {(id) => (
        <div className="check">
          <input id={id} type="checkbox" checked={p.checked} onChange={(e) => p.onChange(e.target.checked)} />
          <span>{p.checked ? "On" : "Off"}</span>
        </div>
      )}
    </Field>
  );
}

export function Message({ ok, error }: { ok?: string; error?: string }) {
  if (error) return <span className="msg bad" role="alert">{error}</span>;
  if (ok) return <span className="msg ok" role="status">{ok}</span>;
  return null;
}
