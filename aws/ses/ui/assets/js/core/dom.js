// h(): build DOM elements. Text is always set as text (never parsed as HTML), so names and message text are safe.
//   h("button", { class: "btn", onclick: fn, disabled: true }, "Save")
// Attributes: on<event> adds a listener, class/className, style (string or object), dataset (object),
// value/checked/disabled/hidden/selected are set as properties; null/undefined/false are skipped.

const PROPS = new Set(["value", "checked", "disabled", "hidden", "selected", "indeterminate", "open"]);

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

export function setAttrs(el, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "class" || key === "className") {
      if (value) el.className = Array.isArray(value) ? value.filter(Boolean).join(" ") : value;
    } else if (key === "style" && typeof value === "object") {
      Object.assign(el.style, value);
    } else if (key === "dataset") {
      Object.assign(el.dataset, value);
    } else if (PROPS.has(key)) {
      el[key] = value;
    } else if (value === false) {
      continue;
    } else {
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
  return el;
}

export function append(el, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === true) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

/** Replace every child of `el`. */
export function mount(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

/** A fragment from a list (handy when a component returns several nodes). */
export function frag(...children) {
  return append(document.createDocumentFragment(), children);
}

/** Calls fn after `ms` without another call (filter inputs). */
export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

let ids = 0;
/** A unique id for label/aria wiring. */
export function uid(prefix = "id") {
  ids += 1;
  return `${prefix}-${ids}`;
}
