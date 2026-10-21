import type { ReactNode } from "react";

type Props = {
  title: string;
  sub?: string;
  actions?: ReactNode;
  accent?: "cyan" | "amber";
  className?: string;
  delay?: number;
  children: ReactNode;
};

/** A glass HUD panel with corner brackets. `delay` staggers the entrance animation (ms). */
export default function Panel({ title, sub, actions, accent = "cyan", className = "", delay = 0, children }: Props) {
  return (
    <section className={`panel ${accent === "amber" ? "amber" : ""} ${className}`} style={delay ? { animationDelay: `${delay}ms` } : undefined}>
      <header className="panel-head">
        <h2 className="panel-title">{title}</h2>
        {sub ? <span className="panel-sub">{sub}</span> : null}
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}
