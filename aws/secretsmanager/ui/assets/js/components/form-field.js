// A labelled form control: formField({ label, description, constraint, optional, control }) -> { el, control, setError }
// input(attrs), select(options, attrs), textarea(attrs) and checkbox(label, attrs) create styled controls.

import { h, uid } from "../core/dom.js";
import { icon } from "../core/icons.js";

export function formField({ label, description, constraint, optional = false, control }) {
  const id = control.id || uid("f");
  control.id = id;
  const error = h("div", { class: "f-error", id: `${id}-err`, role: "alert" });
  const descId = description ? `${id}-desc` : null;
  if (descId) control.setAttribute("aria-describedby", descId);
  const el = h("div", { class: "field" },
    h("label", { for: id }, label, optional ? h("span", { class: "opt" }, " - optional") : null),
    description ? h("div", { class: "f-desc", id: descId }, description) : null,
    control,
    constraint ? h("div", { class: "f-constraint" }, constraint) : null,
    error);
  return {
    el,
    control,
    setError(message) {
      error.replaceChildren(...(message ? [icon("error"), message] : []));
      control.classList.toggle("invalid", Boolean(message));
      if (message) control.setAttribute("aria-invalid", "true");
      else control.removeAttribute("aria-invalid");
    },
  };
}

export function input(attrs = {}) {
  return h("input", { type: "text", autocomplete: "off", spellcheck: "false", ...attrs });
}

export function textarea(attrs = {}) {
  return h("textarea", { spellcheck: "false", ...attrs });
}

export function select(options, attrs = {}) {
  return h("select", attrs, options.map((o) => h("option", { value: o.value, selected: Boolean(o.selected) }, o.label)));
}

/** A checkbox with its label: const { el, box } = checkbox("Show deleted", { checked: true }) */
export function checkbox(label, attrs = {}) {
  const box = h("input", { type: "checkbox", ...attrs });
  return { el: h("label", { class: "check" }, box, label), box };
}
