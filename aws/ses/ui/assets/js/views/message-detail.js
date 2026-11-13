// One message: summary, per-recipient delivery status with the SMTP responses, the event timeline, and tabs for the
// HTML body (sandboxed blob: frame), text, headers, attachments and the raw MIME source. Retry now and Delete.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { bytes, dateTime, relative } from "../core/format.js";
import { navigate, pageId, paths, setQuery } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge, chip } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { copyButton } from "../components/copy-button.js";
import { flash } from "../components/flash.js";
import { htmlPreview } from "../components/html-preview.js";
import { keyValue } from "../components/key-value.js";
import { confirm } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { tabs } from "../components/tabs.js";
import { DELIVERY_LABEL, deliveryLink, loadingPanel, messageStatus } from "./common.js";
import { renderNotFound } from "./not-found.js";
import { keepFlash, showPage } from "./shell.js";

const crumbs = (id) => breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Messages", href: "#/messages" }, { label: id }]);

const EVENT_TONE = {
  Send: "info", Delivery: "success", Bounce: "error", Complaint: "warning", Reject: "error",
  DeliveryDelay: "warning", RenderingFailure: "error", Open: "info", Click: "info",
};
const EVENT_LABEL = { DeliveryDelay: "Delivery delay", RenderingFailure: "Rendering failure" };

export async function renderMessage(id, tab) {
  showPage(crumbs(id), pageHeader({ title: "Message" }), loadingPanel());
  const me = pageId();
  let msg;
  try {
    msg = await call("GetMessage", { MessageId: id });
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status === 404) renderNotFound(`The message ${id} doesn't exist. It may be older than the retention period, or deleted.`);
    else if (err.status !== 401) {
      flash.error("Couldn't load the message", err);
      showPage(crumbs(id), pageHeader({ title: "Message" }));
    }
    return;
  }
  if (me !== pageId()) return;
  draw(id, msg, tab);
}

