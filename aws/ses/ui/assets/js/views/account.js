// Account dashboard: sending status (pause / resume), sandbox or production, the sending quota, the delivery mode,
// 14 days of sending statistics (CSS bars) and resource counts.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { number } from "../core/format.js";
import { navigate, pageId } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { button } from "../components/button.js";
import { barChart, meter, statTile } from "../components/charts.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { keyValue } from "../components/key-value.js";
import { confirm } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { segmented } from "../components/segmented.js";
import { DELIVERY_LABEL, loadingPanel, MESSAGE_STATUSES, messageStatus, serverInfo, VERIFY_LABEL } from "./common.js";
import { showPage } from "./shell.js";

const SERIES = [
  { key: "Sent", label: "Sent", cls: "sent" },
  { key: "Delivered", label: "Delivered", cls: "delivered" },
  { key: "Bounced", label: "Bounces", cls: "bounced" },
  { key: "Complaints", label: "Complaints", cls: "complaints" },
];

let statsView = "chart";

export async function renderAccount() {
  const header = pageHeader({
    title: "Account dashboard",
    description: "Your sending status, quota and recent sending activity on this Amazon SES compatible server.",
    actions: [button("Refresh", { variant: "icon", icon: "refresh", onClick: () => renderAccount() }),
      button("Send test email", { variant: "primary", icon: "send", onClick: () => navigate("/send") })],
  });
  showPage(header, loadingPanel());
  const me = pageId();
  let stats;
  let info;
  try {
    [stats, info] = await Promise.all([call("GetStatistics", { Days: 14 }), serverInfo()]);
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status !== 401) flash.error("Couldn't load the account", err);
    showPage(header);
    return;
  }
  if (me !== pageId()) return;
  showPage(header, ...draw(stats, info));
}

function deliveryBanner(info) {
  if (info.Delivery === "capture") {
    return alert("warning", "Capture mode: mail is kept, not sent",
      "Every accepted message is stored on this server and marked delivered, but nothing leaves it. "
      + "Read captured messages under Messages. Set SES_DELIVERY=relay or direct to really send mail.",
      h("div", { style: "margin-top:8px" }, button("View messages", { onClick: () => navigate("/messages") })));
  }
  if (info.Delivery === "relay") {
    const relay = info.Relay || {};
    return alert("info", "Relay mode: mail is sent through an SMTP relay",
      `Messages are handed to ${relay.Host || "the relay"}:${relay.Port || ""} (${relay.Tls || "starttls"}`
      + `${relay.User ? `, as ${relay.User}` : ""}).`);
  }
  return alert("info", "Direct mode: mail is sent straight to the recipients' mail servers",
    `This server looks up each recipient domain's MX hosts and connects on port ${info.DirectPort || 25} as `
    + `${info.HeloName || "this host"}. Publish SPF and DKIM records for your domains so the mail is accepted.`);
}

