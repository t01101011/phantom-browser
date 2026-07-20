import { invoke } from "@tauri-apps/api/core";

export type ControlPlaneConfig = { baseUrl: string; token: string };
export type ApiErrorBody = { detail?: unknown; code?: string; message?: string };
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); this.name = "ApiError"; }
}

let config: ControlPlaneConfig | null = null;
export function configureControlPlane(next: ControlPlaneConfig) {
  config = { baseUrl: next.baseUrl.replace(/\/$/, ""), token: next.token };
}
export async function connectControlPlane(force = false): Promise<ControlPlaneConfig> {
  if (force || !config) configureControlPlane(await invoke<ControlPlaneConfig>("control_plane_config"));
  return config!;
}
export function clearControlPlaneForTests() { config = null; }

function messageFor(body: ApiErrorBody | null, fallback: string): string {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) return body.detail.map((x: { msg?: string }) => x.msg || "validation error").join("; ");
  return body?.message || fallback;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const c = await connectControlPlane();
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${c.token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`${c.baseUrl}${path}`, { ...init, headers }); }
  catch { throw new ApiError(0, "CONTROL_PLANE_UNAVAILABLE", "Không thể kết nối control plane"); }
  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try { body = await response.json(); } catch { /* non-JSON upstream */ }
    throw new ApiError(response.status, body?.code || `HTTP_${response.status}`, messageFor(body, response.statusText));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type Profile = { id:number; name:string; platform_tag:string; status:string; target_os:string; proxy_host:string; proxy_port:number; proxy_user:string; proxy_source:string; timezone:string|null; locale_language:string; locale_region:string; navigator_language:string; notes:string; folder_id:number|null; proxy_id:number|null; created_at:string; updated_at:string };
export type ProfileInput = { name:string; platform_tag:string; proxy_host?:string; proxy_port?:number; proxy_user?:string; proxy_pass?:string; timezone?:string|null; notes?:string; folder_id?:number|null; proxy_id?:number|null };
export type Folder = { id:number; name:string; parent_id:number|null; defaults_json:string; created_at:string; updated_at:string };
export type Proxy = { id:number; name:string; scheme:string; host:string; port:number; username:string; password:string; source:string; health_status:string; last_checked_at:string|null };
export type Session = { id:string; profile_id:number; mode:string; status:string; worker_pid:number|null; capabilities:{transport?:string; actions?:string[]; cdp_url?:string}; created_at:string; updated_at:string; exit_reason:string|null };
export type SessionEvent = { sequence:number; type:string; data:unknown; created_at?:string };

export const profilesApi = {
  list: () => request<{profiles:Profile[]; count:number}>("/v1/profiles"),
  create: (body:ProfileInput) => request<Profile>("/v1/profiles", {method:"POST", body:JSON.stringify(body)}),
  update: (id:number, body:Partial<ProfileInput>) => request<Profile>(`/v1/profiles/${id}`, {method:"PUT", body:JSON.stringify(body)}),
  remove: (id:number) => request<void>(`/v1/profiles/${id}`, {method:"DELETE"}),
  clone: (id:number, new_name:string) => request<Profile>(`/v1/profiles/${id}/clone`, {method:"POST", body:JSON.stringify({new_name})}),
};
export const foldersApi = {
  list: () => request<{folders:Folder[];count:number}>("/v1/folders"),
  create: (name:string) => request<Folder>("/v1/folders", {method:"POST",body:JSON.stringify({name})}),
  remove: (id:number) => request<void>(`/v1/folders/${id}`, {method:"DELETE"}),
};
export const proxiesApi = {
  list: () => request<{proxies:Proxy[];count:number}>("/v1/proxies"),
  create: (body:{name:string;scheme:string;host:string;port:number;username?:string;password?:string}) => request<Proxy>("/v1/proxies", {method:"POST",body:JSON.stringify(body)}),
  check: (id:number) => request<{proxy_id:number;status:string;latency_ms:number|null;exit_ip:string|null;error:string|null}>(`/v1/proxies/${id}/check`, {method:"POST"}),
  remove: (id:number) => request<void>(`/v1/proxies/${id}`, {method:"DELETE"}),
};
export const sessionsApi = {
  list: () => request<{sessions:Session[];count:number}>("/v1/sessions"),
  start: (profileId:number) => request<Session>(`/v1/profiles/${profileId}/sessions`, {method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()}}),
  stop: (id:string) => request<Session>(`/v1/sessions/${id}`, {method:"DELETE",headers:{"Idempotency-Key":crypto.randomUUID()}}),
};

/** Authenticated SSE over fetch (EventSource cannot set Bearer headers). Reconnects with Last-Event-ID. */
export function subscribeSessionEvents(sessionId:string, onEvent:(event:SessionEvent)=>void, onState?:(state:"connecting"|"live"|"retrying")=>void) {
  const controller = new AbortController();
  let lastId = 0, retry = 500;
  const sleep = (ms:number) => new Promise<void>(resolve => {
    const timer = setTimeout(resolve, ms);
    controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, {once:true});
  });
  const run = async () => {
    while (!controller.signal.aborted) {
      onState?.(lastId ? "retrying" : "connecting");
      try {
        const c = await connectControlPlane();
        const response = await fetch(`${c.baseUrl}/v1/sessions/${encodeURIComponent(sessionId)}/events`, {headers:{Authorization:`Bearer ${c.token}`, ...(lastId ? {"Last-Event-ID":String(lastId)} : {})}, signal:controller.signal});
        if (!response.ok || !response.body) throw new ApiError(response.status, `HTTP_${response.status}`, "SSE connection failed");
        onState?.("live"); retry = 500;
        const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
        while (!controller.signal.aborted) {
          const {done,value} = await reader.read(); if (done) break;
          buffer += decoder.decode(value,{stream:true}).replace(/\r\n/g,"\n");
          const chunks = buffer.split("\n\n"); buffer = chunks.pop() || "";
          for (const chunk of chunks) {
            let id = 0, type = "message"; const dataLines:string[] = [];
            for (const line of chunk.split("\n")) { if (line.startsWith("id:")) id=Number(line.slice(3).trim()); else if(line.startsWith("event:")) type=line.slice(6).trim(); else if(line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /,"")); }
            if (dataLines.length) {
              try { const parsed = JSON.parse(dataLines.join("\n")); lastId = id || parsed.sequence || lastId; onEvent({ sequence:lastId, type:parsed.type || type, data:parsed.data ?? parsed, created_at:parsed.created_at }); }
              catch { /* malformed event: keep stream alive and wait for the next event */ }
            }
          }
        }
      } catch { if (controller.signal.aborted) break; }
      if (!controller.signal.aborted) { onState?.("retrying"); await sleep(retry); retry=Math.min(retry*2,5000); }
    }
  };
  void run(); return () => controller.abort();
}
