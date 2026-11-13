// The account-level suppression list: which reasons add addresses to it automatically (BOUNCE / COMPLAINT), and the
// suppressed addresses (filter, add, remove).

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { dateTime, relative } from "../core/format.js";
import { pageId } from "../core/router.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { checkbox, formField, input, select } from "../components/form-field.js";
import { confirm, modal } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { badge } from "../components/badge.js";
import { showPage } from "./shell.js";

const REASON = { BOUNCE: ["error", "Bounce"], COMPLAINT: ["warning", "Complaint"] };

export function renderSuppression() {
  const me = pageId();
  const bounce = checkbox("Bounce");
  const complaint = checkbox("Complaint");
  const settingsError = h("div", { class: "f-error", role: "alert" });
  const saveSettings = button("Save", {
    variant: "primary",
    onClick: async () => {
      settingsError.textContent = "";
      const reasons = [bounce.box.checked && "BOUNCE", complaint.box.checked && "COMPLAINT"].filter(Boolean);
      try {
        await call("PutAccountSuppressionAttributes", { SuppressedReasons: reasons });
        flash.success("The suppression settings were saved.", reasons.length ? `Addresses are added for: ${reasons.join(", ").toLowerCase()}.` : "No address is added automatically.");
      } catch (err) {
        settingsError.textContent = err.text || err.message;
      }
    },
  });
  const settings = container({
    title: "Account-level suppression list settings",
    description: "Recipients whose mail bounces hard or who complain are added to the list for these reasons, and later "
      + "messages to them are not sent (a Bounce event with the OnAccountSuppressionList subtype). A configuration set can override this.",
    actions: [saveSettings],
  }, h("div", { class: "stack" }, h("div", { class: "row", style: "gap:24px" }, bounce.el, complaint.el), settingsError));

  let reasonFilter = "";
  const reasonSel = select([{ value: "", label: "Any reason" }, { value: "BOUNCE", label: "Bounce" }, { value: "COMPLAINT", label: "Complaint" }],
    { "aria-label": "Filter by reason", class: "inline-select" });
  reasonSel.addEventListener("change", () => {
    reasonFilter = reasonSel.value;
    load();
  });

  const t = table({
    title: "Suppressed addresses",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Add email address", { variant: "primary", onClick: () => addAddress(load) }),
    ],
    filter: { placeholder: "Find addresses", match: (r, text) => r.EmailAddress.toLowerCase().includes(text) },
    tools: [reasonSel],
    columns: [
      { id: "addr", header: "Email address", wrap: true, sort: (r) => r.EmailAddress.toLowerCase(), cell: (r) => r.EmailAddress },
      {
        id: "reason", header: "Reason", sort: (r) => r.Reason,
        cell: (r) => { const [type, label] = REASON[r.Reason] || ["info", r.Reason]; return badge(type, label); },
      },
      { id: "time", header: "Last updated", sort: (r) => r.LastUpdateTime || 0, cell: (r) => h("span", { title: dateTime(r.LastUpdateTime) }, relative(r.LastUpdateTime)) },
      {
        id: "x", header: "", cell: (r) => button("Remove", {
          variant: "inline",
          onClick: () => confirm({
            title: `Remove ${r.EmailAddress}?`,
            message: "Mail to this address will be sent again.",
            confirmLabel: "Remove",
            onConfirm: async () => {
              await call("DeleteSuppressedDestination", { EmailAddress: r.EmailAddress });
              flash.success(`${r.EmailAddress} was removed from the suppression list.`);
              load();
            },
          }),
        }),
      },
    ],
    trackBy: (r) => r.EmailAddress.toLowerCase(),
    pageSize: 50,
    loading: true,
    empty: () => h("div", { class: "table-empty" }, h("b", {}, "No suppressed addresses"),
      reasonFilter ? "No address is suppressed for this reason." : "The suppression list is empty."),
  });

  async function load() {
    t.setLoading(true);
    try {
      const out = [];
      let token;
      do {
        const page = await call("ListSuppressedDestinations", { PageSize: 1000, ...(reasonFilter ? { Reasons: [reasonFilter] } : {}), ...(token ? { NextToken: token } : {}) });
        out.push(...(page.SuppressedDestinationSummaries || []));
        token = page.NextToken;
      } while (token);
      if (me === pageId()) t.setItems(out);
    } catch (err) {
      t.setItems([]);
      if (err.status !== 401) flash.error("Couldn't load the suppression list", err);
    }
  }

  showPage(
    breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Suppression list" }]),
    pageHeader({ title: "Suppression list" }),
    settings,
    t.el);

  call("GetAccount").then((acct) => {
    if (me !== pageId()) return;
    const reasons = (acct.SuppressionAttributes || {}).SuppressedReasons || [];
    bounce.box.checked = reasons.includes("BOUNCE");
    complaint.box.checked = reasons.includes("COMPLAINT");
  }).catch((err) => {
    if (err.status !== 401) flash.error("Couldn't load the suppression settings", err);
  });
  load();
}

function addAddress(onDone) {
  const addr = formField({ label: "Email address", control: input({ type: "email", placeholder: "user@example.com" }) });
  const reason = formField({ label: "Reason", control: select([{ value: "BOUNCE", label: "Bounce" }, { value: "COMPLAINT", label: "Complaint" }]) });
  let m;
  m = modal({
    title: "Add email address",
    body: [addr.el, reason.el],
    footer: [
      button("Cancel", { variant: "link", onClick: () => m.close() }),
      button("Add", {
        variant: "primary",
        onClick: async () => {
          addr.setError("");
          const value = addr.control.value.trim();
          if (!value.includes("@")) {
            addr.setError("Enter an email address.");
            return;
          }
          try {
            await call("PutSuppressedDestination", { EmailAddress: value, Reason: reason.control.value });
            m.close();
            flash.success(`${value} was added to the suppression list.`);
            onDone();
          } catch (err) {
            addr.setError(err.text || err.message);
          }
        },
      }),
    ],
  });
}
