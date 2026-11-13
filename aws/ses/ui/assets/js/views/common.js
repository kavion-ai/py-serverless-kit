// Helpers shared by the views: status badges, the server's settings (cached), loading placeholders and the SES
// mailbox simulator addresses.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { emit } from "../core/state.js";
import { badge } from "../components/badge.js";
import { container } from "../components/container.js";

let infoPromise = null;

/** GetServerInfo, cached for the console's lifetime; refreshServerInfo() asks again (after the delivery mode changes). */
export function serverInfo() {
  if (!infoPromise) {
    infoPromise = call("GetServerInfo").catch((err) => {
      infoPromise = null;
      throw err;
    });
  }
  return infoPromise;
}

export function forgetServerInfo() {
  infoPromise = null;
}

/** Ask the server again and tell listeners ("server-info": the side navigation's boxes). */
export function refreshServerInfo() {
  infoPromise = null;
  const p = serverInfo();
  p.then((info) => emit("server-info", info)).catch(() => {});
  return p;
}

/** A link to the Delivery settings page. */
export function deliveryLink(label = "Change delivery mode") {
  return h("a", { href: "#/delivery" }, label);
}

export const DELIVERY_LABEL = {
  capture: "Capture (mail is kept, not sent)",
  relay: "Relay (through an SMTP server)",
  direct: "Direct (to the recipients' MX hosts)",
};

export const VERIFY_LABEL = {
  auto: "auto (identities are verified at once)",
  dns: "dns (domains verify when their DNS records are found)",
  manual: "manual (mark identities verified here)",
  off: "off (any From address may send)",
};

const MESSAGE_STATUS = {
  QUEUED: ["pending", "Queued"],
  SENDING: ["pending", "Sending"],
  DELAYED: ["warning", "Delayed"],
  DELIVERED: ["success", "Delivered"],
  BOUNCED: ["error", "Bounced"],
  PARTIAL: ["warning", "Partially delivered"],
  SUPPRESSED: ["stopped", "Suppressed"],
};

export const MESSAGE_STATUSES = ["QUEUED", "SENDING", "DELAYED", "DELIVERED", "BOUNCED", "PARTIAL"];

export function messageStatus(status) {
  const [type, label] = MESSAGE_STATUS[status] || ["info", status || "Unknown"];
  return badge(type, label);
}

const VERIFICATION = {
  SUCCESS: ["success", "Verified"],
  PENDING: ["pending", "Verification pending"],
  FAILED: ["error", "Failed"],
  TEMPORARY_FAILURE: ["warning", "Temporary failure"],
  NOT_STARTED: ["stopped", "Not started"],
};

export function verificationStatus(status, labels = {}) {
  const [type, label] = VERIFICATION[status] || ["info", status || "-"];
  return badge(type, labels[status] || label);
}

export function enabledBadge(on, yes = "Enabled", no = "Disabled") {
  return on ? badge("success", yes) : badge("stopped", no);
}

export function loadingPanel(text = "Loading…") {
  return container({}, h("div", { class: "table-empty" }, h("span", { class: "spinner" }), ` ${text}`));
}

export const SIMULATOR = [
  { address: "success@simulator.amazonses.com", label: "Delivered" },
  { address: "bounce@simulator.amazonses.com", label: "Bounce" },
  { address: "complaint@simulator.amazonses.com", label: "Complaint" },
  { address: "ooto@simulator.amazonses.com", label: "Out of office" },
  { address: "suppressionlist@simulator.amazonses.com", label: "On suppression list" },
];

/** "a@x.com, b@y.com" or newlines -> ["a@x.com", "b@y.com"]. */
export function splitAddresses(text) {
  return String(text || "").split(/[,;\n]+/).map((s) => s.trim()).filter(Boolean);
}

export const IDENTITY_TYPE = { DOMAIN: "Domain", EMAIL_ADDRESS: "Email address", MANAGED_DOMAIN: "Managed domain" };
