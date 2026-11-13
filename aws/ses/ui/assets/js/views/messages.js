// Messages (the sending log): status filter, search, server-side paging (NextToken) and auto-refresh.

import { call } from "../core/api.js";
import { debounce, h } from "../core/dom.js";
import { bytes, dateTime, relative, truncate } from "../core/format.js";
import { navigate, onLeave, pageId, paths, setQuery } from "../core/router.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { button } from "../components/button.js";
import { flash } from "../components/flash.js";
import { select } from "../components/form-field.js";
import { icon } from "../core/icons.js";
import { pageHeader } from "../components/page-header.js";
import { table } from "../components/table.js";
import { toggle } from "../components/toggle.js";
import { MESSAGE_STATUSES, messageStatus } from "./common.js";
import { showPage } from "./shell.js";

const PAGE = 50;
const view = { query: "", auto: false };

export function renderMessages(query) {
  const me = pageId();
  let status = query.get("status") || "";
  if (status && !MESSAGE_STATUSES.includes(status)) status = "";
  let tokens = [""]; // tokens[i] is the NextToken of page i
  let page = 0;
  let total = 0;
  let timer = null;
  let seq = 0;

  const statusSel = select([{ value: "", label: "Any status" }, ...MESSAGE_STATUSES.map((s) => ({ value: s, label: s.charAt(0) + s.slice(1).toLowerCase(), selected: s === status }))],
    { "aria-label": "Filter by status", class: "inline-select" });
  statusSel.addEventListener("change", () => {
    status = statusSel.value;
    setQuery({ status });
    restart();
  });

  const auto = toggle("Auto-refresh (5 s)", {
    checked: view.auto,
    onChange: (on) => {
      view.auto = on;
      schedule();
    },
  });

  const prev = h("button", { type: "button", class: "btn icon", "aria-label": "Previous page", onclick: () => go(page - 1) }, icon("caretLeft"));
  const next = h("button", { type: "button", class: "btn icon", "aria-label": "Next page", onclick: () => go(page + 1) }, icon("caretRight"));
  const pageLabel = h("span", {});
  const pager = h("div", { class: "pager" }, prev, pageLabel, next);
  const summary = h("span", { class: "muted" });

  const t = table({
    title: "Messages",
    description: "Every message this server accepted (API and SMTP), newest first. Messages are kept for the retention period.",
    actions: [
      button("Refresh", { variant: "icon", icon: "refresh", onClick: () => load() }),
      button("Send test email", { variant: "primary", icon: "send", onClick: () => navigate("/send") }),
    ],
    filter: {
      placeholder: "Search by message ID, sender, recipient or subject",
      value: view.query,
      onInput: debounce((text) => {
        view.query = text;
        restart();
      }, 300),
    },
    tools: [statusSel, auto.el, summary, pager],
    columns: [
      { id: "time", header: "Sent", cell: (m) => h("span", { class: "nowrap", title: dateTime(m.Timestamp) }, relative(m.Timestamp)) },
      { id: "subject", header: "Subject", wrap: true, cell: (m) => h("a", { href: `#${paths.message(m.MessageId)}` }, m.Subject ? truncate(m.Subject, 80) : "(no subject)") },
      { id: "from", header: "From", wrap: true, cell: (m) => m.From || m.Source },
      {
        id: "to", header: "Recipients", wrap: true,
        cell: (m) => {
          const d = m.Destinations || [];
          return d.length > 2 ? `${d.slice(0, 2).join(", ")} +${d.length - 2}` : d.join(", ");
        },
      },
      { id: "status", header: "Status", cell: (m) => messageStatus(m.Status) },
      { id: "via", header: "Via", cell: (m) => h("span", { class: "faint" }, m.Operation === "SMTP" ? "SMTP" : m.Operation || "-") },
      { id: "size", header: "Size", cell: (m) => h("span", { class: "nowrap" }, bytes(m.Size)) },
    ],
    trackBy: (m) => m.MessageId,
    loading: true,
    empty: () => h("div", { class: "table-empty" }, h("b", {}, "No messages"),
      view.query || status ? "No message matches the filter." : "Nothing was sent yet.",
      h("div", {}, button("Send test email", { onClick: () => navigate("/send") }))),
  });

  function drawPager() {
    const pages = Math.max(1, Math.ceil(total / PAGE));
    pageLabel.textContent = `${page + 1} / ${pages}`;
    prev.disabled = page === 0;
    next.disabled = !tokens[page + 1];
    summary.textContent = `${total} message${total === 1 ? "" : "s"}`;
  }

  function restart() {
    tokens = [""];
    page = 0;
    load();
  }

  function go(p) {
    if (p < 0 || (p > page && !tokens[p])) return;
    page = p;
    load();
  }

  async function load(quiet = false) {
    const mine = ++seq;
    if (!quiet) t.setLoading(true);
    const params = { PageSize: PAGE };
    if (status) params.Status = status;
    if (view.query.trim()) params.Query = view.query.trim();
    if (tokens[page]) params.NextToken = tokens[page];
    try {
      const out = await call("ListMessages", params);
      if (mine !== seq || me !== pageId()) return;
      total = out.Total || 0;
      tokens[page + 1] = out.NextToken || "";
      tokens.length = page + 2;
      t.setItems(out.Messages || []);
      drawPager();
    } catch (err) {
      if (mine !== seq || me !== pageId()) return;
      if (!quiet) t.setItems([]);
      if (err.status === 401) view.auto = false;
      else if (!quiet) flash.error("Couldn't load the messages", err);
    }
  }

  function schedule() {
    clearInterval(timer);
    timer = null;
    if (view.auto) {
      timer = setInterval(() => {
        // Stop when the page is gone (signed out, or navigated away).
        if (me !== pageId() || !t.el.isConnected) {
          clearInterval(timer);
          return;
        }
        load(true);
      }, 5000);
    }
  }
  onLeave(() => clearInterval(timer));

  showPage(
    breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "Messages" }]),
    pageHeader({ title: "Messages" }),
    t.el);
  drawPager();
  load();
  schedule();
}
