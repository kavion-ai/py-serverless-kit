// The console API: POST /ui/api/<Operation> (JSON in, JSON out), PUT /ui/upload, GET /ui/download, the session
// endpoints, and presigned URLs for Open / Download. The session is an HttpOnly cookie; the X-S3-CSRF header proves
// the request comes from this page.

import { state } from "./state.js";
import { baseName } from "./format.js";

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message || code || "Request failed");
    this.code = code || "Error";
    this.status = status || 0;
  }
}

let unauthorized = () => {};

/** Called when the server says the session ended (401). */
export function onUnauthorized(fn) {
  unauthorized = fn;
}

export function errorText(e) {
  if (!e) return "Unknown error";
  if (e instanceof ApiError) return e.code && e.code !== "Error" ? `${e.message} (${e.code})` : e.message;
  return e.message || String(e);
}

export async function api(op, body) {
  let res;
  try {
    res = await fetch(`/ui/api/${op}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-S3-CSRF": state.session.csrf },
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new ApiError("NetworkError", "The server could not be reached. Check your connection and try again.", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    state.session.authenticated = false;
    state.session.csrf = "";
    unauthorized();
    throw new ApiError("SessionEnded", "Your session ended. Sign in again.", 401);
  }
  if (!res.ok) throw new ApiError(data.code || String(res.status), data.message || res.statusText, res.status);
  return data;
}

export async function getSession() {
  const res = await fetch("/ui/session", { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) throw new ApiError(String(res.status), "The console session could not be read.", res.status);
  const s = await res.json();
  Object.assign(state.session, {
    authenticated: Boolean(s.authenticated),
    auth: s.auth !== false,
    user: s.user || "",
    csrf: s.csrf || "",
    passwordLogin: Boolean(s.password_login),
    region: s.region || "us-east-1",
    version: s.version || "",
  });
  return state.session;
}

export async function login(user, password) {
  const res = await fetch("/ui/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(data.code || String(res.status), data.message || "Sign-in failed.", res.status);
  Object.assign(state.session, { authenticated: true, csrf: data.csrf || "", user: data.user || user });
  return state.session;
}

export async function logout() {
  await fetch("/ui/logout", { method: "POST", credentials: "same-origin" }).catch(() => undefined);
  Object.assign(state.session, { authenticated: false, csrf: "", user: "" });
}

function query(params) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  return q.toString();
}

/**
 * Upload one file with progress. Returns {promise, abort}; the promise resolves with {key, etag, versionId}.
 */
export function uploadFile({ bucket, key, file, storageClass, onProgress }) {
  const xhr = new XMLHttpRequest();
  const promise = new Promise((resolve, reject) => {
    xhr.open("PUT", "/ui/upload?" + query({ bucket, key, class: storageClass && storageClass !== "STANDARD" ? storageClass : "" }));
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-S3-CSRF", state.session.csrf);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText || "{}");
      } catch {
        data = {};
      }
      if (xhr.status === 200) resolve(data);
      else {
        if (xhr.status === 401) unauthorized();
        reject(new ApiError(data.code || String(xhr.status), data.message || xhr.statusText || "Upload failed", xhr.status));
      }
    };
    xhr.onerror = () => reject(new ApiError("NetworkError", "Network error", 0));
    xhr.onabort = () => reject(new ApiError("Aborted", "Canceled", 0));
    xhr.send(file);
  });
  return { promise, abort: () => xhr.abort() };
}

/** The cookie-authenticated download URL; used only for in-page text previews. */
export function downloadUrl(bucket, key, versionId) {
  return "/ui/download?" + query({ bucket, key, versionId });
}

/** A presigned URL for this object (GET by default), signed for this page's host. */
export async function presign({ bucket, key, versionId, method = "GET", expires = 300, disposition, filename }) {
  const data = await api("Presign", {
    bucket,
    key,
    versionId: versionId || "",
    method,
    expires,
    host: location.host,
    scheme: location.protocol.replace(":", ""),
    disposition,
    filename,
  });
  return data;
}

/** Open: a presigned inline URL in a new tab, like the AWS console. */
export async function openObject(bucket, key, versionId) {
  const { url } = await presign({ bucket, key, versionId, expires: 300, disposition: "inline" });
  window.open(url, "_blank", "noopener");
}

/** Download: a presigned attachment URL, followed by a hidden link. */
export async function downloadObject(bucket, key, versionId) {
  const { url } = await presign({ bucket, key, versionId, expires: 300, disposition: "attachment", filename: baseName(key) });
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.append(a);
  a.click();
  a.remove();
}
