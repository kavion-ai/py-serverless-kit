// Session state and a tiny event bus. Message bodies and SMTP passwords are never stored here.

export const session = {
  authenticated: false,
  auth: true,          // false when the server runs with SES_AUTH=off
  user: "",
  csrf: "",
  passwordLogin: false,
};

const listeners = new Map();

/** Subscribe to an event; returns the unsubscribe function. */
export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}

export function emit(event, detail) {
  for (const fn of [...(listeners.get(event) || [])]) {
    try {
      fn(detail);
    } catch (err) {
      console.error(err); // eslint-disable-line no-console
    }
  }
}

/** Per-viewer conveniences (theme, side navigation). Storage may be blocked: never let that break the page. */
export const prefs = {
  get(key, fallback) {
    try {
      const v = window.localStorage.getItem(`ses-console:${key}`);
      return v === null ? fallback : v;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      window.localStorage.setItem(`ses-console:${key}`, value);
    } catch {
      /* storage blocked: the setting lasts for this page only */
    }
  },
};
