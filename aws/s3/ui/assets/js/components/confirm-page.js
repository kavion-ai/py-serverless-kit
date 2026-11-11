// The body of a "type to confirm" page (Empty bucket, Delete bucket, Delete objects).
//
// confirmPage({heading, intro, expected, placeholder, confirmLabel, variant, disabled, cancelHref, onConfirm})
// onConfirm() may throw: the error is shown above the buttons.

import { h } from "../core/dom.js";
import { errorText } from "../core/api.js";
import { button, busy } from "./button.js";
import { container, formActions } from "./container.js";
import { errorSlot } from "./alert.js";

export function confirmPage({ heading, intro, expected, placeholder, confirmLabel, variant = "primary", disabled, cancelHref, onConfirm }) {
  const input = h("input", { class: "input", placeholder: placeholder || expected, autocomplete: "off", disabled: Boolean(disabled), "aria-label": `Type ${expected} to confirm` });
  const errors = errorSlot();
  const confirm = button({ label: confirmLabel, variant, disabled: true });
  const update = () => {
    confirm.disabled = Boolean(disabled) || input.value.trim() !== expected;
  };
  input.addEventListener("input", update);
  const run = () =>
    busy(confirm, async () => {
      errors.set(null);
      try {
        await onConfirm();
      } catch (e) {
        errors.set(errorText(e));
      }
    }).then(update);
  confirm.addEventListener("click", run);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !confirm.disabled) run();
  });
  return h(
    "div",
    { class: "confirm-page" },
    container(
      { title: heading },
      h("p", { class: "confirm-page__intro" }, intro || ["To confirm, type ", h("i", { class: "confirm-page__expected" }, expected), " in the text input field."]),
      input,
    ),
    errors,
    formActions(button({ label: "Cancel", variant: "link", href: cancelHref }), confirm),
  );
}
