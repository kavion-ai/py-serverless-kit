// The "Secret value" panel: hidden until "Retrieve secret value", then a key/value table or the plaintext,
// and "Edit" which stores a new version (PutSecretValue). The value lives only in this panel's closure.

import { call } from "../../core/api.js";
import { h, mount } from "../../core/dom.js";
import { parseObject, shortId, stringify } from "../../core/format.js";
import { generatePassword } from "../../core/password.js";
import { chip } from "../../components/badge.js";
import { button } from "../../components/button.js";
import { container } from "../../components/container.js";
import { copyButton } from "../../components/copy-button.js";
import { flash } from "../../components/flash.js";
import { kvEditor } from "../../components/kv-editor.js";
import { modal } from "../../components/modal.js";
import { segmented } from "../../components/segmented.js";

/** versionId: show that version instead of AWSCURRENT (from the Versions tab). */
export function valuePanel(secret, { onSaved, versionId } = {}) {
  const body = h("div");
  const actions = h("div", { class: "btn-group" });
  let value = null; // the GetSecretValue response, once retrieved
  let view = "kv";

  const hasVersions = Object.keys(secret.VersionIdsToStages || {}).length > 0;

  function drawHidden() {
    value = null;
    actions.replaceChildren(button("Retrieve secret value", { variant: "primary", disabled: !hasVersions, onClick: retrieve }));
    mount(body, h("div", { class: "muted" }, hasVersions
      ? "The value is hidden. Retrieve it to see or edit it; reading it updates the secret's last retrieved date."
      : "This secret has no value yet."), hasVersions ? null : h("div", { style: "margin-top:12px" },
      button("Set secret value", { onClick: () => edit("") })));
  }

  async function retrieve() {
    try {
      value = await call("GetSecretValue", versionId ? { SecretId: secret.Name, VersionId: versionId } : { SecretId: secret.Name });
      drawValue();
    } catch (err) {
      flash.error("Couldn't retrieve the secret value", err);
    }
  }

  function drawValue() {
    const binary = value.SecretBinary !== undefined;
    const obj = binary ? null : parseObject(value.SecretString);
    if (!obj) view = "text";
    const switcher = obj ? segmented([{ id: "kv", label: "Key/value" }, { id: "text", label: "Plaintext" }], {
      selected: view, label: "Value view", onChange: (id) => { view = id; drawValue(); },
    }) : null;
    mount(actions,
      button("Hide", { icon: "eyeOff", onClick: drawHidden }),
      binary || versionId ? null : button("Edit", { variant: "primary", onClick: () => edit(value.SecretString) }));
    const meta = h("div", { class: "row muted", style: "margin-bottom:12px;font-size:13px" },
      `Version ${shortId(value.VersionId)}`, ...(value.VersionStages || []).map((s) => chip(s, { accent: s === "AWSCURRENT" })),
      h("span", { class: "grow" }), switcher ? switcher.el : null);
    let content;
    if (binary) {
      content = h("div", { class: "stack" }, h("div", { class: "muted" }, "Binary value (base64)"),
        h("div", { class: "code-box" }, h("pre", { class: "code" }, value.SecretBinary), copyButton(value.SecretBinary, { label: "Copy value" })));
    } else if (view === "kv") {
      content = h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
        h("thead", {}, h("tr", {}, h("th", {}, "Secret key"), h("th", {}, "Secret value"))),
        h("tbody", {}, Object.entries(obj).map(([k, v]) => h("tr", {},
          h("td", { class: "mono cell-wrap" }, k),
          h("td", {}, h("div", { class: "row", style: "flex-wrap:nowrap;align-items:flex-start" },
            copyButton(stringify(v), { label: `Copy ${k}` }), h("span", { class: "mono cell-wrap" }, stringify(v)))))))));
    } else {
      content = h("div", { class: "code-box" }, h("pre", { class: "code", style: "white-space:pre-wrap;word-break:break-all" }, value.SecretString),
        copyButton(value.SecretString, { label: "Copy value" }));
    }
    body.replaceChildren(meta, content);
  }

  function edit(initial) {
    const editor = kvEditor({ initial, generate: generatePassword });
    let m;
    m = modal({
      title: `Edit secret value: ${secret.Name}`,
      wide: true,
      body: [h("div", { class: "muted" }, "Saving stores a new version labelled AWSCURRENT; the current version becomes AWSPREVIOUS."), editor.el],
      footer: [
        button("Cancel", { variant: "link", onClick: () => m.close() }),
        button("Save", {
          variant: "primary",
          onClick: async () => {
            let text;
            try {
              text = editor.value();
            } catch {
              return;
            }
            try {
              await call("PutSecretValue", { SecretId: secret.Name, SecretString: text });
              m.close();
              flash.success(`The secret ${secret.Name} was saved as a new version.`);
              if (onSaved) onSaved();
            } catch (err) {
              flash.error("Couldn't save the secret value", err);
            }
          },
        }),
      ],
    });
  }

  drawHidden();
  return container({
    title: "Secret value",
    description: versionId ? `Version ${versionId}` : "Retrieve and view the secret value.",
    actions: [actions],
  }, body);
}

/** The value of one version, in a dialog (Versions tab > View value). */
export function showVersionValue(secret, versionId) {
  let m;
  m = modal({
    title: `${secret.Name} - version ${shortId(versionId)}`,
    wide: true,
    body: [valuePanel({ ...secret, VersionIdsToStages: { [versionId]: [] } }, { versionId })],
    footer: [button("Close", { variant: "primary", onClick: () => m.close() })],
  });
}
