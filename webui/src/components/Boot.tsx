"use client";
import { useEffect, useState } from "react";

type Props = { device: string; brain: string };

/** A short power-up sequence, once per browser tab. Any key or click skips it. It never shows under reduced motion. */
export default function Boot({ device, brain }: Props) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      if (sessionStorage.getItem("hj-booted")) return;
      sessionStorage.setItem("hj-booted", "1");
    } catch {
      return; // storage blocked: skip the intro rather than show it on every page
    }
    const start = window.setTimeout(() => setShow(true), 0); // begin after mount
    const t = window.setTimeout(() => setShow(false), 3500);
    const skip = () => setShow(false);
    window.addEventListener("keydown", skip, { once: true });
    return () => {
      window.clearTimeout(start);
      window.clearTimeout(t);
      window.removeEventListener("keydown", skip);
    };
  }, []);

  if (!show) return null;
  const lines: [string, string][] = [
    ["HERMES-JARVIS // CORE SEQUENCE", ""],
    ["Initialising audio link", "OK"],
    ["Voice device", device || "SEARCHING"],
    ["Brain", brain || "STANDBY"],
    ["Security: session sealed", "OK"],
    ["All systems nominal", ""],
  ];
  return (
    <div className="boot" role="presentation" onClick={() => setShow(false)}>
      <div className="boot-inner" aria-hidden="true">
        {lines.map(([a, b], i) => (
          <div key={a} className="boot-line" style={{ animationDelay: `${i * 380}ms` }}>
            {a} {b ? <b>[{b}]</b> : null}
          </div>
        ))}
        <div className="boot-bar">
          <i />
        </div>
        <div className="boot-skip">press any key to skip</div>
      </div>
    </div>
  );
}
