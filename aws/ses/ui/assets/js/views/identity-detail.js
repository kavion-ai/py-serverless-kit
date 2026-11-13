// One identity: summary, the DNS records to publish (with "Check DNS now"), "Mark as verified / unverified",
// DKIM signing, the custom MAIL FROM domain, tags, and delete (typed confirmation).

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { dateTime, relative } from "../core/format.js";
import { navigate, pageId, paths, setQuery } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { copyButton } from "../components/copy-button.js";
import { dropdown } from "../components/dropdown.js";
import { flash } from "../components/flash.js";
import { formField, input, select } from "../components/form-field.js";
import { keyValue } from "../components/key-value.js";
import { modal } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { tabs } from "../components/tabs.js";
import { toggle } from "../components/toggle.js";
import { enabledBadge, IDENTITY_TYPE, loadingPanel, serverInfo, verificationStatus } from "./common.js";
import { renderNotFound } from "./not-found.js";
import { keepFlash, showPage } from "./shell.js";

const crumbs = (name) => breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Identities", href: "#/identities" }, { label: name }]);

export async function renderIdentity(name, tab) {
  showPage(crumbs(name), pageHeader({ title: name }), loadingPanel());
  const me = pageId();
  let identity;
  let records = [];
  let info = {};
  try {
    [identity, records, info] = await Promise.all([
      call("GetEmailIdentity", { EmailIdentity: name }),
      call("GetEmailIdentityDnsRecords", { EmailIdentity: name }).then((o) => o.Records || []),
      serverInfo().catch(() => ({})),
    ]);
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status === 404 || err.code === "NotFoundException") renderNotFound(`The identity ${name} doesn't exist. It may have been deleted.`);
    else if (err.status !== 401) {
      flash.error(`Couldn't load ${name}`, err);
      showPage(crumbs(name), pageHeader({ title: name }));
    }
    return;
  }
  if (me !== pageId()) return;
  draw(name, identity, records, info, tab);
}

function draw(name, identity, records, info, tab) {
  const reload = (nextTab) => renderIdentity(name, nextTab === undefined ? tab : nextTab);
  const isDomain = identity.IdentityType === "DOMAIN";
  const verified = identity.VerificationStatus === "SUCCESS";
  const vinfo = identity.VerificationInfo || {};
  const dkim = identity.DkimAttributes || {};

  const setVerified = async (value) => {
    try {
      await call("SetEmailIdentityVerified", { EmailIdentity: name, Verified: value });
      flash.success(value ? `${name} is marked as verified.` : `${name} is marked as not verified.`);
      reload();
    } catch (err) {
      flash.error("Couldn't change the verification status", err);
    }
  };
  const checkDns = async () => {
    try {
      const out = await call("CheckEmailIdentity", { EmailIdentity: name });
      const ok = out.VerificationStatus === "SUCCESS";
      const dk = (out.DkimAttributes || {}).Status;
      const err = (out.VerificationInfo || {}).ErrorType;
      if (ok || dk === "SUCCESS") flash.success(`DNS checked for ${name}.`, `Verification: ${out.VerificationStatus}. DKIM: ${dk || "-"}.`);
      else flash.warning(`The records of ${name} weren't found yet.`, `Verification: ${out.VerificationStatus}. DKIM: ${dk || "-"}${err ? `. Lookup result: ${err}` : ""}. DNS changes can take a while to propagate.`);
      reload();
    } catch (err) {
      flash.error("Couldn't check DNS", err);
    }
  };

  const actions = [
    verified && !isDomain ? button("Send test email", { icon: "send", onClick: () => navigate(paths.send(name)) }) : null,
    isDomain ? button("Check DNS now", { icon: "refresh", onClick: checkDns }) : null,
    dropdown("Actions", [
      verified ? { label: "Mark as not verified", onSelect: () => setVerified(false) } : { label: "Mark as verified", onSelect: () => setVerified(true) },
      isDomain ? { label: "Send test email…", onSelect: () => navigate(paths.send(`noreply@${name}`)) } : null,
      { label: "Delete identity", onSelect: () => openDelete(name) },
    ]),
  ].filter(Boolean);

  let banner = null;
  if (!verified && (info.Verify === "manual" || !isDomain)) {
    banner = alert("info", "This identity is not verified yet",
      info.Verify === "manual"
        ? "The server's verify mode is manual: mark the identity as verified when you trust it."
        : isDomain ? "Publish the DNS records below." : "An address is verified when its domain is verified, or when you mark it verified here.",
      h("div", { style: "margin-top:8px" }, button("Mark as verified", { variant: "primary", onClick: () => setVerified(true) })));
  } else if (!verified && isDomain) {
    banner = alert("info", "Verification pending",
      "Publish the TXT records below at your DNS provider. The server looks them up every 10 minutes for 72 hours; "
      + "use Check DNS now after publishing.",
      h("div", { style: "margin-top:8px" }, button("Mark as verified anyway", { onClick: () => setVerified(true) })));
  }

  const summary = container({ title: "Summary" }, keyValue([
    [{ label: "Identity", value: name, copy: name },
      { label: "Identity type", value: IDENTITY_TYPE[identity.IdentityType] || identity.IdentityType }],
    [{ label: "Identity status", value: verificationStatus(identity.VerificationStatus) },
      { label: "Verified for sending", value: identity.VerifiedForSendingStatus ? badge("success", "Yes") : badge("stopped", "No") }],
    [{ label: "Last checked", value: vinfo.LastCheckedTimestamp ? h("span", { title: dateTime(vinfo.LastCheckedTimestamp) }, relative(vinfo.LastCheckedTimestamp)) : null },
      { label: "Last verified", value: vinfo.LastSuccessTimestamp ? dateTime(vinfo.LastSuccessTimestamp) : null }],
    [{ label: "DKIM", value: verificationStatus(dkim.Status, { SUCCESS: "Successful" }) },
      { label: "Default configuration set", value: identity.ConfigurationSetName || null }],
  ]),
  vinfo.ErrorType && isDomain && (!verified || dkim.Status !== "SUCCESS") ? h("div", { style: "margin-top:16px" }, alert("warning", "Last DNS lookup", `Result: ${vinfo.ErrorType}`)) : null);

  const items = [];
  if (isDomain) items.push({ id: "dns", label: "DNS records", render: () => dnsTab(name, records, checkDns) });
  items.push({ id: "auth", label: "Authentication", render: () => authTab(name, identity, reload) });
  items.push({ id: "tags", label: "Tags", render: () => tagsTab(identity) });

  showPage(
    crumbs(name),
    pageHeader({ title: name, extra: verificationStatus(identity.VerificationStatus), actions }),
    banner,
    summary,
    tabs(items, { selected: tab || items[0].id, onChange: (id) => { tab = id; setQuery({ tab: id === items[0].id ? null : id }); } }));
}

