// "Send test email", like the SES console: a formatted message (subject, text, HTML, attachments) or a template with
// its JSON data, to any address or to the mailbox simulator. On success, the MessageId links to the message page.

import { call } from "../core/api.js";
import { h, uid } from "../core/dom.js";
import { bytes } from "../core/format.js";
import { navigate, pageId, paths } from "../core/router.js";
import { alert } from "../components/alert.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { formField, input, select, textarea } from "../components/form-field.js";
import { jsonEditor } from "../components/json-editor.js";
import { pageHeader } from "../components/page-header.js";
import { segmented } from "../components/segmented.js";
import { listAllIdentities } from "./identities.js";
import { serverInfo, SIMULATOR, splitAddresses } from "./common.js";
import { showPage } from "./shell.js";

// The form survives leaving and coming back while the console is open (not the attachments).
const draft = { mode: "simple", from: "", to: "", cc: "", bcc: "", replyTo: "", subject: "", text: "", html: "", template: "", data: "{}", configSet: "" };

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result || "");
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error || new Error("The file couldn't be read."));
    reader.readAsDataURL(file);
  });
}

export function renderSend(query) {
  const me = pageId();
  if (query.get("from")) draft.from = query.get("from");
  if (query.get("template")) Object.assign(draft, { mode: "template", template: query.get("template") });
  const attachments = []; // { FileName, ContentType, RawContent, Size }

  const fromList = h("datalist", { id: uid("from") });
  const from = formField({
    label: "From address",
    description: "A verified identity, or any address at a verified domain.",
    control: input({ type: "email", value: draft.from, list: fromList.id, placeholder: "sender@example.com", autocomplete: "off" }),
  });
  const to = formField({
    label: "To",
    description: "One or more addresses, separated by commas.",
    control: input({ value: draft.to, placeholder: "recipient@example.com" }),
  });
  const quick = h("div", { class: "row quick-picks" }, h("span", { class: "muted" }, "Mailbox simulator:"),
    SIMULATOR.map((s) => h("button", {
      type: "button", class: "chip-btn", title: s.address,
      onclick: () => {
        const list = splitAddresses(to.control.value);
        if (!list.includes(s.address)) list.push(s.address);
        to.control.value = list.join(", ");
        to.setError("");
      },
    }, s.label)));
  const cc = formField({ label: "Cc", optional: true, control: input({ value: draft.cc }) });
  const bcc = formField({ label: "Bcc", optional: true, control: input({ value: draft.bcc }) });
  const replyTo = formField({ label: "Reply-To", optional: true, control: input({ value: draft.replyTo }) });

  const subject = formField({ label: "Subject", control: input({ value: draft.subject, maxlength: "998" }) });
  const text = formField({ label: "Text body", optional: true, control: textarea({ rows: 8, value: draft.text, spellcheck: "true" }) });
  const html = formField({
    label: "HTML body", optional: true,
    description: "Shown to mail clients that display HTML. Leave empty for a text-only message.",
    control: textarea({ rows: 8, value: draft.html, placeholder: "<p>Hello from <b>SES</b></p>" }),
  });

  const fileInput = h("input", { type: "file", multiple: true, class: "sr-only", id: uid("files") });
  const fileList = h("ul", { class: "file-list" });
  const drawFiles = () => {
    fileList.replaceChildren(...attachments.map((a, i) => h("li", {},
      h("span", { class: "mono" }, a.FileName), h("span", { class: "faint" }, ` ${a.ContentType} · ${bytes(a.Size)}`),
      button("Remove", { variant: "inline", onClick: () => { attachments.splice(i, 1); drawFiles(); } }))));
  };
  fileInput.addEventListener("change", async () => {
    for (const file of [...fileInput.files]) {
      try {
        attachments.push({ FileName: file.name, ContentType: file.type || "application/octet-stream", RawContent: await readBase64(file), Size: file.size });
      } catch (err) {
        flash.error(`Couldn't read ${file.name}`, err);
      }
    }
    fileInput.value = "";
    drawFiles();
  });
  const attach = h("div", { class: "field" },
    h("span", { class: "f-label" }, "Attachments", h("span", { class: "opt" }, " - optional")),
    h("div", {}, h("label", { class: "btn", for: fileInput.id }, "Choose files"), fileInput),
    fileList);

  const templateSel = formField({ label: "Template", control: select([{ value: "", label: "Loading templates…" }]) });
  const data = jsonEditor({ value: draft.data, rows: 6, label: "Template data" });
  const dataField = h("div", { class: "field" }, h("span", { class: "f-label" }, "Template data"),
    h("div", { class: "f-desc" }, "A JSON object with the values of the template's {{placeholders}}."), data.el);

  const configSet = formField({ label: "Configuration set", optional: true, control: select([{ value: "", label: "None" }]) });

  const simpleBox = h("div", { class: "stack" }, subject.el, text.el, html.el, attach);
  const templateBox = h("div", { class: "stack" }, templateSel.el, dataField);
  let mode = draft.mode;
  const modeSwitch = segmented([{ id: "simple", label: "Formatted" }, { id: "template", label: "Template" }], {
    selected: mode, label: "Email format", onChange: (v) => { mode = v; draft.mode = v; drawMode(); },
  });
  const drawMode = () => {
    simpleBox.hidden = mode !== "simple";
    templateBox.hidden = mode !== "template";
  };
  drawMode();

  const result = h("div");
  const error = h("div", { class: "f-error", role: "alert" });

  const save = () => Object.assign(draft, {
    from: from.control.value, to: to.control.value, cc: cc.control.value, bcc: bcc.control.value,
    replyTo: replyTo.control.value, subject: subject.control.value, text: text.control.value,
    html: html.control.value, template: templateSel.control.value, data: data.value(), configSet: configSet.control.value,
  });

  const send = button("Send test email", {
    variant: "primary",
    icon: "send",
    onClick: async () => {
      save();
      error.textContent = "";
      result.replaceChildren();
      [from, to, subject, templateSel].forEach((f) => f.setError(""));
      const source = from.control.value.trim();
      const toList = splitAddresses(to.control.value);
      if (!source) {
        from.setError("Enter the From address.");
        from.control.focus();
        return;
      }
      if (!toList.length) {
        to.setError("Enter at least one recipient.");
        to.control.focus();
        return;
      }
      const params = {
        FromEmailAddress: source,
        Destination: { ToAddresses: toList, CcAddresses: splitAddresses(cc.control.value), BccAddresses: splitAddresses(bcc.control.value) },
        ReplyToAddresses: splitAddresses(replyTo.control.value),
      };
      if (configSet.control.value) params.ConfigurationSetName = configSet.control.value;
      if (mode === "simple") {
        if (!subject.control.value.trim()) {
          subject.setError("Enter a subject.");
          subject.control.focus();
          return;
        }
        const body = {};
        if (text.control.value) body.Text = { Data: text.control.value, Charset: "UTF-8" };
        if (html.control.value) body.Html = { Data: html.control.value, Charset: "UTF-8" };
        if (!body.Text && !body.Html) body.Text = { Data: "", Charset: "UTF-8" };
        const simple = { Subject: { Data: subject.control.value, Charset: "UTF-8" }, Body: body };
        if (attachments.length) simple.Attachments = attachments.map(({ FileName, ContentType, RawContent }) => ({ FileName, ContentType, RawContent }));
        params.Content = { Simple: simple };
      } else {
        if (!templateSel.control.value) {
          templateSel.setError("Choose a template.");
          return;
        }
        if (!data.valid()) {
          error.textContent = "The template data is not valid JSON.";
          return;
        }
        params.Content = { Template: { TemplateName: templateSel.control.value, TemplateData: data.value().trim() || "{}" } };
      }
      try {
        const out = await call("SendEmail", params);
        result.replaceChildren(alert("success", "Email sent",
          h("div", {}, "Message ID: ", h("a", { href: `#${paths.message(out.MessageId)}`, class: "mono" }, out.MessageId)),
          h("div", { class: "row", style: "margin-top:8px" },
            button("View message", { onClick: () => navigate(paths.message(out.MessageId)) }),
            button("View all messages", { variant: "link", onClick: () => navigate("/messages") }))));
        result.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });

  const sandboxNote = h("div");
  showPage(
    breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Send test email" }]),
    pageHeader({
      title: "Send test email",
      description: "Send a message through this server, to real recipients or to the mailbox simulator (success@, bounce@, complaint@, ooto@, suppressionlist@simulator.amazonses.com).",
    }),
    sandboxNote,
    result,
    container({ title: "Message details" },
      h("div", { class: "stack" },
        h("div", { class: "field" }, h("span", { class: "f-label" }, "Email format"), h("div", {}, modeSwitch.el)),
        from.el, fromList, to.el, quick,
        h("div", { class: "form-grid" }, cc.el, bcc.el), replyTo.el, configSet.el)),
    container({ title: "Content" }, simpleBox, templateBox),
    h("div", { class: "form-actions" }, error, h("div", { class: "btn-group" },
      button("Clear", {
        variant: "link",
        onClick: () => {
          Object.assign(draft, { from: "", to: "", cc: "", bcc: "", replyTo: "", subject: "", text: "", html: "", template: "", data: "{}", configSet: "" });
          renderSend(new URLSearchParams());
        },
      }),
      send)));

  // Fill the choices.
  listAllIdentities().then((ids) => {
    if (me !== pageId()) return;
    const verified = ids.filter((i) => i.VerificationStatus === "SUCCESS");
    fromList.replaceChildren(...verified.map((i) => h("option", {
      value: i.IdentityType === "DOMAIN" ? `noreply@${i.IdentityName}` : i.IdentityName,
    })));
    if (!verified.length) {
      sandboxNote.prepend(alert("warning", "No verified identities",
        "Create and verify a domain or address first, unless the server runs with SES_VERIFY=off.",
        h("div", { style: "margin-top:8px" }, button("Create identity", { onClick: () => navigate("/identities/create") }))));
    }
  }).catch(() => {});
  call("ListEmailTemplates", { PageSize: 100 }).then((out) => {
    if (me !== pageId()) return;
    const names = (out.TemplatesMetadata || []).map((t) => t.TemplateName);
    templateSel.control.replaceChildren(
      h("option", { value: "" }, names.length ? "Choose a template" : "No templates"),
      ...names.map((n) => h("option", { value: n, selected: n === draft.template }, n)));
  }).catch(() => {});
  call("ListConfigurationSets", { PageSize: 1000 }).then((out) => {
    if (me !== pageId()) return;
    configSet.control.replaceChildren(h("option", { value: "" }, "None"),
      ...(out.ConfigurationSets || []).map((n) => h("option", { value: n, selected: n === draft.configSet }, n)));
  }).catch(() => {});
  serverInfo().then((info) => {
    if (me !== pageId()) return;
    if (info.Sandbox) {
      sandboxNote.append(alert("info", "Sandbox", "Recipients must be verified identities or mailbox simulator addresses."));
    }
    if (info.Delivery === "capture") {
      sandboxNote.append(alert("info", "Capture mode: mail is kept, not sent", "The message is stored and shown under Messages; nothing leaves the server."));
    }
  }).catch(() => {});
}
