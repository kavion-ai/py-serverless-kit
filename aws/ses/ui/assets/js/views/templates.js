// Email templates: the list, create / edit (name, subject, text and HTML parts), and a template's page with its
// content and "Test render" (TestRenderEmailTemplate with JSON data -> rendered subject, HTML preview, text, raw MIME).

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { dateTime, relative } from "../core/format.js";
import { readMime } from "../core/mime.js";
import { navigate, pageId, paths } from "../core/router.js";
import { alert } from "../components/alert.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { copyButton } from "../components/copy-button.js";
import { flash } from "../components/flash.js";
import { formField, input, textarea } from "../components/form-field.js";
import { disposePreview, htmlPreview } from "../components/html-preview.js";
import { jsonEditor } from "../components/json-editor.js";
import { keyValue } from "../components/key-value.js";
import { confirm } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { tabs } from "../components/tabs.js";
import { tagEditor } from "../components/tag-editor.js";
import { loadingPanel } from "./common.js";
import { renderNotFound } from "./not-found.js";
import { keepFlash, showPage } from "./shell.js";

const root = { label: "Amazon SES", href: "#/account" };
const list = { label: "Email templates", href: "#/templates" };

async function allTemplates() {
  const out = [];
  let token;
  do {
    const page = await call("ListEmailTemplates", { PageSize: 100, ...(token ? { NextToken: token } : {}) });
    out.push(...(page.TemplatesMetadata || []));
    token = page.NextToken;
  } while (token);
  return out;
}

export function renderTemplates() {
  const me = pageId();
  const t = table({
    title: "Email templates",
    description: "Templates hold a subject, a text part and an HTML part with {{placeholders}} filled from JSON data when you send.",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Create template", { variant: "primary", onClick: () => navigate("/templates/create") }),
    ],
    filter: { placeholder: "Find templates", match: (r, text) => r.TemplateName.toLowerCase().includes(text) },
    columns: [
      { id: "name", header: "Template name", wrap: true, sort: (r) => r.TemplateName.toLowerCase(), cell: (r) => h("a", { href: `#${paths.template(r.TemplateName)}` }, r.TemplateName) },
      { id: "created", header: "Created", sort: (r) => r.CreatedTimestamp || 0, cell: (r) => h("span", { title: dateTime(r.CreatedTimestamp) }, relative(r.CreatedTimestamp)) },
    ],
    trackBy: (r) => r.TemplateName,
    pageSize: 50,
    loading: true,
    empty: () => h("div", { class: "table-empty" }, h("b", {}, "No templates"), "Create a template to send personalized email.",
      h("div", {}, button("Create template", { onClick: () => navigate("/templates/create") }))),
  });
  async function load() {
    t.setLoading(true);
    try {
      const items = await allTemplates();
      if (me === pageId()) t.setItems(items);
    } catch (err) {
      t.setItems([]);
      if (err.status !== 401) flash.error("Couldn't load the templates", err);
    }
  }
  showPage(breadcrumbs([root, { label: "Email templates" }]), pageHeader({ title: "Email templates" }), t.el);
  load();
}