function dnsTab(name, records, checkDns) {
  const t = table({
    title: "DNS records",
    description: `Publish these records at the DNS provider of ${name}. Copy each value exactly.`,
    actions: [button("Check DNS now", { icon: "refresh", onClick: checkDns })],
    columns: [
      { id: "purpose", header: "Purpose", cell: (r) => r.Purpose },
      { id: "type", header: "Type", cell: (r) => h("span", { class: "mono" }, r.Type) },
      { id: "name", header: "Name", wrap: true, cell: (r) => h("div", { class: "copy-cell" }, h("span", { class: "mono" }, r.Name), copyButton(r.Name, { label: `Copy name of the ${r.Purpose} record` })) },
      { id: "value", header: "Value", wrap: true, cell: (r) => h("div", { class: "copy-cell" }, h("span", { class: "mono dns-value" }, r.Value), copyButton(r.Value, { label: `Copy value of the ${r.Purpose} record` })) },
      { id: "status", header: "Status", cell: (r) => (r.Status ? verificationStatus(r.Status) : h("span", { class: "faint" }, "Recommended")) },
    ],
    items: records,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No DNS records"), "This identity needs none."),
  });
  return h("div", { class: "stack" }, t.el);
}

function authTab(name, identity, reload) {
  const isDomain = identity.IdentityType === "DOMAIN";
  const dkim = identity.DkimAttributes || {};
  const mf = identity.MailFromAttributes || {};

  let dkimControl;
  if (isDomain && dkim.Status !== "NOT_STARTED") {
    const sw = toggle("DKIM signatures", {
      checked: Boolean(dkim.SigningEnabled),
      onChange: async (on) => {
        sw.box.disabled = true;
        try {
          await call("PutEmailIdentityDkimAttributes", { EmailIdentity: name, SigningEnabled: on });
          flash.success(on ? `DKIM signing enabled for ${name}.` : `DKIM signing disabled for ${name}.`);
          reload("auth");
        } catch (err) {
          sw.box.checked = !on;
          sw.box.disabled = false;
          flash.error("Couldn't change DKIM signing", err);
        }
      },
    });
    dkimControl = sw.el;
  } else if (!isDomain) {
    dkimControl = h("div", { class: "muted" }, dkim.Status === "NOT_STARTED"
      ? "Mail from this address is signed when its domain is a verified identity with DKIM."
      : "This address uses the DKIM key of its domain identity.");
  }

  const dkimPanel = container({
    title: "DomainKeys Identified Mail (DKIM)",
    description: "Mail is signed once the DKIM record is found in DNS and signing is enabled.",
  },
  keyValue([
    [{ label: "DKIM configuration", value: verificationStatus(dkim.Status, { SUCCESS: "Successful" }) },
      { label: "DKIM signatures", value: enabledBadge(dkim.SigningEnabled) }],
    [{ label: "Key origin", value: dkim.SigningAttributesOrigin === "EXTERNAL" ? "Provided by you (BYODKIM)" : dkim.SigningAttributesOrigin ? "Easy DKIM (generated by the server)" : null },
      { label: "Key length", value: dkim.CurrentSigningKeyLength || null }],
    [{ label: "Selector", value: (dkim.Tokens || [])[0] || null, mono: true },
      { label: "Key generated", value: dkim.LastKeyGenerationTimestamp ? dateTime(dkim.LastKeyGenerationTimestamp) : null }],
  ]),
  dkimControl ? h("div", { style: "margin-top:16px" }, dkimControl) : null);

  const parent = name.includes("@") ? name.slice(name.lastIndexOf("@") + 1) : name;
  const domain = formField({
    label: "MAIL FROM domain",
    description: `A subdomain of ${parent}, such as mail.${parent}. Leave empty to use the default.`,
    optional: true,
    control: input({ value: mf.MailFromDomain || "", placeholder: `mail.${parent}` }),
  });
  const behavior = formField({
    label: "Behavior on MX failure",
    description: "What to do when the MAIL FROM domain's MX record is missing.",
    control: select([
      { value: "USE_DEFAULT_VALUE", label: "Use default MAIL FROM domain", selected: mf.BehaviorOnMxFailure !== "REJECT_MESSAGE" },
      { value: "REJECT_MESSAGE", label: "Reject message", selected: mf.BehaviorOnMxFailure === "REJECT_MESSAGE" },
    ]),
  });
  const save = button("Save MAIL FROM", {
    variant: "primary",
    onClick: async () => {
      domain.setError("");
      const value = domain.control.value.trim().toLowerCase();
      if (value && !value.endsWith(`.${parent}`)) {
        domain.setError(`Enter a subdomain of ${parent}.`);
        return;
      }
      try {
        await call("PutEmailIdentityMailFromAttributes", { EmailIdentity: name, MailFromDomain: value, BehaviorOnMxFailure: behavior.control.value });
        flash.success(value ? `The MAIL FROM domain of ${name} is ${value}.` : `The custom MAIL FROM domain of ${name} was removed.`);
        reload("auth");
      } catch (err) {
        domain.setError(err.text || err.message);
      }
    },
  });
  const mailFrom = container({
    title: "Custom MAIL FROM domain",
    description: "The envelope sender (Return-Path) domain. Publish the MX and SPF records shown under DNS records.",
  },
  mf.MailFromDomain ? h("div", { style: "margin-bottom:16px" }, keyValue([[{ label: "Status", value: verificationStatus(mf.MailFromDomainStatus) }]])) : null,
  h("div", { class: "form-grid" }, domain.el, behavior.el),
  h("div", { class: "row", style: "margin-top:16px" }, save));

  return h("div", { class: "stack" }, dkimPanel, mailFrom);
}

