// Configuration sets: the list, "Create configuration set" (TLS policy, maximum delivery time, suppression override,
// tags) and a set's page (sending on/off, delivery and suppression options, event destinations).

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { navigate, pageId, paths } from "../core/router.js";
import { alert } from "../components/alert.js";
import { chip } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { container } from "../components/container.js";
import { flash } from "../components/flash.js";
import { checkbox, formField, input, select } from "../components/form-field.js";
import { keyValue } from "../components/key-value.js";
import { confirm, modal } from "../components/modal.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { tagEditor } from "../components/tag-editor.js";
import { toggle } from "../components/toggle.js";
import { enabledBadge, loadingPanel } from "./common.js";
import { renderNotFound } from "./not-found.js";
import { keepFlash, showPage } from "./shell.js";

const root = { label: "Amazon SES", href: "#/account" };
const list = { label: "Configuration sets", href: "#/configuration-sets" };

export const EVENT_TYPES = [
  ["SEND", "Sends"], ["DELIVERY", "Deliveries"], ["BOUNCE", "Hard bounces"], ["COMPLAINT", "Complaints"],
  ["REJECT", "Rejects"], ["DELIVERY_DELAY", "Delivery delays"], ["RENDERING_FAILURE", "Rendering failures"],
  ["OPEN", "Opens"], ["CLICK", "Clicks"], ["SUBSCRIPTION", "Subscriptions"],
];

export function renderConfigSets() {
  const me = pageId();
  const t = table({
    title: "Configuration sets",
    description: "Rules applied to the mail you send with a set: TLS policy, maximum delivery time, suppression and event destinations.",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Create set", { variant: "primary", onClick: () => navigate("/configuration-sets/create") }),
    ],
    filter: { placeholder: "Find configuration sets", match: (r, text) => r.toLowerCase().includes(text) },
    columns: [
      { id: "name", header: "Name", wrap: true, sort: (r) => r.toLowerCase(), cell: (r) => h("a", { href: `#${paths.configSet(r)}` }, r) },
    ],
    trackBy: (r) => r,
    pageSize: 50,
    loading: true,
    empty: () => h("div", { class: "table-empty" }, h("b", {}, "No configuration sets"), "Create one to apply rules to the mail you send.",
      h("div", {}, button("Create set", { onClick: () => navigate("/configuration-sets/create") }))),
  });
  async function load() {
    t.setLoading(true);
    try {
      const out = await call("ListConfigurationSets", { PageSize: 1000 });
      if (me === pageId()) t.setItems(out.ConfigurationSets || []);
    } catch (err) {
      t.setItems([]);
      if (err.status !== 401) flash.error("Couldn't load the configuration sets", err);
    }
  }
  showPage(breadcrumbs([root, { label: "Configuration sets" }]), pageHeader({ title: "Configuration sets" }), t.el);
  load();
}

function suppressionChoice(current) {
  // current: undefined (use the account's list) or an array of reasons.
  const override = checkbox("Override the account-level suppression settings", { checked: Array.isArray(current) });
  const bounce = checkbox("Bounce", { checked: Array.isArray(current) && current.includes("BOUNCE") });
  const complaint = checkbox("Complaint", { checked: Array.isArray(current) && current.includes("COMPLAINT") });
  const reasons = h("div", { class: "stack indent" },
    h("div", { class: "muted" }, "Suppress recipients on the account's list for these reasons (none: don't suppress for this set)."),
    bounce.el, complaint.el);
  reasons.hidden = !override.box.checked;
  override.box.addEventListener("change", () => { reasons.hidden = !override.box.checked; });
  return {
    el: h("div", { class: "stack" }, override.el, reasons),
    value: () => (override.box.checked
      ? [bounce.box.checked && "BOUNCE", complaint.box.checked && "COMPLAINT"].filter(Boolean) : undefined),
  };
}

