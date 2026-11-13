// Identities: the list (ListEmailIdentities, following NextToken) and the "Create identity" page.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { navigate, pageId, paths } from "../core/router.js";
import { alert } from "../components/alert.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { checkbox, formField, input, textarea } from "../components/form-field.js";
import { pageHeader } from "../components/page-header.js";
import { segmented } from "../components/segmented.js";
import { table } from "../components/table.js";
import { IDENTITY_TYPE, serverInfo, verificationStatus } from "./common.js";
import { keepFlash, showPage } from "./shell.js";

/** Every identity (all pages). */
export async function listAllIdentities() {
  const out = [];
  let token;
  do {
    const page = await call("ListEmailIdentities", { PageSize: 1000, ...(token ? { NextToken: token } : {}) });
    out.push(...(page.EmailIdentities || []));
    token = page.NextToken;
  } while (token);
  return out;
}

export function renderIdentities() {
  const me = pageId();
  const t = table({
    title: "Identities",
    description: "Domains and email addresses you send from. A message's From address must be a verified identity "
      + "(an address is also allowed when its domain is verified).",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Create identity", { variant: "primary", onClick: () => navigate("/identities/create") }),
    ],
    filter: { placeholder: "Find identities", match: (r, text) => r.IdentityName.toLowerCase().includes(text) },
    columns: [
      { id: "name", header: "Identity", wrap: true, sort: (r) => r.IdentityName, cell: (r) => h("a", { href: `#${paths.identity(r.IdentityName)}` }, r.IdentityName) },
      { id: "type", header: "Identity type", sort: (r) => r.IdentityType, cell: (r) => IDENTITY_TYPE[r.IdentityType] || r.IdentityType },
      { id: "status", header: "Identity status", sort: (r) => r.VerificationStatus, cell: (r) => verificationStatus(r.VerificationStatus) },
      {
        id: "send", header: "", cell: (r) => (r.VerificationStatus === "SUCCESS" && r.IdentityType === "EMAIL_ADDRESS"
          ? h("a", { href: `#${paths.send(r.IdentityName)}` }, "Send test email") : ""),
      },
    ],
    trackBy: (r) => r.IdentityName,
    pageSize: 50,
    loading: true,
    empty: () => h("div", { class: "table-empty" }, h("b", {}, "No identities"),
      "Verify a domain or an email address to start sending.",
      h("div", {}, button("Create identity", { onClick: () => navigate("/identities/create") }))),
  });

  async function load() {
    t.setLoading(true);
    try {
      const items = await listAllIdentities();
      if (me === pageId()) t.setItems(items);
    } catch (err) {
      t.setItems([]);
      if (err.status !== 401) flash.error("Couldn't load the identities", err);
    }
  }

  showPage(
    breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Identities" }]),
    pageHeader({ title: "Verified identities" }),
    t.el);
  load();
}