function tagsTab(identity) {
  const tags = identity.Tags || [];
  return table({
    title: "Tags",
    description: "Tags are set with the TagResource API.",
    columns: [
      { id: "k", header: "Key", wrap: true, cell: (t) => t.Key },
      { id: "v", header: "Value", wrap: true, cell: (t) => t.Value || h("span", { class: "faint" }, "-") },
    ],
    items: tags,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No tags"), "This identity has no tags."),
  }).el;
}

function openDelete(name) {
  const field = formField({ label: `To confirm, type ${name}`, control: input({ placeholder: name, "aria-label": "Identity to confirm" }) });
  let m;
  const ok = button("Delete", {
    variant: "primary",
    danger: true,
    onClick: async () => {
      field.setError("");
      if (field.control.value.trim() !== name) {
        field.setError("The identity doesn't match.");
        field.control.focus();
        return;
      }
      try {
        await call("DeleteEmailIdentity", { EmailIdentity: name });
        m.close();
        keepFlash();
        flash.success(`The identity ${name} was deleted.`);
        navigate("/identities");
      } catch (err) {
        field.setError(err.text || err.message);
      }
    },
  });
  m = modal({
    title: `Delete ${name}?`,
    body: [
      alert("warning", "Mail from this identity will be refused",
        "Deleting the identity removes its verification and DKIM key. Sending from it fails until you create and verify it again."),
      field.el,
    ],
    footer: [button("Cancel", { variant: "link", onClick: () => m.close() }), ok],
  });
}