export function renderCreateConfigSet() {
  const name = formField({ label: "Configuration set name", constraint: "Up to 64 characters: letters, digits, _ and -.", control: input({ maxlength: "64" }) });
  const tls = formField({
    label: "Transport Layer Security (TLS)",
    description: "Require: refuse delivery to a server that can't do TLS. Optional: use TLS when the server offers it.",
    control: select([{ value: "OPTIONAL", label: "Optional", selected: true }, { value: "REQUIRE", label: "Require" }]),
  });
  const maxSeconds = formField({
    label: "Maximum delivery time (seconds)",
    optional: true,
    description: "How long delivery is retried before the message bounces.",
    constraint: "300 to 50400 seconds (5 minutes to 14 hours). Empty: the server's retry period.",
    control: input({ type: "number", min: "300", max: "50400", inputmode: "numeric" }),
  });
  const sending = toggle("Sending enabled", { checked: true });
  const suppression = suppressionChoice(undefined);
  const tags = tagEditor([]);
  const error = h("div", { class: "f-error", role: "alert" });

  const submit = button("Create set", {
    variant: "primary",
    onClick: async () => {
      error.textContent = "";
      name.setError("");
      maxSeconds.setError("");
      const n = name.control.value.trim();
      if (!/^[A-Za-z0-9_-]{1,64}$/.test(n)) {
        name.setError("Use 1 to 64 letters, digits, _ or -.");
        name.control.focus();
        return;
      }
      const params = { ConfigurationSetName: n, DeliveryOptions: { TlsPolicy: tls.control.value }, SendingOptions: { SendingEnabled: sending.box.checked } };
      if (maxSeconds.control.value) {
        const s = Number(maxSeconds.control.value);
        if (!Number.isInteger(s) || s < 300 || s > 50400) {
          maxSeconds.setError("Enter a whole number from 300 to 50400.");
          return;
        }
        params.DeliveryOptions.MaxDeliverySeconds = s;
      }
      const reasons = suppression.value();
      if (reasons !== undefined) params.SuppressionOptions = { SuppressedReasons: reasons };
      try {
        params.Tags = tags.value();
        await call("CreateConfigurationSet", params);
        keepFlash();
        flash.success(`The configuration set ${n} was created.`);
        navigate(paths.configSet(n));
      } catch (err) {
        error.textContent = err.text || err.message;
      }
    },
  });

  showPage(
    breadcrumbs([root, list, { label: "Create set" }]),
    pageHeader({ title: "Create configuration set" }),
    container({ title: "General details" }, h("div", { class: "stack" }, name.el, sending.el)),
    container({ title: "Delivery options" }, h("div", { class: "form-grid" }, tls.el, maxSeconds.el)),
    container({ title: "Suppression list settings" }, suppression.el),
    container({ title: "Tags", description: "Optional labels." }, tags.el),
    h("div", { class: "form-actions" }, error, h("div", { class: "btn-group" },
      button("Cancel", { variant: "link", onClick: () => navigate("/configuration-sets") }), submit)));
}

