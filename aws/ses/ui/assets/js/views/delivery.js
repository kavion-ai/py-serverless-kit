// Delivery settings: how accepted mail leaves the server. Capture (keep it), Relay (through a smarthost such as
// Microsoft 365 or SendGrid) or Direct (to the recipients' MX hosts). Test connection tries the form's settings
// without saving; Save applies them at once; Reset goes back to the server's environment settings.
// The relay password is never sent back by the server: an empty password field keeps the saved one.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { pageId } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { formField, input, select } from "../components/form-field.js";
import { keyValue } from "../components/key-value.js";
import { confirm } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { toggle } from "../components/toggle.js";
import { DELIVERY_LABEL, loadingPanel, refreshServerInfo } from "./common.js";
import { showPage } from "./shell.js";

const MODES = [
  { id: "capture", title: "Capture", text: "Keep every message on this server and send nothing. For development and testing." },
  { id: "relay", title: "Relay / smarthost", text: "Send through your mail provider: Microsoft 365, Google Workspace, SendGrid or your own Postfix." },
  { id: "direct", title: "Direct", text: "Deliver straight to each recipient's mail servers (MX), like a mail server of its own." },
];

const PRESETS = [
  { id: "custom", label: "Custom" },
  { id: "m365", label: "Microsoft 365", host: "smtp.office365.com", port: 587, tls: "starttls",
    note: "Sign in with a licensed mailbox; SMTP AUTH must be enabled for it in the Microsoft 365 admin center." },
  { id: "google", label: "Google Workspace / Gmail", host: "smtp.gmail.com", port: 587, tls: "starttls",
    note: "Use an app password (Google account > Security > App passwords), not the account password." },
  { id: "sendgrid", label: "SendGrid", host: "smtp.sendgrid.net", port: 587, tls: "starttls", user: "apikey",
    note: "The user name is literally \"apikey\"; the password is your SendGrid API key." },
  { id: "ses", label: "Amazon SES SMTP", host: "email-smtp.us-east-1.amazonaws.com", port: 587, tls: "starttls",
    note: "Use SES SMTP credentials (not access keys) and change the region in the host name if needed." },
  { id: "mailgun", label: "Mailgun", host: "smtp.mailgun.org", port: 587, tls: "starttls",
    note: "Use the SMTP credentials of your Mailgun domain." },
];

const MODE_NAME = { capture: "Capture", relay: "Relay", direct: "Direct" };
const TLS_LABEL = { starttls: "STARTTLS", tls: "TLS (implicit, usually port 465)", none: "None" };

export async function renderDelivery() {
  const crumbs = breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Delivery settings" }]);
  const header = pageHeader({ title: "Delivery settings", description: "Choose how the mail this server accepts is delivered." });
  showPage(crumbs, header, loadingPanel());
  const me = pageId();
  let conf;
  try {
    conf = await call("GetDeliverySettings");
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status !== 401) flash.error("Couldn't load the delivery settings", err);
    showPage(crumbs, header);
    return;
  }
  if (me !== pageId()) return;
  draw(crumbs, header, conf);
}

