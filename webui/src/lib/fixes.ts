/** Plain-language next steps for a failed check, from the label and detail the service reports. */
export function fixFor(label: string, detail: string): string | null {
  const l = label.toLowerCase();
  const d = detail.toLowerCase();

  const missing = /missing: set ([A-Z0-9_]+)/i.exec(detail);
  if (missing) return `Add ${missing[1]} to the .env file next to config.yaml, then restart hermes-jarvis.`;
  if (d.includes("not installed") && d.includes("faster-whisper"))
    return "Install the local speech option: pip install 'hermes-jarvis[local-stt]', then restart.";
  if (d.includes("invalid gateway api key") || d.includes("http 401") || d.includes("wrong key") || d.includes("key or url wrong"))
    return "The key was refused. For Hermes, the API_SERVER_KEY in Hermes’ own data-folder .env overrides its container settings: make sure HERMES_API_KEY here matches that one.";
  if (l.includes("reachable") || d.includes("cannot connect") || d.includes("connection refused") || d.includes("refused"))
    return "Is it running? Check brain.base_url in config.yaml. Hermes can take several minutes to answer after a restart.";
  if (d.includes("no answer within")) return "The brain is slow or stuck. Try a simpler model, or check its own logs.";
  if (l.includes("voice device") || d.includes("none found"))
    return "Power the device on and make sure it is on the same network, then use the Device step to find it.";
  if (d.includes("does not match") || d.includes("encryption key we do not have") || d.includes("already has an encryption key"))
    return "The device already has a key. Flash it again with “Erase device”, or set ESPHOME_API_KEY to its key.";
  if (d.includes("timeout") || d.includes("timed out")) return "The service did not answer in time. Check the network and try again.";
  if (l.includes("stop word")) return "Flash the hermes-jarvis firmware so “stop” can silence queued speech.";
  return null;
}

export type StepStatus = "todo" | "done" | "warn" | "fail";
export const worst = (a: StepStatus, b: StepStatus): StepStatus => {
  const order: StepStatus[] = ["todo", "done", "warn", "fail"];
  return order[Math.max(order.indexOf(a), order.indexOf(b))] ?? a;
};