export async function renderConfigSet(name) {
  const crumbs = breadcrumbs([root, list, { label: name }]);
  showPage(crumbs, pageHeader({ title: name }), loadingPanel());
  const me = pageId();
  let cs;
  let dests;
  try {
    [cs, dests] = await Promise.all([
      call("GetConfigurationSet", { ConfigurationSetName: name }),
      call("GetConfigurationSetEventDestinations", { ConfigurationSetName: name }).then((o) => o.EventDestinations || []),
    ]);
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status === 404) renderNotFound(`The configuration set ${name} doesn't exist. It may have been deleted.`);
    else if (err.status !== 401) {
      flash.error(`Couldn't load ${name}`, err);
      showPage(crumbs, pageHeader({ title: name }));
    }
    return;
  }
  if (me !== pageId()) return;
  const reload = () => renderConfigSet(name);
  const sendingOn = (cs.SendingOptions || {}).SendingEnabled !== false;
  const delivery = cs.DeliveryOptions || {};
  const supp = cs.SuppressionOptions;

  const sw = toggle("Sending enabled", {
    checked: sendingOn,
    onChange: async (on) => {
      sw.box.disabled = true;
      try {
        await call("PutConfigurationSetSendingOptions", { ConfigurationSetName: name, SendingEnabled: on });
        flash.success(on ? `Sending with ${name} is enabled.` : `Sending with ${name} is paused.`);
        reload();
      } catch (err) {
        sw.box.checked = !on;
        sw.box.disabled = false;
        flash.error("Couldn't change the sending status", err);
      }
    },
  });

  const del = button("Delete", {
    danger: true,
    onClick: () => confirm({
      title: `Delete ${name}?`,
      message: "Messages sent with this configuration set name will be refused once it is deleted.",
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        await call("DeleteConfigurationSet", { ConfigurationSetName: name });
        keepFlash();
        flash.success(`The configuration set ${name} was deleted.`);
        navigate("/configuration-sets");
      },
    }),
  });

  const overview = container({ title: "Overview", actions: [button("Edit options", { onClick: () => editOptions(name, cs, reload) })] }, keyValue([
    [{ label: "Configuration set name", value: name, copy: name },
      { label: "Sending", value: enabledBadge(sendingOn, "Enabled", "Paused") }],
    [{ label: "TLS policy", value: delivery.TlsPolicy === "REQUIRE" ? "Require" : "Optional" },
      { label: "Maximum delivery time", value: delivery.MaxDeliverySeconds ? `${delivery.MaxDeliverySeconds} seconds` : "Server default" }],
    [{ label: "Suppression list", value: supp ? (supp.SuppressedReasons.length ? `Overridden: ${supp.SuppressedReasons.join(", ")}` : "Overridden: no suppression") : "Account-level settings" },
      { label: "Tags", value: (cs.Tags || []).length ? h("div", {}, cs.Tags.map((t) => chip(`${t.Key}=${t.Value}`))) : null }],
  ]), h("div", { style: "margin-top:16px" }, sw.el));

  const destTable = table({
    title: "Event destinations",
    description: "Where events for messages sent with this set go. This server keeps every event on the message (Messages page) "
      + "and POSTs them to SES_EVENTS_URL when set; SNS / Firehose / CloudWatch targets are stored but not called.",
    actions: [button("Add destination", { variant: "primary", onClick: () => addDestination(name, reload) })],
    columns: [
      { id: "name", header: "Name", wrap: true, cell: (d) => d.Name },
      { id: "enabled", header: "Status", cell: (d) => enabledBadge(d.Enabled) },
      { id: "types", header: "Event types", wrap: true, cell: (d) => h("div", {}, (d.MatchingEventTypes || []).map((t) => chip(t))) },
      { id: "target", header: "Target", cell: (d) => targetOf(d) },
      {
        id: "x", header: "", cell: (d) => button("Delete", {
          variant: "inline",
          onClick: () => confirm({
            title: `Delete ${d.Name}?`, message: "Events stop going to this destination.", confirmLabel: "Delete", danger: true,
            onConfirm: async () => {
              await call("DeleteConfigurationSetEventDestination", { ConfigurationSetName: name, EventDestinationName: d.Name });
              flash.success(`The event destination ${d.Name} was deleted.`);
              reload();
            },
          }),
        }),
      },
    ],
    items: dests,
    trackBy: (d) => d.Name,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No event destinations")),
  });

  showPage(crumbs, pageHeader({ title: name, extra: enabledBadge(sendingOn, "Sending enabled", "Sending paused"), actions: [del] }),
    sendingOn ? null : alert("warning", "Sending is paused for this configuration set", "Messages that name it are refused."),
    overview, destTable.el);
}

function targetOf(d) {
  for (const [key, label] of [["SnsDestination", "SNS"], ["EventBridgeDestination", "EventBridge"], ["KinesisFirehoseDestination", "Firehose"],
    ["CloudWatchDestination", "CloudWatch"], ["PinpointDestination", "Pinpoint"]]) {
    if (d[key]) return label;
  }
  return h("span", { class: "faint" }, "Message events only");
}

