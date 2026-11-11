// Versions tab: every version (ListSecretVersionIds with deprecated ones), its staging labels, and
// "View value" / "Make current" (moves AWSCURRENT; the old current version becomes AWSPREVIOUS).

import { call } from "../../core/api.js";
import { h } from "../../core/dom.js";
import { dateTime } from "../../core/format.js";
import { chip } from "../../components/badge.js";
import { button } from "../../components/button.js";
import { flash } from "../../components/flash.js";
import { confirm } from "../../components/modal.js";
import { table } from "../../components/table.js";
import { showVersionValue } from "./value-panel.js";

export function versionsTab(secret, { onChange } = {}) {
  const deleted = Boolean(secret.DeletedDate);
  let rows = [];

  const viewBtn = button("View value", { disabled: true, onClick: () => showVersionValue(secret, t.selected().VersionId) });
  const currentBtn = button("Make current", { disabled: true, onClick: () => makeCurrent(t.selected()) });

  const t = table({
    title: "Versions",
    description: "Up to 100 versions are kept. A version without a staging label is deprecated.",
    actions: deleted ? [] : [viewBtn, currentBtn],
    selection: deleted ? null : "single",
    onSelect: (row) => {
      viewBtn.disabled = !row;
      currentBtn.disabled = !row || row.VersionStages.includes("AWSCURRENT");
    },
    columns: [
      { id: "id", header: "Version ID", wrap: true, cell: (v) => h("span", { class: "mono" }, v.VersionId) },
      {
        id: "stages", header: "Staging labels",
        cell: (v) => (v.VersionStages.length ? v.VersionStages.map((s) => chip(s, { accent: s === "AWSCURRENT" }))
          : h("span", { class: "faint" }, "Deprecated")),
      },
      { id: "created", header: "Created on", sort: (v) => v.CreatedDate, cell: (v) => dateTime(v.CreatedDate) },
    ],
    trackBy: (v) => v.VersionId,
    pageSize: 20,
    loading: true,
    empty: h("div", { class: "table-empty" }, h("b", {}, "No versions"), "This secret has no value yet."),
  });

  async function load() {
    try {
      const out = await call("ListSecretVersionIds", { SecretId: secret.Name, IncludeDeprecated: true, MaxResults: 100 });
      rows = out.Versions || [];
      t.setItems(rows);
    } catch (err) {
      t.setItems([]);
      flash.error("Couldn't list the versions", err);
    }
  }

  function makeCurrent(row) {
    const holder = rows.find((v) => v.VersionStages.includes("AWSCURRENT"));
    confirm({
      title: "Make this version current?",
      message: `Version ${row.VersionId} becomes AWSCURRENT: applications read it from now on. `
        + `${holder ? `The current version (${holder.VersionId}) becomes AWSPREVIOUS.` : ""}`,
      confirmLabel: "Make current",
      onConfirm: async () => {
        const params = { SecretId: secret.Name, VersionStage: "AWSCURRENT", MoveToVersionId: row.VersionId };
        if (holder) params.RemoveFromVersionId = holder.VersionId;
        await call("UpdateSecretVersionStage", params);
        flash.success("The version is now AWSCURRENT.");
        if (onChange) onChange();
      },
    });
  }

  load();
  return t.el;
}