export function renderCreateIdentity() {
  let kind = "DOMAIN";
  const typeSwitch = segmented([{ id: "DOMAIN", label: "Domain" }, { id: "EMAIL_ADDRESS", label: "Email address" }], {
    selected: kind, label: "Identity type", onChange: (v) => { kind = v; drawKind(); },
  });

  const domain = formField({
    label: "Domain",
    description: "A domain you own, such as example.com. All its addresses (and those of its subdomains) can send once it is verified.",
    control: input({ placeholder: "example.com", maxlength: "253", autocapitalize: "off" }),
  });
  const email = formField({
    label: "Email address",
    description: "The address you send from, such as noreply@example.com.",
    control: input({ type: "email", placeholder: "noreply@example.com", maxlength: "320", autocapitalize: "off" }),
  });

  const byo = checkbox("Use your own DKIM key (Bring Your Own DKIM)");
  const selector = formField({
    label: "Selector name",
    description: "The DKIM selector your public key is published under (<selector>._domainkey.<domain>).",
    control: input({ placeholder: "mail", maxlength: "63" }),
  });
  const key = formField({
    label: "Private key",
    description: "Your RSA private key: PEM (PKCS#1 or PKCS#8) or the base64 body only. It stays on this server.",
    control: textarea({ rows: 8, placeholder: "-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----", autocomplete: "off" }),
  });
  const byoBox = h("div", { class: "stack indent" }, selector.el, key.el);
  byoBox.hidden = true;
  byo.box.addEventListener("change", () => { byoBox.hidden = !byo.box.checked; });
  const dkimBlock = container({
    title: "Advanced DKIM settings",
    description: "By default this server generates a 2048-bit key (Easy DKIM) and shows the TXT record to publish.",
  }, h("div", { class: "stack" }, byo.el, byoBox));

  const note = h("div");
  serverInfo().then((info) => {
    if (info.Verify === "auto" || info.Verify === "off") {
      note.replaceChildren(alert("info", "Identities are verified at once",
        `The server's verify mode is "${info.Verify}", so a new identity can send right away. `
        + "Domains still get DNS records (DKIM, SPF, DMARC) to publish so receivers accept their mail."));
    } else if (info.Verify === "dns") {
      note.replaceChildren(alert("info", "Domains verify through DNS",
        "Publish the records shown on the identity page; the server checks them and marks the domain verified. "
        + "Email addresses are marked verified by an administrator here."));
    } else {
      note.replaceChildren(alert("info", "Identities are verified by hand",
        "After creating it, use \"Mark as verified\" on the identity page."));
    }
  }).catch(() => {});

  const body = h("div", { class: "stack" });
  function drawKind() {
    body.replaceChildren(kind === "DOMAIN" ? domain.el : email.el);
    dkimBlock.hidden = kind !== "DOMAIN";
  }
  drawKind();

  const error = h("div", { class: "f-error", role: "alert" });
  const submit = button("Create identity", {
    variant: "primary",
    onClick: async () => {
      error.textContent = "";
      domain.setError("");
      email.setError("");
      selector.setError("");
      key.setError("");
      const field = kind === "DOMAIN" ? domain : email;
      const name = field.control.value.trim().replace(/\.$/, "");
      if (!name) {
        field.setError(kind === "DOMAIN" ? "Enter a domain." : "Enter an email address.");
        field.control.focus();
        return;
      }
      if (kind === "DOMAIN" && name.includes("@")) {
        field.setError("A domain has no @. Choose Email address to verify one address.");
        return;
      }
      if (kind === "EMAIL_ADDRESS" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(name)) {
        field.setError("Enter an address such as name@example.com.");
        return;
      }
      const params = { EmailIdentity: name };
      if (kind === "DOMAIN" && byo.box.checked) {
        const sel = selector.control.value.trim();
        const pem = key.control.value.trim();
        if (!sel) {
          selector.setError("Enter the selector.");
          return;
        }
        if (!pem) {
          key.setError("Paste the private key.");
          return;
        }
        params.DkimSigningAttributes = { DomainSigningSelector: sel, DomainSigningPrivateKey: pem };
      }
      try {
        await call("CreateEmailIdentity", params);
        keepFlash();
        flash.success(`The identity ${name} was created.`,
          kind === "DOMAIN" ? "Publish the DNS records below so receivers trust its mail." : undefined);
        // The server keeps domains in lower case and an address's local part as typed.
        const key = kind === "DOMAIN" ? name.toLowerCase() : name.replace(/@([^@]*)$/, (_m, d) => `@${d.toLowerCase()}`);
        navigate(paths.identity(key, kind === "DOMAIN" ? "dns" : undefined));
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });

  showPage(
    breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Identities", href: "#/identities" }, { label: "Create identity" }]),
    pageHeader({ title: "Create identity", description: "An identity is a domain or an email address you send mail from." }),
    note,
    container({ title: "Identity details" },
      h("div", { class: "stack" },
        h("div", { class: "field" }, h("span", { class: "f-label" }, "Identity type"), h("div", {}, typeSwitch.el)),
        body)),
    dkimBlock,
    h("div", { class: "form-actions" }, error,
      h("div", { class: "btn-group" }, button("Cancel", { variant: "link", onClick: () => navigate("/identities") }), submit)));
}
