export type PipelineState =
  | "idle"
  | "wake"
  | "listening"
  | "speech"
  | "thinking"
  | "speaking"
  | "stopped"
  | "followup";

export type Settings = {
  session_window_minutes: number;
  recent_sessions_count: number;
  match_sources: string[];
  router_enabled: boolean;
  router_model: string;
  router_url: string;
  router_timeout_s: number;
  profile_threshold: number;
  session_threshold: number;
  router_profile_instructions: string;
  router_session_instructions: string;
  vad_silence_s: number;
  no_speech_s: number;
  followup_no_speech_s: number;
  followup_enabled: boolean;
  followup_window_minutes: number;
  followup_ignore_phrases: string[];
  tts_voice: string;
  address_as: string;
  piper_length_scale: number;
  piper_noise_scale: number;
  piper_noise_w_scale: number;
  ack_after_s: number;
  canned_acks: string[];
  voice_prompt: string;
  profiles: Profile[];
  onboarding_completed: boolean;
};

export type Profile = { name: string; description: string; enabled: boolean; is_default: boolean };

export type Status = {
  device_connected: boolean;
  device_name: string;
  uptime_s: number;
  state: PipelineState;
  session_id: string | null;
  profile: string;
  minutes_since_voice_activity: number | null;
  brain: { name: string; profiles: boolean; sessions: boolean };
  router_available: boolean;
  persona: string;
  stt: string;
  voice: string;
  onboarding_completed: boolean;
  secrets: Record<string, boolean>;
  profile_keys: Record<string, boolean>;
};

export type SessionInfo = {
  authenticated: boolean;
  user: string;
  csrf?: string;
  idle_seconds?: number;
  expires_in?: number;
};

export type Turn = {
  ts: number;
  text: string;
  profile: string;
  route: { reason?: string; router_ms?: number } | null;
  first_speech_s: number | null;
  total_s: number;
  spoken_chars: number;
  listen_after?: boolean;
};

export type DeviceControl = {
  name: string;
  id: string;
  kind: "select" | "switch" | "number" | "button";
  state: string | boolean | number | null;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
};

export type RouteResult = {
  profile: string;
  session_id: string | null;
  reason: string;
  router_ms: number;
  profile_probs: Record<string, number>;
  session_probs: Record<string, number>;
  candidates: { id: string; profile: string; title: string; age_min: number }[];
};

export type HistoryEntry = { ts: number; who: string; key: string; old: unknown; new: unknown };
export type DoctorRow = { level: "ok" | "warn" | "FAIL"; label: string; detail: string };

export type LiveEvent =
  | { type: "state"; id: number; ts: number; state: PipelineState }
  | { type: "transcript"; id: number; ts: number; role: "user" | "assistant"; text: string; hidden: boolean }
  | { type: "tool"; id: number; ts: number; tool: string; label: string; status: string }
  | { type: "route"; id: number; ts: number; profile: string; reason: string; router_ms: number; resumed: boolean }
  | { type: "device"; id: number; ts: number; connected: boolean; name: string }
  | { type: "level"; id: number; ts: number; value: number };

export type FeedItem =
  | { kind: "user" | "assistant"; id: number; ts: number; text: string; hidden: boolean }
  | { kind: "tool"; id: number; ts: number; tool: string; label: string; status: string }
  | { kind: "route"; id: number; ts: number; profile: string; reason: string; router_ms: number; resumed: boolean };