function draw(crumbs, header, conf) {
  let mode = conf.Mode || "capture";
  const env = conf.Environment || {};

  // ---- mode tiles (radio group)
  const tiles = h("div", { class: "tiles", role: "radiogroup", "aria-label": "Delivery mode" });
  const drawTiles = () => tiles.replaceChildren(...MODES.map((m) => {
    const radio = h("input", {
      type: "radio", name: "delivery-mode", value: m.id, checked: m.id === mode,
      onchange: () => { mode = m.id; drawTiles(); drawMode(); },
    });
    return h("label", { class: ["tile", m.id === mode && "on"] }, radio,
      h("div", {}, h("b", {}, m.title, m.id === conf.Mode ? h("span", { class: "tile-current" }, " (in use)") : null), h("span", {}, m.text)));
  }));
  drawTiles();

  // ---- relay fields
  const preset = formField({
    label: "Provider",
    description: "Fills the host, port and TLS for a known provider.",
    control: select(PRESETS.map((p) => ({ value: p.id, label: p.label, selected: p.host === conf.RelayHost }))),
  });
  const presetNote = h("div");
  const host = formField({ label: "SMTP host", control: input({ value: conf.RelayHost || "", placeholder: "smtp.example.com" }) });
  const port = formField({ label: "Port", control: input({ type: "number", min: "1", max: "65535", value: String(conf.RelayPort || 587), inputmode: "numeric" }) });
  const tls = formField({
    label: "Encryption",
    control: select(["starttls", "tls", "none"].map((t) => ({ value: t, label: TLS_LABEL[t], selected: (conf.RelayTls || "starttls") === t }))),
  });
  const verify = toggle("Verify the relay's TLS certificate", { checked: conf.RelayTlsVerify !== false });
  const user = formField({ label: "User name", optional: true, control: input({ value: conf.RelayUser || "", autocomplete: "off" }) });
  const password = formField({
    label: "Password",
    optional: true,
    description: conf.RelayPasswordSet ? "A password is saved. Leave empty to keep it (as long as host and user stay the same)." : undefined,
    control: input({ type: "password", autocomplete: "new-password", placeholder: conf.RelayPasswordSet ? "saved — leave empty to keep" : "" }),
  });
  const drawPresetNote = () => {
    const p = PRESETS.find((x) => x.id === preset.control.value);
    presetNote.replaceChildren(p && p.note ? alert("info", p.label, p.note) : "");
  };
  preset.control.addEventListener("change", () => {
    const p = PRESETS.find((x) => x.id === preset.control.value);
    if (p && p.host) {
      host.control.value = p.host;
      port.control.value = String(p.port);
      tls.control.value = p.tls;
      if (p.user) user.control.value = p.user;
    }
    drawPresetNote();
  });
  drawPresetNote();

  const relayBox = container({ title: "Relay (smarthost)", description: "The SMTP server that sends the mail for you." },
    h("div", { class: "stack" },
      h("div", { class: "form-grid" }, preset.el),
      presetNote,
      h("div", { class: "form-grid" }, host.el, port.el, tls.el),
      verify.el,
      h("div", { class: "form-grid" }, user.el, password.el)));

  const directWarn = alert("warning", "Direct delivery needs a real mail-server setup",
    h("ul", { class: "tight-list" },
      h("li", {}, `Outbound TCP port ${conf.DirectPort || 25} must be open. Most clouds (AWS, Azure, GCP) and home ISPs block it.`),
      h("li", {}, "A public IP address whose reverse DNS (PTR) matches the HELO name below."),
      h("li", {}, "SPF, DKIM and DMARC records for your sending domains (see each identity's DNS records)."),
      h("li", {}, "Without these, mail is refused or lands in spam: a relay is usually the better choice.")));
  const testDomain = formField({
    label: "Test domain", optional: true,
    description: "Test connection looks up this domain's MX hosts and connects to them (nothing is sent).",
    control: input({ value: "gmail.com" }),
  });
  const directBox = container({ title: "Direct delivery" }, h("div", { class: "stack" }, directWarn, h("div", { class: "form-grid" }, testDomain.el)));

  const helo = formField({
    label: "HELO name",
    description: "The host name this server announces when it connects (EHLO). Use a name that resolves to this server.",
    control: input({ value: conf.HeloName || "", placeholder: "mail.example.com" }),
  });
  const heloBox = container({ title: "Server identity" }, h("div", { class: "form-grid" }, helo.el));

  const captureBox = alert("info", "Capture mode keeps mail on this server",
    "Messages are stored and shown under Messages, marked delivered; nothing is sent. Mailbox simulator addresses still behave as on SES.");

  function drawMode() {
    relayBox.hidden = mode !== "relay";
    directBox.hidden = mode !== "direct";
    heloBox.hidden = mode === "capture";
    captureBox.hidden = mode !== "capture";
  }
  drawMode();

  // ---- actions
  const result = h("div", { "aria-live": "polite" });
  const error = h("div", { class: "f-error", role: "alert" });

  function params() {
    const out = { Mode: mode };
    if (mode !== "capture" && helo.control.value.trim()) out.HeloName = helo.control.value.trim();
    if (mode === "relay") {
      Object.assign(out, {
        RelayHost: host.control.value.trim(),
        RelayPort: Number(port.control.value) || 587,
        RelayTls: tls.control.value,
        RelayTlsVerify: verify.box.checked,
        RelayUser: user.control.value.trim(),
      });
      if (password.control.value) out.RelayPassword = password.control.value;
    }
    return out;
  }

  function validate() {
    [host, port, user, password].forEach((f) => f.setError(""));
    if (mode !== "relay") return true;
    if (!host.control.value.trim()) {
      host.setError("Enter the relay's host name.");
      host.control.focus();
      return false;
    }
    const p = Number(port.control.value);
    if (!Number.isInteger(p) || p < 1 || p > 65535) {
      port.setError("Enter a port from 1 to 65535.");
      return false;
    }
    if (user.control.value.trim() && tls.control.value === "none") {
      user.setError("A login needs STARTTLS or TLS: the password would cross the network in plain text.");
      return false;
    }
    return true;
  }

  const test = button("Test connection", {
    onClick: async () => {
      error.textContent = "";
      if (!validate()) return;
      const body = params();
      if (mode === "direct" && testDomain.control.value.trim()) body.TestDomain = testDomain.control.value.trim();
      result.replaceChildren(alert("info", "Testing the connection…", h("span", { class: "row" }, h("span", { class: "spinner", "aria-hidden": "true" }),
        mode === "capture" ? "Checking." : "This can take up to a minute when a host doesn't answer.")));
      try {
        const out = await call("TestDeliverySettings", body);
        const steps = (out.Steps || []).length ? h("ol", { class: "steps-list" }, out.Steps.map((s) => h("li", { class: "mono" }, s))) : null;
        result.replaceChildren(alert(out.Ok ? "success" : "error", out.Ok ? "Connection test passed" : "Connection test failed", out.Message || "", steps));
      } catch (err) {
        result.replaceChildren(alert("error", "The test couldn't run", err.text || err.message));
      }
    },
  });

  const save = button("Save", {
    variant: "primary",
    onClick: async () => {
      error.textContent = "";
      result.replaceChildren();
      if (!validate()) return;
      try {
        const out = await call("PutDeliverySettings", params());
        flash.success(`Delivery mode is now ${MODE_NAME[out.Mode] || out.Mode}.`, "Queued and delayed messages are retried with the new settings.");
        refreshServerInfo();
        draw(crumbs, header, out);
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });

  const reset = conf.Source === "console" ? button("Reset to server default", {
    variant: "link",
    onClick: () => {
      confirm({
        title: "Reset to the server's settings?",
        message: h("div", { class: "stack" },
          h("p", { style: "margin:0" }, "The settings saved in the console are forgotten and the server goes back to the ones it was started with:"),
          keyValue([[{ label: "Mode", value: DELIVERY_LABEL[env.Mode] || env.Mode }],
            env.Mode === "relay" ? [{ label: "Relay", value: `${env.RelayHost}:${env.RelayPort} (${env.RelayTls})`, mono: true }] : []])),
        confirmLabel: "Reset",
        onConfirm: async () => {
          const out = await call("ResetDeliverySettings", {});
          flash.success(`Delivery mode is now ${MODE_NAME[out.Mode] || out.Mode} (server default).`);
          refreshServerInfo();
          draw(crumbs, header, out);
        },
      });
      return undefined;
    },
  }) : null;

  const current = container({ title: "Current setting" }, keyValue([
    [{ label: "Delivery mode", value: DELIVERY_LABEL[conf.Mode] || conf.Mode }],
    [{ label: "Set by", value: conf.Source === "console" ? badge("info", "This console (saved on the server)") : badge("stopped", "Server environment (SES_DELIVERY)") }],
    [{ label: "Server default", value: DELIVERY_LABEL[env.Mode] || env.Mode || "-" }],
  ]));

  showPage(crumbs, header, current,
    container({ title: "Delivery mode" }, tiles),
    captureBox, relayBox, directBox, heloBox,
    result,
    h("div", { class: "form-actions" }, error, h("div", { class: "btn-group" }, reset, test, save)));
}
