// Hash router: "#/buckets/<bucket>?tab=objects&prefix=a/". Reload and Back work because the page state is in the URL.

const routes = [];
const listeners = [];
let token = 0;
let guard = () => true;
let notFound = () => {};

/** route("/buckets/:bucket/object", handler) - handler({params, query, path, alive}) */
export function route(pattern, handler) {
  const names = [];
  const source = pattern
    .split("/")
    .map((part) => {
      if (part.startsWith(":")) {
        names.push(part.slice(1));
        return "([^/]+)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  routes.push({ re: new RegExp(`^${source}/?$`), names, handler });
}

function encodePath(path) {
  return path;
}

/** "#/path?query" from a path whose dynamic segments are already encoded (see seg()). */
export function href(path, query) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const qs = q.toString();
  return "#" + encodePath(path) + (qs ? "?" + qs : "");
}

/** Encode one path segment (a bucket name). */
export function seg(value) {
  return encodeURIComponent(value);
}

export function navigate(path, query, options = {}) {
  const target = href(path, query);
  if (options.replace) {
    history.replaceState(null, "", target);
    dispatch();
  } else if (location.hash === target) {
    dispatch();
  } else {
    location.hash = target;
  }
}

export function current() {
  const raw = location.hash.replace(/^#/, "") || "/buckets";
  const i = raw.indexOf("?");
  const path = i < 0 ? raw : raw.slice(0, i);
  const query = Object.fromEntries(new URLSearchParams(i < 0 ? "" : raw.slice(i + 1)));
  return { path, query };
}

/** Re-run the current route (after a change that needs a fresh page). */
export function reload() {
  dispatch();
}

export function beforeEach(fn) {
  guard = fn;
}

export function onNavigate(fn) {
  listeners.push(fn);
}

export function setNotFound(fn) {
  notFound = fn;
}

function dispatch() {
  token += 1;
  const mine = token;
  const { path, query } = current();
  for (const fn of listeners) fn({ path, query });
  if (!guard({ path, query })) return;
  for (const r of routes) {
    const m = r.re.exec(path);
    if (!m) continue;
    const params = {};
    r.names.forEach((name, i) => {
      try {
        params[name] = decodeURIComponent(m[i + 1]);
      } catch {
        params[name] = m[i + 1];
      }
    });
    const ctx = { params, query, path, alive: () => mine === token };
    Promise.resolve(r.handler(ctx)).catch((e) => console.error(e)); // eslint-disable-line no-console
    return;
  }
  notFound({ path, query });
}

export function start() {
  window.addEventListener("hashchange", dispatch);
  if (!location.hash) history.replaceState(null, "", "#/buckets");
  dispatch();
}
