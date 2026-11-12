// Line icons (24x24, stroke = currentColor), built as SVG elements.

import { svg } from "../core/dom.js";

const CIRCLE = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z";

const PATHS = {
  folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  file: ["M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z", "M14 3v6h6"],
  copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  download: ["M12 4v11", "M7 10l5 5 5-5", "M5 20h14"],
  upload: ["M12 20V9", "M7 14l5-5 5 5", "M5 4h14"],
  refresh: ["M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7"],
  search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M21 21l-5-5"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  "caret-down": ["M6 9l6 6 6-6"],
  "caret-right": ["M9 6l6 6-6 6"],
  "caret-left": ["M15 6l-6 6 6 6"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  info: [CIRCLE, "M12 11v5", "M12 8h.01"],
  success: [CIRCLE, "M8 12l3 3 5-6"],
  error: [CIRCLE, "M15 9l-6 6", "M9 9l6 6"],
  warning: ["M12 3l10 18H2z", "M12 10v4", "M12 17h.01"],
  stopped: [CIRCLE, "M8 12h8"],
  sun: ["M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z", "M12 2v2", "M12 20v2", "M2 12h2", "M20 12h2", "M4.9 4.9l1.4 1.4", "M17.7 17.7l1.4 1.4", "M19.1 4.9l-1.4 1.4", "M6.3 17.7l-1.4 1.4"],
  moon: ["M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"],
  auto: [CIRCLE, "M12 3v18"],
  "sign-out": ["M9 21H4V3h5", "M16 17l5-5-5-5", "M21 12H9"],
  user: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M4 21a8 8 0 0 1 16 0"],
  bucket: ["M4 6c0-1.1 3.6-2 8-2s8 .9 8 2-3.6 2-8 2-8-.9-8-2z", "M4 6l2 13c.2 1 2.8 2 6 2s5.8-1 6-2l2-13"],
  plus: ["M12 5v14", "M5 12h14"],
  trash: ["M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 13h10l1-13", "M9 7V4h6v3"],
  lock: ["M6 11h12v10H6z", "M8 11V7a4 4 0 0 1 8 0v4"],
  history: ["M3 12a9 9 0 1 0 3-6.7", "M3 4v5h5", "M12 8v4l3 2"],
  globe: [CIRCLE, "M3 12h18", "M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"],
  check: ["M5 12l5 5 9-10"],
  logo: ["M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z", "M4 7v5c0 1.7 3.6 3 8 3s8-1.3 8-3V7", "M4 12v5c0 1.7 3.6 3 8 3s8-1.3 8-3v-5"],
};

export function icon(name, { size = 16, label, className } = {}) {
  const el = svg(
    "svg",
    {
      viewBox: "0 0 24 24",
      width: size,
      height: size,
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      class: ["icon", className].filter(Boolean).join(" "),
      "aria-hidden": label ? undefined : "true",
      role: label ? "img" : undefined,
      "aria-label": label,
      focusable: "false",
    },
    ...(PATHS[name] || PATHS.info).map((d) => svg("path", { d })),
  );
  return el;
}

export function spinner(size = 16) {
  return svg(
    "svg",
    { viewBox: "0 0 24 24", width: size, height: size, class: "spinner", "aria-hidden": "true", focusable: "false" },
    svg("circle", { cx: 12, cy: 12, r: 9, fill: "none", stroke: "currentColor", "stroke-width": 3, "stroke-opacity": 0.25 }),
    svg("path", { d: "M21 12a9 9 0 0 0-9-9", fill: "none", stroke: "currentColor", "stroke-width": 3, "stroke-linecap": "round" }),
  );
}
