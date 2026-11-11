// Resource permissions tab: the secret's resource policy (Get / Put / Delete / ValidateResourcePolicy).
// The server stores and returns the policy; it does not enforce it.

import { call } from "../../core/api.js";
import { h, mount } from "../../core/dom.js";
import { alert } from "../../components/alert.js";
import { button } from "../../components/button.js";
import { container } from "../../components/container.js";
import { flash } from "../../components/flash.js";
import { jsonEditor } from "../../components/json-editor.js";
import { confirm } from "../../components/modal.js";

const TEMPLATE = (arn) => JSON.stringify({
  Version: "2012-10-17",
  Statement: [{
    Effect: "Allow",
    Principal: { AWS: "arn:aws:iam::000000000000:root" },
    Action: "secretsmanager:GetSecretValue",
    Resource: arn,
  }],
}, null, 2);

export function permissionsTab(secret) {
  const deleted = Boolean(secret.DeletedDate);
  const body = h("div", { class: "stack" }, h("div", { class: "table-empty" }, h("span", { class: "spinner" }), " Loading…"));
  const actions = h("div", { class: "btn-group" });
  let policy = "";

  function drawView() {
    mount(actions,
      policy ? button("Delete", { danger: true, disabled: deleted, onClick: remove }) : null,
      button(policy ? "Edit permissions" : "Add permissions", { variant: "primary", disabled: deleted, onClick: drawEdit }));
    mount(body, policy
      ? h("pre", { class: "code" }, pretty(policy))
      : h("div", { class: "table-empty" }, h("b", {}, "No resource policy"), "No resource permissions are attached to this secret."));
  }

  function drawEdit() {
    const editor = jsonEditor({ value: policy ? pretty(policy) : TEMPLATE(secret.ARN), allowEmpty: false, label: "Resource policy" });
    const note = h("div");
    actions.replaceChildren();
    body.replaceChildren(editor.el, note, h("div", { class: "btn-group", style: "justify-content:flex-end" },
      button("Format", { variant: "link", onClick: () => editor.format() }),
      button("Validate", {
        onClick: async () => {
          note.replaceChildren();
          if (!editor.valid()) return;
          try {
            await call("ValidateResourcePolicy", { SecretId: secret.Name, ResourcePolicy: editor.value() });
            note.replaceChildren(alert("success", "The policy is valid."));
          } catch (err) {
            note.replaceChildren(alert("error", "The policy is not valid", err.text || err.message));
          }
        },
      }),
      button("Cancel", { variant: "link", onClick: drawView }),
      button("Save", {
        variant: "primary",
        onClick: async () => {
          note.replaceChildren();
          if (!editor.valid()) return;
          try {
            await call("PutResourcePolicy", { SecretId: secret.Name, ResourcePolicy: editor.value() });
            policy = editor.value();
            flash.success("The resource permissions were saved.");
            drawView();
          } catch (err) {
            note.replaceChildren(alert("error", "Couldn't save the policy", err.text || err.message));
          }
        },
      })));
    editor.focus();
  }

  function remove() {
    confirm({
      title: "Delete resource permissions?",
      message: "The resource policy is removed from this secret.",
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        await call("DeleteResourcePolicy", { SecretId: secret.Name });
        policy = "";
        flash.success("The resource permissions were deleted.");
        drawView();
      },
    });
  }

  call("GetResourcePolicy", { SecretId: secret.Name })
    .then((out) => {
      policy = out.ResourcePolicy || "";
      drawView();
    })
    .catch((err) => {
      body.replaceChildren(alert("error", "Couldn't load the resource policy", err.text || err.message));
    });

  return h("div", { class: "stack" },
    alert("info", "Stored, not enforced", "This server keeps the policy and returns it to GetResourcePolicy, but every valid access key can still read and change every secret."),
    container({ title: "Resource permissions", description: "A JSON policy document attached to the secret.", actions: [actions] }, body));
}

function pretty(text) {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}
