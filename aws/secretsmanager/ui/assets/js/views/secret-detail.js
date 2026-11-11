// One secret: details, its value (retrieved on request), and the Overview / Rotation / Versions / Tags /
// Resource permissions tabs.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { dateTime, utcDate } from "../core/format.js";
import { navigate, setQuery } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { codeSamples } from "../components/code-samples.js";
import { container } from "../components/container.js";
import { copyText } from "../components/copy-button.js";
import { dropdown } from "../components/dropdown.js";
import { flash } from "../components/flash.js";
import { formField, input } from "../components/form-field.js";
import { keyValue } from "../components/key-value.js";
import { modal } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { tabs } from "../components/tabs.js";
import { openDeleteSecret } from "./delete-secret.js";
import { renderNotFound } from "./not-found.js";
import { permissionsTab } from "./secret/permissions-tab.js";
import { tagsTab } from "./secret/tags-tab.js";
import { valuePanel } from "./secret/value-panel.js";
import { versionsTab } from "./secret/versions-tab.js";
import { showPage } from "./shell.js";

export async function renderSecret(name, tab) {
  const crumbs = breadcrumbs([{ label: "Secrets Manager", href: "#/secrets" }, { label: "Secrets", href: "#/secrets" }, { label: name }]);
  showPage(crumbs, pageHeader({ title: name }), container({}, h("div", { class: "table-empty" }, h("span", { class: "spinner" }), " Loading…")));
  let secret;
  try {
    secret = await call("DescribeSecret", { SecretId: name });
  } catch (err) {
    if (err.code === "ResourceNotFoundException") renderNotFound(`The secret ${name} doesn't exist. It may have been deleted.`);
    else if (err.status !== 401) {
      flash.error(`Couldn't load ${name}`, err);
      showPage(crumbs, pageHeader({ title: name }));
    }
    return;
  }
  draw(secret, tab);
}

function draw(secret, tab) {
  const reload = (nextTab) => renderSecret(secret.Name, nextTab);
  const deleted = Boolean(secret.DeletedDate);

  const actions = dropdown("Actions", [
    deleted
      ? { label: "Cancel deletion", onSelect: () => restore(secret, reload) }
      : { label: "Delete secret", onSelect: () => openDeleteSecret(secret, { onDone: (force) => (force ? navigate("/secrets") : reload()) }) },
    { label: "Edit description", disabled: deleted, onSelect: () => editDescription(secret, reload) },
    { label: "Copy secret ARN", onSelect: async () => ((await copyText(secret.ARN)) ? flash.info("Secret ARN copied") : flash.error("Couldn't copy the ARN")) },
  ]);

  const details = container({ title: "Secret details" }, keyValue([
    [{ label: "Encryption key", value: secret.KmsKeyId || "aws/secretsmanager" },
      { label: "Status", value: deleted ? badge("warning", "Scheduled for deletion") : badge("success", "Available") }],
    [{ label: "Secret name", value: secret.Name, copy: secret.Name },
      { label: "Secret ARN", value: secret.ARN, copy: secret.ARN, mono: true }],
    [{ label: "Secret description", value: secret.Description },
      { label: "Last retrieved (UTC)", value: utcDate(secret.LastAccessedDate) }],
    [{ label: "Created", value: dateTime(secret.CreatedDate) },
      { label: "Last modified", value: dateTime(secret.LastChangedDate) }],
  ]));

  const tabItems = [
    {
      id: "overview", label: "Overview",
      render: () => container({ title: "Sample code", description: "Use these snippets to retrieve the secret in your application." },
        codeSamples(secret.Name)),
    },
    {
      id: "rotation", label: "Rotation",
      render: () => container({ title: "Rotation configuration" },
        keyValue([[{ label: "Rotation status", value: badge("stopped", "Disabled") }], [{ label: "Rotation schedule", value: "None" }]]),
        h("div", { style: "margin-top:16px" }, alert("info", "Rotation is not supported by this server",
          "RotateSecret and rotation functions are not available. Rotate by storing a new value (Secret value > Edit): "
          + "the new version becomes AWSCURRENT and the old one AWSPREVIOUS."))),
    },
    { id: "versions", label: "Versions", render: () => versionsTab(secret, { onChange: () => reload("versions") }) },
    { id: "tags", label: "Tags", render: () => tagsTab(secret, { onChange: () => reload("tags") }) },
    { id: "permissions", label: "Resource permissions", render: () => permissionsTab(secret) },
  ];

  showPage(
    breadcrumbs([{ label: "Secrets Manager", href: "#/secrets" }, { label: "Secrets", href: "#/secrets" }, { label: secret.Name }]),
    pageHeader({ title: secret.Name, actions: [actions] }),
    deleted ? alert("warning", "This secret is scheduled for deletion",
      `Deletion was requested ${dateTime(secret.DeletedDate)}. Applications can't read it. Cancel the deletion to use it again.`,
      h("div", { style: "margin-top:8px" }, button("Cancel deletion", { onClick: () => restore(secret, reload) }))) : null,
    details,
    deleted ? null : valuePanel(secret, { onSaved: () => reload("versions") }),
    tabs(tabItems, { selected: tab || "overview", onChange: (id) => setQuery({ tab: id === "overview" ? null : id }) }));
}

async function restore(secret, reload) {
  try {
    await call("RestoreSecret", { SecretId: secret.Name });
    flash.success(`The deletion of ${secret.Name} was canceled.`);
    reload();
  } catch (err) {
    flash.error("Couldn't cancel the deletion", err);
  }
}

function editDescription(secret, reload) {
  const field = formField({ label: "Description", optional: true, control: input({ value: secret.Description || "", maxlength: "2048" }) });
  let m;
  m = modal({
    title: "Edit description",
    body: [field.el],
    footer: [
      button("Cancel", { variant: "link", onClick: () => m.close() }),
      button("Save", {
        variant: "primary",
        onClick: async () => {
          try {
            await call("UpdateSecret", { SecretId: secret.Name, Description: field.control.value.trim() });
            m.close();
            flash.success("The description was saved.");
            reload();
          } catch (err) {
            field.setError(err.text || err.message);
          }
        },
      }),
    ],
  });
}
