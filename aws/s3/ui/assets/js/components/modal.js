// Modal dialogs on <dialog>: Escape and Cancel close them; errors show inside the dialog.

import { h } from "../core/dom.js";
import { errorText } from "../core/api.js";
import { alert } from "./alert.js";
import { icon, spinner } from "./icons.js";

/**
 * modal({title, body, actions: [{label, variant, onClick}], cancelLabel, size, onClose})
 * An action's onClick may be async; returning false (or throwing) keeps the dialog open. Thrown errors are shown in it.
 * Returns {el, close, setError, buttons}.
 */
export function modal({ title, body, actions = [], cancelLabel = "Cancel", size = "medium", onClose }) {
  const errorBox = h("div", { class: "modal__error" });
  const dlg = h("dialog", { class: `modal modal--${size}`, "aria-label": title });
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    if (dlg.open) dlg.close();
    dlg.remove();
    if (onClose) onClose();
  };
  const setError = (e) => {
    errorBox.replaceChildren(e ? alert({ type: "error" }, typeof e === "string" ? e : errorText(e)) : "");
  };
  const buttons = actions.map((a) => {
    const btn = h("button", { type: "button", class: ["btn", `btn--${a.variant || "primary"}`], disabled: Boolean(a.disabled) }, h("span", { class: "btn__label" }, a.label));
    btn.addEventListener("click", async () => {
      setError(null);
      btn.disabled = true;
      const spin = spinner(14);
      btn.prepend(spin);
      let keep = false;
      try {
        keep = (await a.onClick()) === false;
      } catch (e) {
        keep = true;
        setError(e);
      } finally {
        spin.remove();
        btn.disabled = false;
      }
      if (!keep) close();
    });
    return btn;
  });
  dlg.append(
    h(
      "div",
      { class: "modal__header" },
      h("h2", { class: "modal__title" }, title),
      h("button", { type: "button", class: "modal__close", "aria-label": "Close", onclick: close }, icon("close", { size: 16 })),
    ),
    h("div", { class: "modal__body" }, body, errorBox),
    h(
      "div",
      { class: "modal__footer" },
      cancelLabel ? h("button", { type: "button", class: "btn btn--link", onclick: close }, cancelLabel) : null,
      buttons,
    ),
  );
  dlg.addEventListener("cancel", (e) => {
    e.preventDefault();
    close();
  });
  document.body.append(dlg);
  dlg.showModal();
  const first = dlg.querySelector(".modal__body input:not([type=hidden]):not([disabled]), .modal__body select, .modal__body textarea");
  if (first) first.focus();
  return { el: dlg, close, setError, buttons };
}

/**
 * confirmModal({title, message, confirmLabel, variant, typed}) -> Promise<boolean>. With `typed` ("delete",
 * "permanently delete", "confirm"), the user must type that text first.
 */
export function confirmModal({ title, message, confirmLabel = "Confirm", variant = "primary", typed }) {
  return new Promise((resolve) => {
    let answered = false;
    const input = typed ? h("input", { class: "input", placeholder: typed, autocomplete: "off", "aria-label": `Type ${typed} to confirm` }) : null;
    const m = modal({
      title,
      body: [
        h("div", { class: "modal__message" }, message),
        typed ? h("div", { class: "field" }, h("label", { class: "field__label" }, "To confirm, type ", h("i", {}, typed), " in the field."), input) : null,
      ],
      actions: [
        {
          label: confirmLabel,
          variant,
          disabled: Boolean(typed),
          onClick: () => {
            answered = true;
            resolve(true);
          },
        },
      ],
      onClose: () => {
        if (!answered) resolve(false);
      },
    });
    if (input) {
      input.addEventListener("input", () => {
        m.buttons[0].disabled = input.value.trim() !== typed;
      });
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && input.value.trim() === typed) m.buttons[0].click();
      });
    }
  });
}
