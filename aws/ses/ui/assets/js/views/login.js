// The sign-in card: an access key ID and its secret access key, or the console password (SES_UI_PASSWORD).

import { login } from "../core/api.js";
import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { session } from "../core/state.js";
import { alert } from "../components/alert.js";
import { button } from "../components/button.js";
import { formField, input } from "../components/form-field.js";

export function renderLogin(root, { message, onSignedIn } = {}) {
  const pw = session.passwordLogin;
  const user = formField({
    label: pw ? "Name" : "Access key ID",
    optional: pw,
    control: input({ name: "user", autocomplete: "username", required: !pw }),
  });
  const pass = formField({
    label: pw ? "Console password" : "Secret access key",
    description: pw ? undefined : "The secret access key is the console password.",
    control: input({ name: "password", type: "password", autocomplete: "current-password", required: true }),
  });
  const note = h("div");
  if (message) note.append(alert("info", message));

  const submit = button("Sign in", { variant: "primary", type: "submit" });
  submit.style.width = "100%";
  const form = h("form", {
    class: "login-card",
    novalidate: true,
    onsubmit: async (e) => {
      e.preventDefault();
      user.setError("");
      pass.setError("");
      note.replaceChildren();
      if (!pw && !user.control.value.trim()) {
        user.setError("Enter the access key ID.");
        user.control.focus();
        return;
      }
      if (!pass.control.value) {
        pass.setError(pw ? "Enter the password." : "Enter the secret access key.");
        pass.control.focus();
        return;
      }
      submit.disabled = true;
      try {
        await login(user.control.value.trim(), pass.control.value);
        onSignedIn();
      } catch (err) {
        const text = err.status === 429 ? "Too many failed sign-ins from this address. Wait 5 minutes." : err.message;
        note.replaceChildren(alert("error", "Sign-in failed", text));
        pass.control.value = "";
        pass.control.focus();
      } finally {
        submit.disabled = false;
      }
    },
  },
  h("div", { class: "brand" }, h("span", { class: "logo" }, icon("mail", { size: 18 })), h("span", {}, "SES", h("span", { class: "brand-sub" }, "Simple Email Service"))),
  h("div", { class: "muted" }, pw
    ? "Sign in with the console password."
    : "Sign in with an access key ID and its secret access key, the same keys your SDK signs with."),
  note,
  user.el,
  pass.el,
  submit,
  h("div", { class: "faint", style: "font-size:12px" }, "The session lasts 12 hours. Ten failed sign-ins lock this address out for 5 minutes."));

  root.replaceChildren(h("div", { class: "center-page" }, form));
  (pw ? pass.control : user.control).focus();
}
