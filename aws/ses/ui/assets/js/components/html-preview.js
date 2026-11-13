// A sandboxed preview of an HTML document (an email's HTML body, a rendered template):
//   htmlPreview(html, { title: "HTML body", height: 480 }) -> <iframe>
// The HTML goes into a blob: URL shown in <iframe sandbox="">: no scripts, no same origin, no forms, no top
// navigation, so it can't read the console's cookies or call its API. The URL is revoked when the page changes
// (and when the frame is replaced by a new preview).

import { h } from "../core/dom.js";
import { onLeave } from "../core/router.js";

let live = [];
let hooked = false;

function revokeAll() {
  for (const url of live) URL.revokeObjectURL(url);
  live = [];
  hooked = false;
}

export function htmlPreview(html, { title = "HTML preview", height = 480 } = {}) {
  const url = URL.createObjectURL(new Blob([String(html || "")], { type: "text/html" }));
  live.push(url);
  if (!hooked) {
    hooked = true;
    onLeave(revokeAll);
  }
  const frame = h("iframe", {
    class: "html-preview", sandbox: "", referrerpolicy: "no-referrer", title, src: url,
    style: `height:${Number(height) || 480}px`,
  });
  return frame;
}

/** Revoke the URL of a preview that is being replaced on the same page. */
export function disposePreview(frame) {
  if (!frame || !frame.src) return;
  const url = frame.src;
  if (live.includes(url)) {
    URL.revokeObjectURL(url);
    live = live.filter((u) => u !== url);
  }
}
