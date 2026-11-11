// Secrets: the list page. Filtering is done by the server (ListSecrets Filters key "all", a prefix match on the name,
// description, tag keys and tag values); "Load more" follows NextToken.

import { call } from "../core/api.js";
import { debounce, h } from "../core/dom.js";
import { dateTime, relative, truncate, utcDate } from "../core/format.js";
import { navigate, secretPath } from "../core/router.js";
import { badge } from "../components/badge.js";
import { button } from "../components/button.js";
import { flash } from "../components/flash.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { toggle } from "../components/toggle.js";
import { showPage } from "./shell.js";

// Kept while the console is open, so coming back to the list keeps the filter.
const view = { filter: "", deleted: false };

export function renderSecretsList() {
  let items = [];
  let next = null;
  let seq = 0;

  const more = button("Load more", { onClick: () => load(true) });
  const moreRow = h("div", { class: "row", style: "justify-content:center", hidden: true }, more);

  const showDeleted = toggle("Show secrets scheduled for deletion", {
    checked: view.deleted,
    onChange: (on) => {
      view.deleted = on;
      load();
    },
  });

  const t = table({
    title: "Secrets",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Store a new secret", { variant: "primary", onClick: () => navigate("/store-secret") }),
    ],
    filter: { placeholder: "Filter secrets by name, description, tag key or tag value", value: view.filter, onInput: debounce((text) => {
      view.filter = text;
      load();
    }, 300) },
    tools: [showDeleted.el],
    columns: [
      {
        id: "name", header: "Secret name", wrap: true, sort: (s) => s.Name.toLowerCase(),
        cell: (s) => h("a", { href: `#${secretPath(s.Name)}` }, s.Name),
      },
      { id: "desc", header: "Description", cell: (s) => (s.Description ? truncate(s.Description, 90) : h("span", { class: "faint" }, "-")) },
      {
        id: "status", header: "Status", sort: (s) => (s.DeletedDate ? 1 : 0),
        cell: (s) => (s.DeletedDate ? badge("warning", "Scheduled for deletion") : badge("success", "Available")),
      },
      { id: "read", header: "Last retrieved (UTC)", sort: (s) => s.LastAccessedDate || 0, cell: (s) => utcDate(s.LastAccessedDate) },
      {
        id: "changed", header: "Last modified", sort: (s) => s.LastChangedDate || 0,
        cell: (s) => h("span", { title: dateTime(s.LastChangedDate) }, relative(s.LastChangedDate)),
      },
    ],
    trackBy: (s) => s.ARN,
    loading: true,
    empty: () => h("div", { class: "table-empty" },
      h("b", {}, "No secrets"),
      view.filter ? "No secret matches the filter." : "You don't have any secrets yet.",
      h("div", {}, button("Store a new secret", { onClick: () => navigate("/store-secret") }))),
    footer: moreRow,
  });

  async function load(append = false) {
    const mine = ++seq;
    const params = { MaxResults: 100, IncludePlannedDeletion: view.deleted, SortOrder: "asc" };
    if (view.filter.trim()) params.Filters = [{ Key: "all", Values: [view.filter.trim()] }];
    if (append && next) params.NextToken = next;
    if (!append) t.setLoading(true);
    try {
      const out = await call("ListSecrets", params);
      if (mine !== seq) return; // a newer filter is already loading
      items = append ? [...items, ...(out.SecretList || [])] : out.SecretList || [];
      next = out.NextToken || null;
      moreRow.hidden = !next;
      t.setItems(items);
    } catch (err) {
      if (mine !== seq) return;
      t.setItems(items);
      if (err.status !== 401) flash.error("Couldn't load the secrets", err);
    }
  }

  showPage(
    pageHeader({
      title: "Secrets",
      description: "Store, read, version and recover secrets with the AWS Secrets Manager API. "
        + "Your applications read them with any AWS SDK pointed at this server.",
    }),
    t.el);
  load();
}
