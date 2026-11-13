// Hash routes:
//   #/account                              the account dashboard (default)
//   #/identities, #/identities/create      verified identities
//   #/identities/<identity>?tab=dns        one identity (encodeURIComponent'ed)
//   #/send?from=<identity>                 send a test email
//   #/messages?status=DELAYED              the sending log
//   #/messages/<message id>?tab=html       one message
//   #/templates, #/templates/create, #/templates/<name>, #/templates/<name>/edit
//   #/configuration-sets, #/configuration-sets/create, #/configuration-sets/<name>
//   #/suppression, #/smtp
// Message bodies and SMTP passwords never go into the URL.

import { emit } from "./state.js";

const routes = [];
const leaving = [];
let generation = 0;

/** Run `fn` when the user leaves the current page (stop timers, revoke blob: URLs). */
export function onLeave(fn) {
  leaving.push(fn);
}

/** A number that changes on every navigation: async views compare it before drawing a late answer. */
export function pageId() {
  return generation;
}

/** Register `pattern` (a RegExp on the path) -> handler(match, query). First match wins. */
export function route(pattern, handler) {
  routes.push({ pattern, handler });
}

export function current() {
  const raw = window.location.hash.replace(/^#/, "") || "/account";
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

const enc = encodeURIComponent;
const withTab = (path, tab) => `${path}${tab ? `?tab=${enc(tab)}` : ""}`;

export const paths = {
  identity: (name, tab) => withTab(`/identities/${enc(name)}`, tab),
  message: (id, tab) => withTab(`/messages/${enc(id)}`, tab),
  template: (name) => `/templates/${enc(name)}`,
  editTemplate: (name) => `/templates/${enc(name)}/edit`,
  configSet: (name) => `/configuration-sets/${enc(name)}`,
  send: (from) => `/send${from ? `?from=${enc(from)}` : ""}`,
};

export function resolve() {
  const { path, query } = current();
  for (const { pattern, handler } of routes) {
    const match = pattern.exec(path);
    if (match) {
      generation += 1;
      for (const fn of leaving.splice(0)) {
        try {
          fn();
        } catch (err) {
          console.error(err); // eslint-disable-line no-console
        }
      }
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