function draw(id, msg, tab) {
  const reload = () => renderMessage(id, tab);
  const recipients = Object.entries(msg.Recipients || {}).map(([address, st]) => ({ address, ...st }));
  const waiting = recipients.filter((r) => r.Status === "QUEUED" || r.Status === "DELAYED");
  const content = msg.Content || {};

  const retry = waiting.length ? button("Retry now", {
    icon: "refresh",
    onClick: async () => {
      try {
        await call("RetryMessage", { MessageId: id });
        flash.success("Delivery will be retried now.", `${waiting.length} recipient${waiting.length === 1 ? "" : "s"} waiting.`);
        setTimeout(() => { if (document.body.contains(header)) reload(); }, 1500);
      } catch (err) {
        flash.error("Couldn't retry the message", err);
      }
    },
  }) : null;
  const del = button("Delete", {
    danger: true,
    onClick: () => {
      confirm({
        title: "Delete this message?",
        message: "The message, its content and its delivery history are removed from the server. Recipients still waiting won't get it.",
        confirmLabel: "Delete",
        danger: true,
        onConfirm: async () => {
          await call("DeleteMessage", { MessageId: id });
          keepFlash();
          flash.success("The message was deleted.");
          navigate("/messages");
        },
      });
    },
  });

  const header = pageHeader({
    title: msg.Subject || "(no subject)",
    extra: messageStatus(msg.Status),
    actions: [button("Refresh", { variant: "icon", icon: "refresh", onClick: reload }), retry, del].filter(Boolean),
  });

  const tags = (msg.Tags || []).map((t) => chip(`${t.Name}=${t.Value}`));
  const summary = container({ title: "Message details" }, keyValue([
    [{ label: "Message ID", value: msg.MessageId, copy: msg.MessageId, mono: true },
      { label: "Status", value: messageStatus(msg.Status) },
      { label: "Accepted", value: dateTime(msg.Timestamp) }],
    [{ label: "From", value: msg.Source || msg.From },
      { label: "Envelope sender (MAIL FROM)", value: msg.MailFrom },
      { label: "Recipients", value: (msg.Destinations || []).join(", ") }],
    [{ label: "Sent with", value: `${msg.Operation || "-"}${msg.Caller ? ` by ${msg.Caller}` : ""}` },
      { label: "Source IP", value: msg.SourceIp, mono: true },
      { label: "Configuration set", value: msg.ConfigurationSetName ? h("a", { href: `#${paths.configSet(msg.ConfigurationSetName)}` }, msg.ConfigurationSetName) : null }],
    [{ label: "Size", value: bytes(msg.Size) },
      { label: "DKIM signed by", value: msg.DkimDomain || h("span", { class: "faint" }, "Not signed") },
      { label: "Delivery", value: `${DELIVERY_LABEL[msg.Delivery] || msg.Delivery || "-"}${msg.TlsPolicy ? `, TLS ${msg.TlsPolicy.toLowerCase()}` : ""}` }],
  ]),
  tags.length ? h("div", { style: "margin-top:16px" }, h("div", { class: "kv-label" }, "Message tags"), h("div", {}, tags)) : null);

  const banner = msg.Delivery === "capture"
    ? alert("info", "Captured: this message was kept, not sent", "The server was in capture mode, so the message was stored and marked delivered without leaving the server. ",
      deliveryLink())
    : null;

  const rcpt = table({
    title: "Recipients",
    columns: [
      { id: "addr", header: "Recipient", wrap: true, sort: (r) => r.address, cell: (r) => r.address },
      { id: "status", header: "Status", sort: (r) => r.Status, cell: (r) => messageStatus(r.Status) },
      { id: "attempts", header: "Attempts", cell: (r) => String(r.Attempts || 0) },
      { id: "response", header: "SMTP response", wrap: true, cell: (r) => (r.Response ? h("span", { class: "mono" }, r.Response) : h("span", { class: "faint" }, "-")) },
      { id: "mta", header: "Remote MTA", cell: (r) => (r.RemoteMtaIp ? h("span", { class: "mono" }, r.RemoteMtaIp) : h("span", { class: "faint" }, "-")) },
      {
        id: "when", header: "Last / next attempt",
        cell: (r) => h("div", {},
          r.LastAttempt ? h("div", { title: dateTime(r.LastAttempt) }, `Last ${relative(r.LastAttempt)}`) : null,
          r.NextAttempt && (r.Status === "QUEUED" || r.Status === "DELAYED") ? h("div", { class: "faint", title: dateTime(r.NextAttempt) }, r.NextAttempt * 1000 <= Date.now() ? "Next: now" : `Next ${relative(r.NextAttempt)}`) : null,
          !r.LastAttempt && !r.NextAttempt ? h("span", { class: "faint" }, "-") : null),
      },
    ],
    items: recipients,
    trackBy: (r) => r.address,
  });

  const items = [
    { id: "html", label: "HTML", render: () => (content.Html ? container({ title: "HTML body", description: "Shown in a sandbox: scripts don't run and remote images are not loaded.", flush: true }, htmlPreview(content.Html, { title: "HTML body of the message" })) : emptyBox("This message has no HTML body.")) },
    { id: "text", label: "Text", render: () => (content.Text ? codeBox(content.Text, "Copy text") : emptyBox("This message has no text body.")) },
    { id: "headers", label: "Headers", render: () => headersTable(content.Headers || []) },
    { id: "attachments", label: `Attachments (${(content.Attachments || []).length})`, render: () => attachmentsTable(content.Attachments || []) },
    { id: "raw", label: "Raw", render: () => rawTab(id) },
  ];
  const firstTab = content.Html ? "html" : "text";

  showPage(
    crumbs(id),
    header,
    banner,
    summary,
    rcpt.el,
    container({ title: "Events", description: "What happened to the message, oldest first." }, timeline(msg.Events || [])),
    tabs(items, { selected: tab || firstTab, onChange: (t) => { tab = t; setQuery({ tab: t === firstTab ? null : t }); } }));
}

