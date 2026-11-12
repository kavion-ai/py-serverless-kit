// The sign-in page (access key ID + secret access key, or the console password).

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { login, errorText } from "../core/api.js";
import { field, input } from "../components/field.js";
import { alert } from "../components/alert.js";
import { icon, spinner } from "../components/icons.js";

export function renderLogin(app, message, onSignedIn) {
  const pw = state.session.passwordLogin;
  const notice = h("div", { class: "login__notice" }, message ? alert({ type: message.startsWith("Signed out") ? "info" : "warning" }, message) : null);
  const user = input({ name: "user", autocomplete: "username", required: !pw });
  const pass = input({ name: "password", type: "password", autocomplete: "current-password", required: true });
  const submit = h("button", { type: "submit", class: "btn btn--primary btn--block" }, h("span", { class: "btn__label" }, "Sign in"));
  const form = h(
    "form",
    {
      class: "login__form",
      onsubmit: async (e) => {
        e.preventDefault();
        mount(notice);
        submit.disabled = true;
        const spin = spinner(14);
        submit.prepend(spin);
        try {
          await login(user.value.trim(), pass.value);
          onSignedIn();
        } catch (err) {
          mount(notice, alert({ type: "error" }, errorText(err)));
          pass.value = "";
          pass.focus();
        } finally {
          spin.remove();
          submit.disabled = false;
        }
      },
    },
    field({ label: pw ? "Name" : "Access key ID", optional: pw, control: user }),
    field({ label: pw ? "Console password" : "Secret access key", control: pass }),
    submit,
  );
  mount(
    app,
    h(
      "div",
      { class: "login" },
      h(
        "div",
        { class: "login__card" },
        h("div", { class: "login__brand" }, h("span", { class: "login__logo" }, icon("bucket", { size: 18 })), "S3"),
        h("p", { class: "login__hint" }, pw ? "Sign in with the console password." : "Sign in with an access key ID and its secret access key, the same keys your SDK signs with."),
        notice,
        form,
        h("p", { class: "login__footer" }, `Endpoint ${location.origin} · Region ${state.session.region}`),
      ),
    ),
  );
  document.title = "Sign in | S3 console";
  (pw ? pass : user).focus();
}
