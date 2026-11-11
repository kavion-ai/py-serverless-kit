// The bucket's Management tab: lifecycle rules (table, create, edit, enable/disable, delete) and "Run lifecycle now".

import { h } from "../core/dom.js";
import { api, errorText } from "../core/api.js";
import { navigate, reload } from "../core/router.js";
import { plural } from "../core/format.js";
import { lifecycleFromXml, lifecycleToXml, ruleSummary } from "../core/s3.js";
import { container, emptyState } from "../components/container.js";
import { table } from "../components/table.js";
import { button, busy } from "../components/button.js";
import { dropdown } from "../components/dropdown.js";
import { badge } from "../components/badge.js";
import { confirmModal } from "../components/modal.js";
import { flash } from "../components/toast.js";
import { bucketPath } from "./common.js";

/** Save the whole lifecycle configuration (an empty list deletes it). */
export async function saveLifecycle(bucket, rules) {
  return api("PutBucketSetting", { bucket, setting: "lifecycle", value: lifecycleToXml(rules) });
}

export async function renderManagementTab({ bucket, info, body }) {
  const rules = lifecycleFromXml(info.configs.lifecycle);
  let selected = null;
  const editBtn = button({ label: "Edit", disabled: true, onClick: () => navigate(bucketPath(bucket, "/lifecycle/edit"), { id: selected.id }) });
  const deleteBtn = button({
    label: "Delete",
    disabled: true,
    onClick: async () => {
      const rule = selected;
      const ok = await confirmModal({
        title: "Delete lifecycle rule",
        message: `Delete the lifecycle rule "${rule.id}"? Objects it would have expired or transitioned are no longer affected.`,
        confirmLabel: "Delete",
        variant: "danger",
        typed: "delete",
      });
      if (!ok) return;
      try {
        await saveLifecycle(bucket, rules.filter((r) => r !== rule));
        flash("success", "", { title: `Successfully deleted lifecycle rule "${rule.id}"` });
        reload();
      } catch (e) {
        flash("error", errorText(e), { title: "Could not delete the lifecycle rule" });
      }
    },
  });
  const setStatus = async (status) => {
    const rule = selected;
    try {
      await saveLifecycle(
        bucket,
        rules.map((r) => (r === rule ? { ...r, status } : r)),
      );
      flash("success", "", { title: `Lifecycle rule "${rule.id}" ${status === "Enabled" ? "enabled" : "disabled"}` });
      reload();
    } catch (e) {
      flash("error", errorText(e), { title: "Could not change the lifecycle rule" });
    }
  };
  const actions = dropdown({
    label: "Actions",
    disabled: true,
    items: () => [
      { label: "Enable rule", disabled: !selected || selected.status === "Enabled", onClick: () => setStatus("Enabled") },
      { label: "Disable rule", disabled: !selected || selected.status !== "Enabled", onClick: () => setStatus("Disabled") },
    ],
  });
  const runBtn = button({ label: "Run lifecycle now", title: "Apply every bucket's lifecycle rules once, now (the server also runs them on a schedule)" });
  runBtn.addEventListener("click", () =>
    busy(runBtn, async () => {
      try {
        const r = await api("RunLifecycle");
        flash("success", "", { title: `Lifecycle rules applied: ${plural(r.changes || 0, "change")}` });
      } catch (e) {
        flash("error", errorText(e), { title: "Could not run the lifecycle rules" });
      }
    }),
  );

  const tbl = table({
    ariaLabel: "Lifecycle rules",
    selectable: "single",
    rowKey: (r) => r.id,
    pageSize: 25,
    filter: { placeholder: "Find lifecycle rules", match: (r, q) => r.id.toLowerCase().includes(q) },
    onSelect: (list) => {
      selected = list[0] || null;
      editBtn.disabled = deleteBtn.disabled = !selected;
      actions.setDisabled(!selected);
    },
    columns: [
      { id: "id", header: "Lifecycle rule name", sortValue: (r) => r.id, cell: (r) => h("span", { class: "strong" }, r.id) },
      { id: "status", header: "Status", cell: (r) => (r.status === "Enabled" ? badge("success", "Enabled") : badge("stopped", "Disabled")) },
      { id: "scope", header: "Scope", cell: (r) => ruleSummary(r).scope + (r.filtered && r.prefix ? ` (prefix ${r.prefix})` : "") },
      { id: "current", header: "Current version actions", cell: (r) => ruleSummary(r).current },
      { id: "noncurrent", header: "Noncurrent versions actions", cell: (r) => ruleSummary(r).noncurrent },
      { id: "markers", header: "Expired object delete markers", cell: (r) => ruleSummary(r).markers },
      { id: "mpu", header: "Incomplete multipart uploads", cell: (r) => ruleSummary(r).multipart },
    ],
    rows: rules,
    empty: () =>
      emptyState({
        title: "No lifecycle rules",
        text: "There are no lifecycle rules for this bucket.",
        action: button({ label: "Create lifecycle rule", onClick: () => navigate(bucketPath(bucket, "/lifecycle/create")) }),
      }),
  });

  body.replaceChildren(
    h(
      "div",
      { class: "stack" },
      container(
        {
          title: "Lifecycle rules",
          counter: rules.length,
          description: "Use lifecycle rules to define actions you want the server to take during an object's lifetime, such as transitioning objects to another storage class, expiring them, or deleting noncurrent versions. Rules run automatically on a schedule.",
          actions: [editBtn, deleteBtn, actions, button({ label: "Create lifecycle rule", variant: "primary", onClick: () => navigate(bucketPath(bucket, "/lifecycle/create")) })],
        },
        tbl.el,
        h("div", { class: "btn-row btn-row--end muted small" }, runBtn),
      ),
    ),
  );
}
