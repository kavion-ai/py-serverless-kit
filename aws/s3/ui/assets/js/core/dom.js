// Tiny DOM helpers. Text is always added as text nodes: never use innerHTML with bucket or key names.

const SVG_NS = "http://www.w3.org/2000/svg";
const PROPS = new Set(["value", "checked", "disabled", "selected", "indeterminate", "readOnly", "multiple", "open"]);

function apply(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") {
      const cls = Array.isArray(v) ? v.filter(Boolean).join(" ") : v;
      if (cls) el.setAttribute("class", cls);
    } else if (k === "style" && typeof v === "object") {
      for (const [p, val] of Object.entries(v)) if (val !== undefined && val !== null) el.style.setProperty(p, String(val));
    } else if (k === "dataset") {
      for (const [p, val] of Object.entries(v)) el.dataset[p] = val;
    } else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (PROPS.has(k)) {
      el[k] = v;
    } else {
      el.setAttribute(k, v === true ? "" : String(v));
    }
  }
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false || c === true) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** h("button", {class: "btn", onclick: fn}, "Label", child, [more]) */
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  apply(el, attrs);
  append(el, children);
  return el;
}

/** An SVG element (icons). */
export function svg(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null && v !== false) el.setAttribute(k, String(v));
  append(el, children);
  return el;
}

export function mount(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

let counter = 0;
export function uid(prefix = "id") {
  counter += 1;
  return `${prefix}-${counter}`;
}

/** A fragment of several nodes. */
export function frag(...children) {
  const f = document.createDocumentFragment();
  append(f, children);
  return f;
}

/** Show or hide an element. */
export function show(el, visible) {
  el.hidden = !visible;
  return el;
}
