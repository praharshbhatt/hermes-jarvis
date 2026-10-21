"use client";
import type { ReactNode } from "react";
import { fixFor } from "@/lib/fixes";

export type Check = { label: string; ok: boolean; detail: string };

/** A list of check results with a suggested fix under each failure. */
export function CheckList({ checks }: { checks: Check[] }) {
  return (
    <div className="check-list" role="list">
      {checks.map((c) => {
        const fix = c.ok ? null : fixFor(c.label, c.detail);
        return (
          <div className="check-row" role="listitem" key={c.label}>
            <span className={`dot ${c.ok ? "ok" : "bad"}`} aria-label={c.ok ? "passed" : "failed"} style={{ marginTop: 7 }} />
            <div>
              <div className="t">{c.label}</div>
              {c.detail ? <div className="d">{c.detail}</div> : null}
              {fix ? <div className="fix"><b>How to fix:</b> {fix}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function StepFrame({ title, intro, children, footer }: { title: string; intro: string; children?: ReactNode; footer?: ReactNode }) {
  return (
    <div className="stack">
      <div>
        <h2 style={{ fontSize: "1.25rem", marginBottom: 6 }}>{title}</h2>
        <p className="muted">{intro}</p>
      </div>
      {children}
      {footer ? <div className="row" style={{ marginTop: 6 }}>{footer}</div> : null}
    </div>
  );
}
