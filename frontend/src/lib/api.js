const BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Fired on any 401 so the app can show the login prompt. */
export const AUTH_REQUIRED_EVENT = "npl-adda:auth-required";

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function readCookie(name) {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function messageFrom(data) {
  if (!data || typeof data !== "object") return null;
  if (typeof data.detail === "string") return data.detail;
  const first = Object.values(data)[0];
  return Array.isArray(first) ? String(first[0]) : typeof first === "string" ? first : null;
}

let csrfPromise = null;

/** Make sure the csrftoken cookie exists (GET /accounts/session sets it). */
async function ensureCsrf() {
  if (readCookie("csrftoken")) return readCookie("csrftoken");
  csrfPromise ??= fetch(`${BASE}/accounts/session`, { credentials: "include" }).finally(() => {
    csrfPromise = null;
  });
  await csrfPromise;
  return readCookie("csrftoken");
}

/**
 * Call the API. Auth is the HttpOnly session cookie (never a token in JS); writes carry
 * Django's CSRF token. Errors are thrown as ApiError, never swallowed into fake success.
 */
export async function api(path, { method = "GET", body, signal, silent401 = false, blob = false } = {}) {
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  // Image calls still accept JSON so validation/throttle errors come back readable.
  const headers = { Accept: blob ? "image/jpeg, application/json;q=0.9" : "application/json" };
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const token = await ensureCsrf();
    if (token) headers["X-CSRFToken"] = token;
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    signal,
    credentials: "include",
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  if (blob && res.ok) return res.blob();
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && !silent401) window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT));
    throw new ApiError(messageFrom(data) || `Request failed (${res.status})`, res.status, data);
  }
  return data;
}

export const results = (page) => (Array.isArray(page) ? page : page?.results ?? []);