function editOptions(name, cs, reload) {
  const delivery = cs.DeliveryOptions || {};
  const tls = formField({
    label: "TLS policy",
    control: select([{ value: "OPTIONAL", label: "Optional", selected: delivery.TlsPolicy !== "REQUIRE" }, { value: "REQUIRE", label: "Require", selected: delivery.TlsPolicy === "REQUIRE" }]),
  });
  const maxSeconds = formField({
    label: "Maximum delivery time (seconds)", optional: true, constraint: "300 to 50400.",
    control: input({ type: "number", min: "300", max: "50400", value: delivery.MaxDeliverySeconds ? String(delivery.MaxDeliverySeconds) : "" }),
  });
  const suppression = suppressionChoice(cs.SuppressionOptions ? cs.SuppressionOptions.SuppressedReasons : undefined);
  const error = h("div", { class: "f-error", role: "alert" });
  let m;
  m = modal({
    title: "Edit options",
    body: [tls.el, maxSeconds.el, h("div", { class: "field" }, h("span", { class: "f-label" }, "Suppression list"), suppression.el), h("div", { class: "field" }, error)],
    footer: [
      button("Cancel", { variant: "link", onClick: () => m.close() }),
      button("Save", {
        variant: "primary",
        onClick: async () => {
          error.textContent = "";
          const params = { ConfigurationSetName: name, TlsPolicy: tls.control.value };
          if (maxSeconds.control.value) {
            const s = Number(maxSeconds.control.value);
            if (!Number.isInteger(s) || s < 300 || s > 50400) {
              maxSeconds.setError("Enter a whole number from 300 to 50400.");
              return;
            }
            params.MaxDeliverySeconds = s;
          }
          try {
            await call("PutConfigurationSetDeliveryOptions", params);
            const reasons = suppression.value();
            await call("PutConfigurationSetSuppressionOptions", reasons === undefined
              ? { ConfigurationSetName: name } : { ConfigurationSetName: name, SuppressedReasons: reasons });
            m.close();
            flash.success(`The options of ${name} were saved.`);
            reload();
          } catch (err) {
            error.textContent = err.text || err.message;
          }
        },
      }),
    ],
  });
}

function addDestination(name, reload) {
  const destName = formField({ label: "Name", constraint: "Letters, digits, _ and -.", control: input({ maxlength: "64" }) });
  const enabled = checkbox("Enabled", { checked: true });
  const boxes = EVENT_TYPES.map(([id, label]) => ({ id, ...checkbox(label, { checked: ["SEND", "DELIVERY", "BOUNCE", "COMPLAINT"].includes(id) }) }));
  const error = h("div", { class: "f-error", role: "alert" });
  let m;
  m = modal({
    title: "Add event destination",
    body: [
      destName.el,
      enabled.el,
      h("fieldset", { class: "checks" }, h("legend", {}, "Event types"), h("div", { class: "check-grid" }, boxes.map((b) => b.el))),
      h("div", { class: "field" }, error),
    ],
    footer: [
      button("Cancel", { variant: "link", onClick: () => m.close() }),
      button("Add", {
        variant: "primary",
        onClick: async () => {
          error.textContent = "";
          destName.setError("");
          const n = destName.control.value.trim();
          if (!/^[A-Za-z0-9_-]{1,64}$/.test(n)) {
            destName.setError("Use 1 to 64 letters, digits, _ or -.");
            return;
          }
          const types = boxes.filter((b) => b.box.checked).map((b) => b.id);
          if (!types.length) {
            error.textContent = "Choose at least one event type.";
            return;
          }
          try {
            await call("CreateConfigurationSetEventDestination", {
              ConfigurationSetName: name, EventDestinationName: n,
              EventDestination: { Enabled: enabled.box.checked, MatchingEventTypes: types },
            });
            m.close();
            flash.success(`The event destination ${n} was added.`);
            reload();
          } catch (err) {
            error.textContent = err.text || err.message;
          }
        },
      }),
    ],
  });
}
