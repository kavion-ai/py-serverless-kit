// General purpose buckets: account snapshot + the bucket table (Copy ARN, Empty, Delete, Create bucket).

import { h } from "../core/dom.js";
import { state } from "../core/state.js";
import { errorText } from "../core/api.js";
import { formatDate } from "../core/format.js";
import { bucketArn, accessOf, ACCESS_TEXT } from "../core/s3.js";
import { navigate } from "../core/router.js";
import { table } from "../components/table.js";
import { button, iconButton, link } from "../components/button.js";
import { container, emptyState } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { copyWithToast } from "../components/copy-button.js";
import { errorSlot } from "../components/alert.js";
import { setPage, refreshBuckets } from "./shell.js";
import { accessBadge, bucketHref, bucketPath, rootCrumbs } from "./common.js";

export async function render(ctx) {
  const errors = errorSlot();
  let selected = null;
  const snapshot = h("div", { class: "snapshot" });

  const copyArn = button({ label: "Copy ARN", icon: "copy", disabled: true, onClick: () => selected && copyWithToast(bucketArn(selected.name), "ARN copied") });
  const empty = button({ label: "Empty", disabled: true, onClick: () => selected && navigate(bucketPath(selected.name, "/empty")) });
  const del = button({ label: "Delete", disabled: true, onClick: () => selected && navigate(bucketPath(selected.name, "/delete")) });
  const create = button({ label: "Create bucket", variant: "primary", href: "#/create-bucket" });
  const refresh = iconButton("refresh", "Refresh", () => load());

  const tbl = table({
    ariaLabel: "Buckets",
    selectable: "single",
    rowKey: (b) => b.name,
    pageSize: 25,
    loading: true,
    sort: { id: "name", desc: false },
    filter: { placeholder: "Find buckets by name", match: (b, q) => b.name.toLowerCase().includes(q) },
    onSelect: (rows) => {
      selected = rows[0] || null;
      copyArn.disabled = empty.disabled = del.disabled = !selected;
    },
    columns: [
      { id: "name", header: "Name", sortValue: (b) => b.name, cell: (b) => link(b.name, bucketHref(b.name), { className: "strong" }) },
      { id: "region", header: "AWS Region", sortValue: (b) => b.region, cell: (b) => b.region },
      { id: "access", header: "Access", sortValue: (b) => ACCESS_TEXT[accessOf(b)], cell: (b) => accessBadge(accessOf(b)) },
      { id: "created", header: "Creation date", sortValue: (b) => b.created, cell: (b) => formatDate(b.created) },
    ],
    empty: () =>
      emptyState({
        title: "No buckets",
        text: "You don't have any buckets.",
        action: button({ label: "Create bucket", href: "#/create-bucket" }),
      }),
  });

  const counter = h("span", {});
  setPage({
    crumbs: rootCrumbs(),
    title: "Buckets",
    content: h(
      "div",
      { class: "stack" },
      pageHeader({ title: "General purpose buckets", description: "Buckets are containers for data stored in S3. Each bucket has its own access settings, versioning and lifecycle rules." }),
      errors,
      container({ title: "Account snapshot", description: "Storage on this server, for every bucket." }, snapshot),
      container(
        {
          title: h("span", {}, "General purpose buckets", counter),
          actions: [refresh, copyArn, empty, del, create],
        },
        tbl.el,
      ),
    ),
  });

  async function load() {
    errors.set(null);
    tbl.setLoading(true);
    try {
      const list = await refreshBuckets();
      if (!ctx.alive()) return;
      tbl.setRows(list);
      counter.textContent = ` (${list.length})`;
      const objects = list.reduce((n, b) => n + (Number(b.objects) || 0), 0);
      const pub = list.filter((b) => accessOf(b) === "public").length;
      snapshot.replaceChildren(
        stat("Buckets", String(list.length)),
        stat("Objects", objects.toLocaleString()),
        stat("Public buckets", String(pub), pub ? "warn" : ""),
        stat("Region", state.session.region),
      );
    } catch (e) {
      if (!ctx.alive()) return;
      tbl.setRows([]);
      errors.set(errorText(e));
    }
  }

  function stat(label, value, tone) {
    return h("div", { class: ["snapshot__item", tone ? `is-${tone}` : ""] }, h("div", { class: "snapshot__label" }, label), h("div", { class: "snapshot__value" }, value));
  }

  snapshot.append(h("div", { class: "muted" }, "Loading"));
  await load();
}
