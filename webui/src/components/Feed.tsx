"use client";
import { useEffect, useRef } from "react";
import { clock } from "@/lib/format";
import type { FeedItem } from "@/lib/types";

function line(item: FeedItem) {
  switch (item.kind) {
    case "user":
    case "assistant":
      return (
        <>
          <span className="who">{item.kind === "user" ? "You" : "JARVIS"}</span>
          {item.hidden ? <em className="muted">(text hidden: transcripts are off)</em> : item.text}
        </>
      );
    case "tool":
      return (
        <>
          <span className="who">tool · {item.status}</span>
          {item.tool}
          {item.label ? ` — ${item.label}` : ""}
        </>
      );
    case "route":
      return (
        <>
          <span className="who">routing</span>
          {item.resumed ? "continues" : "new conversation"} in <b>{item.profile}</b> · {item.reason}
          {item.router_ms ? ` · ${item.router_ms} ms` : ""}
        </>
      );
  }
}

export default function Feed({ items, empty }: { items: FeedItem[]; empty: string }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items.length]);
  if (!items.length) return <div className="empty">{empty}</div>;
  return (
    <div className="feed" ref={box} role="log" aria-live="polite" aria-label="Live conversation">
      {items.map((it) => (
        <div key={`${it.kind}-${it.id}`} className={`feed-item ${it.kind}`}>
          <span className="t">{clock(it.ts)}</span>
          <span>{line(it)}</span>
        </div>
      ))}
    </div>
  );
}
