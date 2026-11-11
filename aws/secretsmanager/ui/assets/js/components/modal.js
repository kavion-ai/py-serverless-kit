// Modal dialogs on <dialog>: Esc and the close button dismiss, focus moves into the dialog and back after.
//   const m = modal({ title, body: [nodes], footer: [buttons], wide })
//   m.close()
// confirm({ title, message, confirmLabel, danger, onConfirm }) is a ready-made yes/no dialog.

import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { button } from "./button.js";

export function modal({ title, body = [], footer = [], wide = false, onClose } = {}) {
  const opener = document.activeElement;
  const titleId = `m-${Math.random().toString(36).slice(2)}`;
  const dialog = h("dialog", { class: ["modal", wide && "wide"], "aria-labelledby": titleId },
    h("div", { class: "m-header" },
      h("h2", { id: titleId }, title),
      h("button", { type: "button", class: "btn icon", "aria-label": "Close", onclick: () => dialog.close() }, icon("close"))),
    h("div", { class: "m-body" }, body),
    footer.length ? h("div", { class: "m-footer" }, footer) : null);
  dialog.addEventListener("close", () => {
    dialog.remove();
    if (onClose) onClose();
    if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
  });
  // A click on the backdrop (the dialog element itself, outside its content box) closes it.
  dialog.addEventListener("mousedown", (event) => {
    if (event.target !== dialog) return;
    const r = dialog.getBoundingClientRect();
    const inside = event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
    if (!inside) dialog.close();
  });
  document.body.append(dialog);
  dialog.showModal();
  const first = dialog.querySelector(".m-body input, .m-body textarea, .m-body select, .m-footer .btn.primary");
  if (first) first.focus();
  return { dialog, close: () => dialog.close() };
}

/** Yes/no dialog. onConfirm may be async; an error it throws is shown inside the dialog. */
export function confirm({ title, message, confirmLabel = "Confirm", danger = false, onConfirm }) {
  const error = h("div", { class: "f-error", role: "alert" });
  let m;
  const ok = button(confirmLabel, {
    variant: "primary",
    danger,
    onClick: async () => {
      error.textContent = "";
      try {
        await onConfirm();
        m.close();
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });
  m = modal({
    title,
    body: [typeof message === "string" ? h("p", { style: "margin:0" }, message) : message, h("div", { class: "field" }, error)],
    footer: [button("Cancel", { variant: "link", onClick: () => m.close() }), ok],
  });
  return m;
}
