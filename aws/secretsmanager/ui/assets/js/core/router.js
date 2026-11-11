// Hash routes:
//   #/secrets                       the list
//   #/store-secret                  store a new secret
//   #/secrets/<name>?tab=versions   one secret (name is encodeURIComponent'ed; it may contain "/")
//   #/quick-start                   connection snippets
// Secret values never go into the URL.

import { emit } from "./state.js";

const routes = [];

/** Register `pattern` (a RegExp on the path) -> handler(match, query). First match wins. */
export function route(pattern, handler) {
  routes.push({ pattern, handler });
}

export function current() {
  const raw = window.location.hash.replace(/^#/, "") || "/secrets";
  const at = raw.indexOf("?");
  const path = at < 0 ? raw : raw.slice(0, at);
  const query = new URLSearchParams(at < 0 ? "" : raw.slice(at + 1));
  return { path, query };
}

export function navigate(path, { replace = false } = {}) {
  const hash = `#${path}`;
  if (window.location.hash === hash) {
    resolve();
  } else if (replace) {
    window.history.replaceState(null, "", hash);
    resolve();
  } else {
    window.location.hash = hash;
  }
}

/** Change the query (e.g. the selected tab) without adding a history entry or re-rendering. */
export function setQuery(params) {
  const { path, query } = current();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") query.delete(k);
    else query.set(k, v);
  }
  const qs = query.toString();
  window.history.replaceState(null, "", `#${path}${qs ? `?${qs}` : ""}`);
}

export function secretPath(name, tab) {
  return `/secrets/${encodeURIComponent(name)}${tab ? `?tab=${tab}` : ""}`;
}

export function resolve() {
  const { path, query } = current();
  for (const { pattern, handler } of routes) {
    const match = pattern.exec(path);
    if (match) {
      emit("route", { path, query });
      handler(match, query);
      return;
    }
  }
}

export function start() {
  window.addEventListener("hashchange", resolve);
  resolve();
}
