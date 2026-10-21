// Fetch wrapper for the JSON API: same-origin cookies, the CSRF token on changes, and one place that reacts to an
// expired session. Nothing here stores a secret: the session id is an HttpOnly cookie that scripts cannot read.

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let csrfToken = "";
let onUnauthorized: (() => void) | null = null;

export function setCsrf(token: string) {
  csrfToken = token;
}
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

type Options = { method?: string; body?: unknown; background?: boolean; signal?: AbortSignal };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.background) headers["X-HJ-Background"] = "1"; // polling: must not keep the session alive
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Cannot reach the hermes-jarvis service. Is it running?", 0);
  }
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* an empty or non-JSON body */
  }
  if (!res.ok) {
    const message = (data as { error?: string } | null)?.error ?? `Request failed (HTTP ${res.status})`;
    if (res.status === 401 && path !== "/api/login") onUnauthorized?.();
    throw new ApiError(message, res.status);
  }
  return data as T;
}

export const get = <T,>(path: string, background = false) => api<T>(path, { background });
export const post = <T,>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", body });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
