// The "Delete secret" dialog: a waiting period of 7-30 days (the secret can be restored until then) or, explicitly,
// deletion without recovery. The name must be typed to confirm.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { dateTime } from "../core/format.js";
import { alert } from "../components/alert.js";
import { button } from "../components/button.js";
import { flash } from "../components/flash.js";
import { checkbox, formField, input } from "../components/form-field.js";
import { modal } from "../components/modal.js";

export function openDeleteSecret(secret, { onDone } = {}) {
  const days = formField({
    label: "Waiting period",
    description: "Days before the secret is deleted for good. You can cancel the deletion until then.",
    constraint: "7 to 30 days.",
    control: input({ type: "number", min: "7", max: "30", value: "30", inputmode: "numeric" }),
  });
  const force = checkbox("Delete immediately, without a recovery window");
  const forceWarn = alert("error", "This can't be undone", "The secret and all its versions are removed now.");
  forceWarn.hidden = true;
  force.box.addEventListener("change", () => {
    days.control.disabled = force.box.checked;
    forceWarn.hidden = !force.box.checked;
  });
  const confirmField = formField({
    label: `To confirm, type the secret name`,
    control: input({ placeholder: secret.Name, "aria-label": "Secret name to confirm" }),
  });

  const submit = button("Schedule deletion", {
    variant: "primary",
    danger: true,
    onClick: async () => {
      confirmField.setError("");
      days.setError("");
      if (confirmField.control.value !== secret.Name) {
        confirmField.setError("The name doesn't match.");
        confirmField.control.focus();
        return;
      }
      const params = { SecretId: secret.Name };
      if (force.box.checked) params.ForceDeleteWithoutRecovery = true;
      else {
        const n = Number(days.control.value);
        if (!Number.isInteger(n) || n < 7 || n > 30) {
          days.setError("Enter a whole number of days from 7 to 30.");
          return;
        }
        params.RecoveryWindowInDays = n;
      }
      try {
        const out = await call("DeleteSecret", params);
        m.close();
        if (force.box.checked) flash.success(`The secret ${secret.Name} was deleted.`);
        else flash.success(`The secret ${secret.Name} is scheduled for deletion on ${dateTime(out.DeletionDate)}.`,
          "Use Actions > Cancel deletion to keep it.");
        if (onDone) onDone(force.box.checked);
      } catch (err) {
        confirmField.setError(err.text || err.message);
      }
    },
  });
  force.box.addEventListener("change", () => {
    submit.lastChild.textContent = force.box.checked ? "Delete now" : "Schedule deletion";
  });

  const m = modal({
    title: "Delete secret",
    body: [
      alert("warning", "Applications can't read a deleted secret",
        "Any application or service that uses this secret fails to retrieve it once it is scheduled for deletion. "
        + "Check that nothing still uses it."),
      h("div", {}, h("span", { class: "muted" }, "Secret: "), h("b", {}, secret.Name)),
      days.el,
      force.el,
      forceWarn,
      confirmField.el,
    ],
    footer: [button("Cancel", { variant: "link", onClick: () => m.close() }), submit],
  });
}
