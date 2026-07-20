// Sidecar JSON-RPC envelope types — mirrors docs/sidecar-contract.md.
// The Rust `sidecar_call(action, args)` command returns the envelope as a
// serde_json::Value; we cast it to SidecarEnvelope<T> for type-safe access.

export type SidecarEnvelope<T> =
  | { ok: true; data: T }
  | { ok: false; error: SidecarError };

export interface SidecarError {
  code: SidecarErrorCode;
  message: string;
  detail?: string | null;
}

export type SidecarErrorCode =
  | "bad_args"
  | "not_found"
  | "bad_proxy"
  | "already_running"
  | "still_running"
  | "no_log"
  | "panic"
  | "no_output"
  | "bad_json"
  | "unknown";

// --- Profile (GUI-facing, no secrets — sidecar strips them server-side) ----

export interface Profile {
  id: number;
  name: string;
  platform_tag: "facebook" | "tiktok" | "chatgpt" | "custom";
  status: "idle" | "running";
  proxy_host: string;
  proxy_port: number;
  proxy_user: string;
  proxy_source: "manual" | "iproyal" | "file";
  target_os: "windows" | "macos" | "linux";
  timezone: string | null;
  locale_language: string;
  locale_region: string;
  navigator_language: string;
  user_data_dir: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface Preset {
  platform_tag: string;
  target_os: string;
  locale_region: string;
  navigator_language: string;
  timezone_default: string | null;
  proxy_required: boolean;
  proxy_kind: string | null;
  notes_default: string;
}

export interface PresetsResponse {
  presets: Record<string, Preset>;
}

export interface ListResponse {
  profiles: Profile[];
  count: number;
}

export interface CreateResponse {
  profile: Profile;
  duplicate_proxy_count: number;
}

export interface LaunchResponse {
  profile_id: number;
  pid: number;
  log_path: string;
}

export interface StopResponse {
  profile_id: number;
  stopped: boolean;
  previous_pid: number | null;
}

export interface DeleteResponse {
  profile_id: number;
  deleted: boolean;
}

export interface StatusResponse {
  profile_id: number;
  status: "idle" | "running";
  running: boolean;
  pid: number | null;
  log_path: string | null;
}

export interface LogTailResponse {
  profile_id: number;
  bytes: number;
  log: string;
}
