// Inline SVG icons (stroke icons on a 16x16 grid), built with createElementNS: no markup parsing.

const NS = "http://www.w3.org/2000/svg";

const PATHS = {
  key: ["M10.5 1.5a4 4 0 0 0-3.8 5.2L1.5 11.9V14.5h2.6v-1.5h1.5v-1.5h1.5l1.2-1.2A4 4 0 1 0 10.5 1.5z", "M11.5 4.5h.01"],
  search: ["M7 12.5a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11z", "M11 11l3.5 3.5"],
  refresh: ["M14 8a6 6 0 1 1-1.8-4.3", "M14 2v3.5h-3.5"],
  copy: ["M5.5 5.5h8v8h-8z", "M10.5 5.5v-3h-8v8h3"],
  check: ["M2.5 8.5l3.5 3.5 7.5-8"],
  close: ["M3.5 3.5l9 9", "M12.5 3.5l-9 9"],
  menu: ["M2 4h12", "M2 8h12", "M2 12h12"],
  caretDown: ["M4 6l4 4 4-4"],
  caretLeft: ["M10 3.5L5.5 8l4.5 4.5"],
  caretRight: ["M6 3.5L10.5 8 6 12.5"],
  info: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M8 7.5v4", "M8 4.8v.01"],
  success: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M5 8.3l2 2 4-4.3"],
  error: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M5.7 5.7l4.6 4.6", "M10.3 5.7l-4.6 4.6"],
  warning: ["M8 1.8L15 14H1z", "M8 6.5v3.5", "M8 12v.01"],
  stopped: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M4 8h8"],
  pending: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M8 4.5V8l2.5 1.5"],
  eye: ["M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z", "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"],
  eyeOff: ["M2 2l12 12", "M6.6 3.2A6.7 6.7 0 0 1 8 3c4.5 0 7 5 7 5a12 12 0 0 1-1.9 2.5", "M4.2 4.4A11.7 11.7 0 0 0 1 8s2.5 5 7 5a6.6 6.6 0 0 0 3.4-.9"],
  plus: ["M8 2.5v11", "M2.5 8h11"],
  sun: ["M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M8 1v1.5", "M8 13.5V15", "M1 8h1.5", "M13.5 8H15", "M3 3l1 1", "M12 12l1 1", "M13 3l-1 1", "M4 12l-1 1"],
  moon: ["M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z"],
  auto: ["M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M8 1.5v13"],
  signOut: ["M6 14.5H2.5v-13H6", "M10.5 11.5L14 8l-3.5-3.5", "M14 8H6"],
  external: ["M9.5 2.5h4v4", "M13.5 2.5L7 9", "M11.5 9.5v4h-9v-9h4"],
  lock: ["M3.5 7.5h9v7h-9z", "M5.5 7.5V5a2.5 2.5 0 0 1 5 0v2.5"],
};

/** An <svg> icon; `label` makes it meaningful to screen readers, otherwise it is hidden from them. */
export function icon(name, { label, size } = {}) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.6");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("focusable", "false");
  if (size) {
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
  }
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
  }
  for (const d of PATHS[name] || PATHS.info) {
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", d);
    svg.append(path);
  }
  return svg;
}