function emptyBox(text) {
  return container({}, h("div", { class: "table-empty" }, text));
}

function codeBox(text, label) {
  const pre = h("pre", { class: "code wrap" });
  pre.textContent = text;
  return h("div", { class: "code-box" }, pre, copyButton(text, { label }));
}

function timeline(events) {
  if (!events.length) return h("div", { class: "faint" }, "No events yet.");
  const SKIP = new Set(["Type", "Timestamp", "Recipients"]);
  return h("ol", { class: "timeline" }, events.map((ev) => {
    const details = Object.entries(ev).filter(([k, v]) => !SKIP.has(k) && v !== "" && v !== null && v !== undefined);
    return h("li", { class: ["tl-item", EVENT_TONE[ev.Type] || "info"] },
      h("span", { class: "tl-dot", "aria-hidden": "true" }),
      h("div", { class: "tl-body" },
        h("div", { class: "tl-head" }, badge(EVENT_TONE[ev.Type] || "info", EVENT_LABEL[ev.Type] || ev.Type),
          h("span", { class: "faint", title: dateTime(ev.Timestamp) }, dateTime(ev.Timestamp))),
        (ev.Recipients || []).length ? h("div", { class: "muted" }, (ev.Recipients || []).join(", ")) : null,
        details.length ? h("dl", { class: "tl-details" }, details.map(([k, v]) => [
          h("dt", {}, k), h("dd", { class: "mono" }, typeof v === "object" ? JSON.stringify(v) : String(v))])) : null));
  }));
}

function headersTable(headers) {
  return table({
    title: "Headers",
    filter: { placeholder: "Find headers", match: (r, t) => `${r.Name}: ${r.Value}`.toLowerCase().includes(t) },
    columns: [
      { id: "n", header: "Name", cell: (r) => h("span", { class: "mono" }, r.Name) },
      { id: "v", header: "Value", wrap: true, cell: (r) => h("span", { class: "mono" }, r.Value) },
    ],
    items: headers,
    empty: h("div", { class: "table-empty" }, "No headers."),
  }).el;
}

function attachmentsTable(list) {
  return table({
    title: "Attachments",
    description: "Download the raw message (Raw tab) to get the files.",
    columns: [
      { id: "f", header: "File name", wrap: true, cell: (a) => a.FileName || h("span", { class: "faint" }, "(no name)") },
      { id: "t", header: "Content type", cell: (a) => h("span", { class: "mono" }, a.ContentType) },
      { id: "d", header: "Disposition", cell: (a) => (a.Disposition || "").toLowerCase() },
      { id: "s", header: "Size", cell: (a) => bytes(a.Size) },
      { id: "c", header: "Content ID", wrap: true, cell: (a) => (a.ContentId ? h("span", { class: "mono" }, a.ContentId) : h("span", { class: "faint" }, "-")) },
    ],
    items: list,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No attachments")),
  }).el;
}

function rawTab(id) {
  const box = h("div", {}, h("div", { class: "table-empty" }, h("span", { class: "spinner" }), " Loading the raw message…"));
  const me = pageId();
  call("GetMessage", { MessageId: id, IncludeRaw: true }).then((out) => {
    if (me !== pageId()) return;
    const raw = out.Raw || "";
    const download = button("Download .eml", {
      icon: "download",
      onClick: () => {
        const url = URL.createObjectURL(new Blob([raw], { type: "message/rfc822" }));
        const a = h("a", { href: url, download: `${id}.eml` });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
    });
    box.replaceChildren(container({
      title: "Raw message",
      description: raw.length >= 5 * 1024 * 1024 ? "Only the first 5 MB are shown." : "The MIME source as stored (DKIM-signed when a key applies).",
      actions: [download],
    }, codeBox(raw, "Copy raw message")));
  }).catch((err) => {
    if (me !== pageId()) return;
    box.replaceChildren(alert("error", "Couldn't load the raw message", err.text || err.message));
  });
  return box;
}