function draw(stats, info) {
  const account = stats.Account || {};
  const quota = account.SendQuota || {};
  const sending = account.SendingEnabled !== false;
  const sent = Number(quota.SentLast24Hours) || 0;
  const max = Number(quota.Max24HourSend) || 0;

  const toggleSending = button(sending ? "Pause sending" : "Resume sending", {
    danger: sending,
    onClick: () => {
      if (!sending) return setSending(true);
      confirm({
        title: "Pause sending for the account?",
        message: "SendEmail, SendRawEmail and SMTP calls are refused (SendingPausedException) until you resume sending. "
          + "Messages already queued are still delivered.",
        confirmLabel: "Pause sending",
        danger: true,
        onConfirm: () => setSending(false),
      });
      return undefined;
    },
  });

  const status = container({ title: "Account status", actions: [toggleSending] }, keyValue([
    [{ label: "Sending status", value: sending ? badge("success", "Enabled") : badge("error", "Paused") },
      { label: "Enforcement status", value: badge("success", account.EnforcementStatus === "HEALTHY" ? "Healthy" : (account.EnforcementStatus || "-")) }],
    [{ label: "Account type", value: account.ProductionAccessEnabled ? badge("success", "Production") : badge("warning", "Sandbox") },
      { label: "Region", value: info.Region }],
    [{ label: "Delivery mode", value: DELIVERY_LABEL[info.Delivery] || info.Delivery },
      { label: "Identity verification", value: VERIFY_LABEL[info.Verify] || info.Verify }],
    [{ label: "Message retention", value: `${number(info.RetentionDays)} days` },
      { label: "Server version", value: `${info.Version || "-"} (${info.Implementation || "-"})` }],
  ]));

  const quotaPanel = container({ title: "Sending quota", description: "Recipients count against the quota (as on SES)." },
    h("div", { class: "stats" },
      statTile({ label: "Sent in the last 24 hours", value: number(sent), detail: `of ${number(max)} (${max ? ((sent / max) * 100).toFixed(1) : 0}%)` }),
      statTile({ label: "Daily sending quota", value: number(max), detail: `${number(Math.max(0, max - sent))} remaining` }),
      statTile({ label: "Maximum send rate", value: `${number(quota.MaxSendRate)}`, detail: "messages per second" })),
    h("div", { style: "margin-top:16px" }, meter({ value: sent, max, label: "Daily quota used" })));

  const days = stats.Days || [];
  const totals = SERIES.map((s) => ({ ...s, total: days.reduce((n, d) => n + (Number(d[s.key]) || 0), 0) }));
  const statsBody = h("div");
  const drawStats = () => {
    statsBody.replaceChildren(statsView === "chart" ? barChart(days, SERIES) : statsTable(days));
  };
  const switcher = segmented([{ id: "chart", label: "Chart" }, { id: "table", label: "Table" }], {
    selected: statsView, label: "Statistics view", onChange: (v) => { statsView = v; drawStats(); },
  });
  drawStats();
  const statsPanel = container({
    title: "Sending statistics",
    description: "Recipients per day (UTC) over the last 14 days.",
    actions: [switcher.el],
  },
  h("div", { class: "stats" }, totals.map((t) => statTile({ label: t.label, value: number(t.total), tone: t.cls }))),
  h("div", { style: "margin-top:16px" }, statsBody));

  const counts = stats.Counts || {};
  const byStatus = stats.MessagesByStatus || {};
  const resource = (label, value, href) => h("a", { class: "stat link-tile", href },
    h("div", { class: "stat-label" }, label), h("div", { class: "stat-value" }, number(value)));
  const resources = container({ title: "Resources" },
    h("div", { class: "stats" },
      resource("Identities", counts.Identities, "#/identities"),
      resource("Templates", counts.Templates, "#/templates"),
      resource("Configuration sets", counts.ConfigurationSets, "#/configuration-sets"),
      resource("Suppressed addresses", counts.Suppressed, "#/suppression"),
      resource("Messages kept", counts.Messages, "#/messages")),
    h("div", { class: "status-row" }, MESSAGE_STATUSES.map((st) => h("a", { class: "status-chip", href: `#/messages?status=${st}` },
      messageStatus(st), h("b", {}, number(byStatus[st] || 0))))));

  return [
    deliveryBanner(info),
    account.ProductionAccessEnabled ? null : alert("info", "This account is in the sandbox",
      "You can send only to verified identities and to the mailbox simulator (…@simulator.amazonses.com). "
      + "Start the server with SES_SANDBOX=off for production access."),
    sending ? null : alert("error", "Sending is paused", "The account refuses new messages until you resume sending."),
    status, quotaPanel, statsPanel, resources,
  ];
}

function statsTable(days) {
  const rows = [...days].reverse().map((d) => {
    const day = new Date(d.Date * 1000).toISOString().slice(0, 10);
    return h("tr", {}, h("td", {}, day), ["Sent", "Delivered", "Bounced", "Complaints", "Rejected", "Delayed"]
      .map((k) => h("td", { class: "num" }, number(d[k]))));
  });
  return h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
    h("thead", {}, h("tr", {}, ["Date (UTC)", "Sent", "Delivered", "Bounces", "Complaints", "Rejected", "Delayed"]
      .map((t, i) => h("th", { scope: "col", class: i ? "num" : undefined }, t)))),
    h("tbody", {}, rows)));
}

async function setSending(enabled) {
  try {
    await call("PutAccountSendingAttributes", { SendingEnabled: enabled });
    flash.success(enabled ? "Sending resumed for the account." : "Sending paused for the account.");
    renderAccount();
  } catch (err) {
    flash.error("Couldn't change the sending status", err);
    throw err;
  }
}
