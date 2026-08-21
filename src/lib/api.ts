/**
 * One request helper for every API client.
 *
 * It replaces three near-identical `handle`/`request` functions that used to
 * live in uploadApi, forumApi and gameApi, and it is where the session token
 * gets attached. Nothing else in the app should call `fetch` against `/api`.
 *
 * The token lives in a module variable with a setter rather than in a hook,
 * deliberately: these clients are plain modules called from effects and event
 * handlers, and threading a token through every call site would be a far
 * larger change for no benefit.
 */

let authToken: string | null = null;
let mediaToken: string | null = null;
let onUnauthorized: () => void = () => {};

/** Called by AuthProvider whenever the session changes. */
export function setAuthToken(token: string | null) {
  authToken = token;
}

/**
 * The short-lived token appended to `<img>` and `<video>` URLs, which cannot
 * carry an Authorization header. Kept in memory only — it expires in minutes,
 * so persisting it would buy nothing.
 */
export function setMediaToken(token: string | null) {
  mediaToken = token;
}

export function getMediaToken(): string | null {
  return mediaToken;
}

/** Called by AuthProvider so a 401 anywhere logs the user out once. */
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers = new Headers(extra);
  if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
  return headers;
}

export async function authFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders(init.headers));
  // Never set Content-Type for FormData: the browser has to add it itself,
  // because only it knows the multipart boundary it generated.
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("Can't reach the server. Is the backend running?", 0);
  }

  if (res.status === 401) {
    // One place decides what an expired session means, so a stale token can't
    // leave half the app showing errors and the other half showing nothing.
    onUnauthorized();
    throw new ApiError("Your session has expired. Please log in again.", 401);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`.
    const detail =
      typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => authFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    authFetch<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown) =>
    authFetch<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string, body?: unknown) =>
    authFetch<T>(path, {
      method: "DELETE",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  form: <T>(path: string, form: FormData, method = "POST") =>
    authFetch<T>(path, { method, body: form }),
};

/**
 * Append the media token to a URL a browser will fetch on its own.
 *
 * Used for private photos and DM attachments. A shared gallery match needs no
 * token at all — it is readable by anyone, which is what sharing means — so
 * callers pass `signed: false` there and keep the URL cacheable.
 */
export function withMediaToken(url: string): string {
  if (!mediaToken) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}t=${encodeURIComponent(mediaToken)}`;
}