/** Create (name === null) or edit a template. */
export async function renderTemplateForm(name) {
  const editing = name !== null && name !== undefined;
  const crumbs = breadcrumbs([root, list, ...(editing ? [{ label: name, href: `#${paths.template(name)}` }, { label: "Edit" }] : [{ label: "Create template" }])]);
  let current = { TemplateContent: { Subject: "", Text: "", Html: "" }, Tags: [] };
  if (editing) {
    showPage(crumbs, pageHeader({ title: `Edit ${name}` }), loadingPanel());
    const me = pageId();
    try {
      current = await call("GetEmailTemplate", { TemplateName: name });
    } catch (err) {
      if (me !== pageId()) return;
      if (err.status === 404) renderNotFound(`The template ${name} doesn't exist.`);
      else if (err.status !== 401) flash.error(`Couldn't load ${name}`, err);
      return;
    }
    if (me !== pageId()) return;
  }
  const c = current.TemplateContent || {};
  const nameField = formField({
    label: "Template name",
    constraint: "Up to 64 characters: letters, digits, _ and -.",
    control: input({ value: editing ? name : "", maxlength: "64", disabled: editing }),
  });
  const subject = formField({ label: "Subject", description: "May contain {{placeholders}}.", control: input({ value: c.Subject || "", placeholder: "Your order {{orderId}} has shipped" }) });
  const text = formField({ label: "Text part", optional: true, control: textarea({ rows: 8, value: c.Text || "", placeholder: "Hello {{name}},\n…" }) });
  const html = formField({ label: "HTML part", optional: true, control: textarea({ rows: 12, value: c.Html || "", placeholder: "<h1>Hello {{name}}</h1>" }) });
  const tags = editing ? null : tagEditor([]);
  const error = h("div", { class: "f-error", role: "alert" });

  const submit = button(editing ? "Save changes" : "Create template", {
    variant: "primary",
    onClick: async () => {
      error.textContent = "";
      nameField.setError("");
      subject.setError("");
      const tplName = editing ? name : nameField.control.value.trim();
      if (!/^[A-Za-z0-9_-]{1,64}$/.test(tplName)) {
        nameField.setError("Use 1 to 64 letters, digits, _ or -.");
        nameField.control.focus();
        return;
      }
      if (!subject.control.value && !text.control.value && !html.control.value) {
        subject.setError("A template needs a subject, a text part or an HTML part.");
        return;
      }
      const params = { TemplateName: tplName, TemplateContent: { Subject: subject.control.value, Text: text.control.value, Html: html.control.value } };
      try {
        if (tags) params.Tags = tags.value();
        await call(editing ? "UpdateEmailTemplate" : "CreateEmailTemplate", params);
        keepFlash();
        flash.success(editing ? `The template ${tplName} was saved.` : `The template ${tplName} was created.`);
        navigate(paths.template(tplName));
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });

  showPage(
    crumbs,
    pageHeader({ title: editing ? `Edit ${name}` : "Create template", description: "Use {{name}} placeholders; {{#if x}}…{{/if}} and {{#each list}}…{{/each}} blocks are supported as on SES." }),
    container({ title: "Template details" }, nameField.el),
    container({ title: "Content" }, h("div", { class: "stack" }, subject.el, text.el, html.el)),
    tags ? container({ title: "Tags", description: "Optional labels." }, tags.el) : null,
    h("div", { class: "form-actions" }, error, h("div", { class: "btn-group" },
      button("Cancel", { variant: "link", onClick: () => navigate(editing ? paths.template(name) : "/templates") }), submit)));
}

export async function renderTemplate(name) {
  const crumbs = breadcrumbs([root, list, { label: name }]);
  showPage(crumbs, pageHeader({ title: name }), loadingPanel());
  const me = pageId();
  let tpl;
  try {
    tpl = await call("GetEmailTemplate", { TemplateName: name });
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status === 404) renderNotFound(`The template ${name} doesn't exist. It may have been deleted.`);
    else if (err.status !== 401) {
      flash.error(`Couldn't load ${name}`, err);
      showPage(crumbs, pageHeader({ title: name }));
    }
    return;
  }
  if (me !== pageId()) return;
  const c = tpl.TemplateContent || {};

  const del = button("Delete", {
    danger: true,
    onClick: () => confirm({
      title: `Delete ${name}?`,
      message: "Sending with this template fails once it is deleted.",
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        await call("DeleteEmailTemplate", { TemplateName: name });
        keepFlash();
        flash.success(`The template ${name} was deleted.`);
        navigate("/templates");
      },
    }),
  });

  const placeholders = [...new Set(`${c.Subject || ""} ${c.Text || ""} ${c.Html || ""}`.match(/\{\{\s*([A-Za-z_][\w.]*)\s*\}\}/g) || [])]
    .map((p) => p.replace(/[{}\s]/g, "")).filter((p) => p !== "this" && p !== "else");
  const sample = {};
  placeholders.forEach((p) => {
    const keys = p.split(".");
    let at = sample;
    keys.forEach((k, i) => {
      if (i === keys.length - 1) at[k] = at[k] === undefined ? k : at[k];
      else {
        if (typeof at[k] !== "object" || at[k] === null) at[k] = {};
        at = at[k];
      }
    });
  });

  const content = tabs([
    { id: "html", label: "HTML part", render: () => (c.Html ? sourceBox(c.Html) : h("div", { class: "faint" }, "No HTML part.")) },
    { id: "text", label: "Text part", render: () => (c.Text ? sourceBox(c.Text) : h("div", { class: "faint" }, "No text part.")) },
  ]);

  showPage(
    crumbs,
    pageHeader({
      title: name,
      actions: [
        button("Send with this template", { icon: "send", onClick: () => navigate(`/send?template=${encodeURIComponent(name)}`) }),
        button("Edit", { onClick: () => navigate(paths.editTemplate(name)) }),
        del,
      ],
    }),
    container({ title: "Template" }, keyValue([
      [{ label: "Template name", value: name, copy: name }],
      [{ label: "Subject", value: c.Subject }],
      [{ label: "Placeholders", value: placeholders.length ? placeholders.join(", ") : null }],
    ])),
    container({ title: "Content" }, content),
    testRender(name, sample));
}

function sourceBox(text) {
  const pre = h("pre", { class: "code wrap" });
  pre.textContent = text;
  return h("div", { class: "code-box" }, pre, copyButton(text, { label: "Copy" }));
}

function testRender(name, sample) {
  const data = jsonEditor({ value: JSON.stringify(sample, null, 2), rows: 8, label: "Template data" });
  const out = h("div");
  let frame = null;
  const run = button("Test render", {
    variant: "primary",
    onClick: async () => {
      if (!data.valid()) return;
      try {
        const res = await call("TestRenderEmailTemplate", { TemplateName: name, TemplateData: data.value().trim() || "{}" });
        const raw = res.RenderedTemplate || "";
        const parsed = readMime(raw);
        disposePreview(frame);
        frame = null;
        const items = [];
        if (parsed.html) {
          items.push({
            id: "html", label: "HTML preview", render: () => {
              disposePreview(frame);
              frame = htmlPreview(parsed.html, { title: "Rendered HTML", height: 420 });
              return h("div", { class: "preview-wrap" }, frame);
            },
          });
        }
        items.push({ id: "text", label: "Text", render: () => sourceBox(parsed.text || "(empty)") });
        items.push({ id: "raw", label: "Raw MIME", render: () => sourceBox(raw) });
        out.replaceChildren(h("div", { class: "stack" },
          keyValue([[{ label: "Rendered subject", value: parsed.subject || "(empty)" }]]),
          tabs(items)));
      } catch (err) {
        out.replaceChildren(alert("error", "The template couldn't be rendered", err.text || err.message));
      }
    },
  });
  return container({
    title: "Test render",
    description: "Fill the placeholders with JSON data and see the message the template produces.",
  }, h("div", { class: "stack" }, data.el, h("div", { class: "row" }, run, button("Format JSON", { variant: "link", onClick: () => data.format() })), out));
}
