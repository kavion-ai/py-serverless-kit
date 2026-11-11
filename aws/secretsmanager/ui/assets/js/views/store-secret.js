// "Store a new secret": a three-step wizard (value and encryption key, name/description/tags/permissions, review).

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { generatePassword } from "../core/password.js";
import { navigate, secretPath } from "../core/router.js";
import { alert } from "../components/alert.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { codeSamples } from "../components/code-samples.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { formField, input } from "../components/form-field.js";
import { jsonEditor } from "../components/json-editor.js";
import { keyValue } from "../components/key-value.js";
import { kvEditor } from "../components/kv-editor.js";
import { tagEditor } from "../components/tag-editor.js";
import { wizard } from "../components/wizard.js";
import { keepFlash, showPage } from "./shell.js";

const NAME_RE = /^[A-Za-z0-9/_+=.@-]{1,512}$/;
const DEFAULT_KEY = "aws/secretsmanager";

export function renderStoreSecret() {
  const value = kvEditor({ initial: "", generate: generatePassword });
  const kms = formField({
    label: "Encryption key",
    description: "The master key of this server that encrypts the secret: aws/secretsmanager (the default key), a key id, "
      + "alias/<id>, or a KMS ARN ending in one.",
    control: input({ value: DEFAULT_KEY, placeholder: DEFAULT_KEY }),
  });
  const name = formField({
    label: "Secret name",
    description: "A descriptive name that helps you find your secret later.",
    constraint: "1-512 characters: letters, digits and /_+=.@- . Use / for a hierarchy, e.g. prod/payments/db.",
    control: input({ placeholder: "prod/AppBeta/MySql" }),
  });
  const desc = formField({ label: "Description", optional: true, control: input({ maxlength: "2048", placeholder: "Access to MYSQL prod database for my AppBeta" }) });
  const tags = tagEditor([]);
  const tagError = h("div", { class: "f-error", role: "alert" });
  const policy = jsonEditor({ placeholder: '{\n  "Version": "2012-10-17",\n  "Statement": []\n}', label: "Resource permissions" });

  let secretString = "";

  const step1 = () => h("div", { class: "stack" },
    container({ title: "Secret type" }, h("div", { class: "tiles" },
      h("div", { class: "tile on" }, h("input", { type: "radio", checked: true, "aria-label": "Other type of secret", tabindex: "-1" }),
        h("div", {}, h("b", {}, "Other type of secret"), h("span", {}, "API key, OAuth token, database credentials or any other text."))))),
    container({ title: "Key/value pairs", description: "Values are encrypted before they are written to disk." }, value.el),
    container({ title: "Encryption key" }, kms.el));

  const step2 = () => h("div", { class: "stack" },
    container({ title: "Secret name and description" }, name.el, desc.el),
    container({ title: "Tags - optional", description: "Tags help you find and filter secrets (the list filter matches tag keys and values)." },
      tags.el, tagError),
    container({
      title: "Resource permissions - optional",
      description: "A JSON resource policy stored with the secret and returned by GetResourcePolicy. This server stores it; it does not enforce it.",
    }, policy.el));

  const review = () => {
    const pairs = [[{ label: "Encryption key", value: kms.control.value.trim() || DEFAULT_KEY }],
      [{ label: "Secret name", value: name.control.value.trim() }],
      [{ label: "Description", value: desc.control.value.trim() }]];
    let tagList = [];
    try {
      tagList = tags.value();
    } catch {
      tagList = [];
    }
    return h("div", { class: "stack" },
      container({ title: "Step 1: Secret type and value" }, keyValue([
        [{ label: "Secret type", value: "Other type of secret" }],
        [{ label: "Value", value: h("span", { class: "masked" }, "••••••••••") }],
        [{ label: "Encryption key", value: kms.control.value.trim() || DEFAULT_KEY }],
      ])),
      container({ title: "Step 2: Configure secret" }, keyValue(pairs),
        h("div", { style: "margin-top:16px" }, h("div", { class: "kv-label muted", style: "font-weight:700;font-size:13px" }, "Tags"),
          tagList.length ? tagList.map((t) => h("span", { class: "chip" }, `${t.Key}${t.Value ? ` = ${t.Value}` : ""}`)) : h("span", { class: "faint" }, "-")),
        h("div", { style: "margin-top:16px" }, h("div", { style: "font-weight:700;font-size:13px", class: "muted" }, "Resource permissions"),
          policy.value().trim() ? "A resource policy will be attached." : h("span", { class: "faint" }, "-"))),
      container({ title: "Sample code", description: "Read the secret from your application once it is stored." },
        codeSamples(name.control.value.trim() || "my-secret")));
  };

  function validateValue() {
    try {
      secretString = value.value();
    } catch {
      return false;
    }
    if (!secretString || secretString === "{}") {
      flash.error("Enter a secret value", null);
      return false;
    }
    if (new TextEncoder().encode(secretString).length > 65536) {
      flash.error("The secret value is too large", "A secret value can be at most 64 KB.");
      return false;
    }
    return true;
  }

  function validateConfig() {
    let ok = true;
    const n = name.control.value.trim();
    name.setError(NAME_RE.test(n) ? "" : "Enter a name of 1-512 letters, digits and /_+=.@- characters.");
    if (!NAME_RE.test(n)) {
      ok = false;
      name.control.focus();
    }
    tagError.textContent = "";
    try {
      tags.value();
    } catch (err) {
      tagError.textContent = err.message;
      ok = false;
    }
    if (!policy.valid()) ok = false;
    return ok;
  }

  async function submit() {
    if (!validateValue() || !validateConfig()) throw new Error("Check the steps above: some values are not valid.");
    const n = name.control.value.trim();
    const params = { Name: n, SecretString: secretString, Tags: tags.value() };
    if (desc.control.value.trim()) params.Description = desc.control.value.trim();
    const key = kms.control.value.trim();
    if (key && key !== DEFAULT_KEY) params.KmsKeyId = key;
    await call("CreateSecret", params);
    if (policy.value().trim()) {
      try {
        await call("PutResourcePolicy", { SecretId: n, ResourcePolicy: policy.value() });
      } catch (err) {
        keepFlash();
        flash.warning("The secret was stored, but its resource policy was not", err.text || err.message);
      }
    }
    secretString = "";
    keepFlash();
    flash.success(`You successfully stored the secret ${n}.`, "Applications can read it now with GetSecretValue.");
    navigate(secretPath(n));
  }

  showPage(
    breadcrumbs([{ label: "Secrets Manager", href: "#/secrets" }, { label: "Secrets", href: "#/secrets" }, { label: "Store a new secret" }]),
    wizard({
      steps: [
        { title: "Choose secret type", render: step1, validate: validateValue },
        { title: "Configure secret", render: step2, validate: validateConfig },
        { title: "Review", render: review, fresh: true },
      ],
      submitLabel: "Store",
      onSubmit: submit,
      onCancel: () => navigate("/secrets"),
    }),
    alert("info", "Rotation", "Automatic rotation is not available on this server. Store a new value with \"Retrieve secret value\" > Edit when you rotate credentials."));
}
