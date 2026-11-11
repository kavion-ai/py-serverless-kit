// Form fields: a labelled wrapper plus inputs, selects, checkboxes and radio groups.

import { h, uid } from "../core/dom.js";
import { icon } from "./icons.js";

/**
 * field({label, description, constraint, optional, control, error}) - wraps a control with its label; returns the
 * wrapper with .setError(text).
 */
export function field({ label, description, constraint, optional, control, error, info }) {
  const id = control.id || uid("f");
  if (!control.id) control.id = id;
  const errEl = h("div", { class: "field__error", id: `${id}-error`, hidden: !error }, icon("error", { size: 14 }), h("span", {}, error || ""));
  const descId = description ? `${id}-desc` : undefined;
  if (descId) control.setAttribute("aria-describedby", descId);
  const wrap = h(
    "div",
    { class: "field" },
    label ? h("label", { class: "field__label", for: id }, label, optional ? h("i", { class: "field__optional" }, " - optional") : null, info ? h("span", { class: "field__info" }, info) : null) : null,
    description ? h("div", { class: "field__desc", id: descId }, description) : null,
    h("div", { class: "field__control" }, control),
    constraint ? h("div", { class: "field__constraint" }, constraint) : null,
    errEl,
  );
  wrap.setError = (text) => {
    errEl.hidden = !text;
    errEl.lastChild.textContent = text || "";
    control.classList.toggle("is-invalid", Boolean(text));
    if (text) control.setAttribute("aria-invalid", "true");
    else control.removeAttribute("aria-invalid");
  };
  return wrap;
}

/** A group of controls under one legend (radio groups, checkbox lists). */
export function fieldset({ legend, description }, ...children) {
  return h(
    "fieldset",
    { class: "fieldset" },
    legend ? h("legend", { class: "field__label" }, legend) : null,
    description ? h("div", { class: "field__desc" }, description) : null,
    children,
  );
}

export function input(attrs = {}) {
  return h("input", { class: "input", type: "text", autocomplete: "off", spellcheck: "false", ...attrs });
}

export function textarea(attrs = {}) {
  return h("textarea", { class: "input textarea", spellcheck: "false", ...attrs });
}

/** select({options: [{value, label}] | [string], value, onChange}) */
export function select({ options, value, onChange, id, disabled, ariaLabel }) {
  const el = h(
    "select",
    { class: "input select", id, disabled: Boolean(disabled), "aria-label": ariaLabel, onchange: onChange ? (e) => onChange(e.target.value) : undefined },
    options.map((o) => {
      const opt = typeof o === "string" ? { value: o, label: o } : o;
      return h("option", { value: opt.value, selected: opt.value === value, disabled: Boolean(opt.disabled) }, opt.label);
    }),
  );
  return el;
}

/** checkbox({label, description, checked, onChange, disabled}) - returns the label; .input is the checkbox. */
export function checkbox({ label, description, checked, onChange, disabled, className }) {
  const box = h("input", { type: "checkbox", checked: Boolean(checked), disabled: Boolean(disabled), onchange: onChange ? (e) => onChange(e.target.checked) : undefined });
  const el = h(
    "label",
    { class: ["check", className, disabled ? "is-disabled" : ""] },
    box,
    h("span", { class: "check__text" }, h("span", { class: "check__label" }, label), description ? h("span", { class: "check__desc" }, description) : null),
  );
  el.input = box;
  return el;
}

/**
 * radioGroup({name, items: [{value, label, description, disabled}], value, onChange, tiles}) - returns the group with
 * .value (getter) and .setValue(v).
 */
export function radioGroup({ name, items, value, onChange, tiles, ariaLabel }) {
  const groupName = name || uid("radio");
  const inputs = [];
  const group = h(
    "div",
    { class: ["radio-group", tiles ? "radio-group--tiles" : ""], role: "radiogroup", "aria-label": ariaLabel },
    items.map((item) => {
      const r = h("input", {
        type: "radio",
        name: groupName,
        value: item.value,
        checked: item.value === value,
        disabled: Boolean(item.disabled),
        onchange: () => {
          group.querySelectorAll(".radio").forEach((el) => el.classList.toggle("is-checked", el.contains(r) && r.checked));
          if (onChange) onChange(item.value);
        },
      });
      inputs.push(r);
      return h(
        "label",
        { class: ["radio", item.value === value ? "is-checked" : "", item.disabled ? "is-disabled" : ""] },
        r,
        h("span", { class: "check__text" }, h("span", { class: "check__label" }, item.label), item.description ? h("span", { class: "check__desc" }, item.description) : null),
      );
    }),
  );
  Object.defineProperty(group, "value", {
    get: () => {
      const on = inputs.find((r) => r.checked);
      return on ? on.value : "";
    },
  });
  group.setValue = (v) => {
    inputs.forEach((r) => {
      r.checked = r.value === v;
      r.closest(".radio").classList.toggle("is-checked", r.checked);
    });
  };
  return group;
}
