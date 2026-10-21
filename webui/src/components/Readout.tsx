"use client";
import { useCountUp } from "@/lib/motion";

type Props = { label: string; value: number | null; unit?: string; decimals?: number; text?: string };

/** A HUD readout. Numbers count up to their value; `text` shows a plain string instead. */
export default function Readout({ label, value, unit, decimals = 0, text }: Props) {
  const counted = useCountUp(value ?? 0, 700, decimals);
  return (
    <div className="readout">
      <div className="label">{label}</div>
      <div className={`value ${text !== undefined ? "text" : ""}`} title={text}>
        {text !== undefined ? text : value === null ? "–" : counted}
        {unit && value !== null && text === undefined ? <small>{unit}</small> : null}
      </div>
    </div>
  );
}
