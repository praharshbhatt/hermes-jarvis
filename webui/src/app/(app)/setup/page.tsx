"use client";
import { useCallback, useState } from "react";
import Panel from "@/components/Panel";
import { BrainStep, DeviceStep, Finish, LiveTest, SttStep, VoiceStep, WakeStep, Welcome } from "@/components/setup/steps";
import type { StepStatus } from "@/lib/fixes";

const STEPS = [
  { id: "welcome", label: "Welcome", C: Welcome },
  { id: "brain", label: "Brain", C: BrainStep },
  { id: "stt", label: "Speech to text", C: SttStep },
  { id: "voice", label: "Voice", C: VoiceStep },
  { id: "device", label: "Device", C: DeviceStep },
  { id: "wake", label: "Wake word", C: WakeStep },
  { id: "test", label: "Live test", C: LiveTest },
  { id: "finish", label: "Finish", C: Finish },
] as const;

function Wizard() {
  const [i, setI] = useState(0);
  const [status, setStatus] = useState<Record<string, StepStatus>>({});
  const step = STEPS[i]!;
  const set = useCallback((s: StepStatus) => setStatus((m) => (m[step.id] === s ? m : { ...m, [step.id]: s })), [step.id]);
  const next = useCallback(() => setI((n) => Math.min(STEPS.length - 1, n + 1)), []);
  const done = STEPS.filter((s) => status[s.id] === "done").length;
  const Current = step.C;

  return (
    <div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={done} aria-label="Setup progress">
        <i style={{ width: `${((i + 1) / STEPS.length) * 100}%` }} />
      </div>
      <div className="wizard">
        <nav className="steps" aria-label="Setup steps">
          {STEPS.map((s, n) => {
            const st = status[s.id];
            return (
              <button key={s.id} className={`step-btn ${st === "done" ? "done" : st === "warn" ? "warn" : st === "fail" ? "fail" : ""}`} aria-current={n === i ? "step" : undefined} onClick={() => setI(n)}>
                <span className="step-num">{st === "done" ? "✓" : n + 1}</span>
                <span>{s.label}</span>
              </button>
            );
          })}
        </nav>
        <Panel title={`Step ${i + 1} of ${STEPS.length}`} sub={step.label} key={step.id}>
          <Current onStatus={set} next={next} />
        </Panel>
      </div>
    </div>
  );
}

export default function Page() {
  return <Wizard />;
}
