// The console's calls: /ui/session, /ui/login, /ui/logout and /ui/api/<Operation> (the Secrets Manager JSON API).
// The session is an HttpOnly cookie; X-SM-CSRF proves the request comes from this page.

import { emit, session } from "./state.js";

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }

  /** "Code: message", the way errors are shown in flashbars and forms. */
  get text() {
    return this.code ? `${this.code}: ${this.message}` : this.message;
  }
}

async function request(path, { method = "POST", body, csrf = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrf) headers["X-SM-CSRF"] = session.csrf;
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    throw new ApiError("NetworkError", `The server did not answer (${err.message}).`, 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.__type || `HTTP ${res.status}`, data.message || res.statusText || "Request failed", res.status);
  }
  return data;
}

/** Call a Secrets Manager operation. A 401 ends the session and shows the sign-in page. */
export async function call(operation, params = {}) {
  try {
    return await request(`/ui/api/${encodeURIComponent(operation)}`, { body: params, csrf: true });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      session.authenticated = false;
      session.csrf = "";
      emit("signed-out", "Your session ended. Sign in again.");
    }
    throw err;
  }
}

export async function loadSession() {
  const s = await request("/ui/session", { method: "GET" });
  Object.assign(session, {
    authenticated: Boolean(s.authenticated),
    auth: s.auth !== false,
    user: s.user || "",
    csrf: s.csrf || "",
    passwordLogin: Boolean(s.password_login),
  });
  return session;
}

export async function login(user, password) {
  const out = await request("/ui/login", { body: { user, password } });
  Object.assign(session, { authenticated: true, user: out.user || user, csrf: out.csrf || "" });
  return session;
}

export async function logout() {
  try {
    await request("/ui/logout", { body: {} });
  } finally {
    Object.assign(session, { authenticated: false, csrf: "" });
  }
}
