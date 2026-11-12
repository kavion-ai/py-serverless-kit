// The application shell: top bar, collapsible side navigation, breadcrumbs, flashbar and the page content area.

import { h, mount } from "../core/dom.js";
import { state, navCollapsed, setNavCollapsed } from "../core/state.js";
import { api, logout } from "../core/api.js";
import { current, href, seg } from "../core/router.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { attachFlashbar } from "../components/toast.js";
import { icon } from "../components/icons.js";
import { copyButton } from "../components/copy-button.js";
import { cycleTheme, currentTheme, THEME_ICON, THEME_LABEL } from "../core/theme.js";

let shell = null;
let onSignOut = () => {};

export function setSignOutHandler(fn) {
  onSignOut = fn;
}

const isMobile = () => window.matchMedia("(max-width: 900px)").matches;

function toggleNav() {
  const root = document.body;
  if (isMobile()) {
    root.classList.toggle("nav-open");
  } else {
    const collapsed = !root.classList.contains("nav-collapsed");
    root.classList.toggle("nav-collapsed", collapsed);
    setNavCollapsed(collapsed);
  }
}

export function closeMobileNav() {
  document.body.classList.remove("nav-open");
}

function themeButton() {
  const btn = h("button", { type: "button", class: "topbar__btn", onclick: () => draw(cycleTheme()) });
  const draw = (t) => {
    mount(btn, icon(THEME_ICON[t], { size: 18 }));
    btn.title = THEME_LABEL[t];
    btn.setAttribute("aria-label", `${THEME_LABEL[t]} (change)`);
  };
  draw(currentTheme());
  return btn;
}

function topBar() {
  const s = state.session;
  const user = s.auth
    ? [
        h("span", { class: "topbar__who", title: s.user || "" }, s.user ? `Signed in as ${s.user}` : "Signed in"),
        h(
          "button",
          {
            type: "button",
            class: "topbar__btn",
            onclick: async () => {
              try {
                await logout();
              } finally {
                onSignOut();
              }
            },
          },
          icon("sign-out", { size: 18 }),
          "Sign out",
        ),
      ]
    : h("span", { class: "topbar__who topbar__who--warn", title: "S3_AUTH=off: anyone who reaches this server can use it" }, "Authentication off");
  return h(
    "header",
    { class: "topbar" },
    h("button", { type: "button", class: "topbar__btn", "aria-label": "Show or hide the navigation", title: "Navigation", onclick: toggleNav }, icon("menu", { size: 18 })),
    h("a", { class: "topbar__brand", href: "#/buckets" }, h("span", { class: "topbar__logo" }, icon("bucket", { size: 16 })), h("span", { class: "topbar__name" }, "S3")),
    h("div", { class: "topbar__spacer" }),
    themeButton(),
    user,
  );
}

function sideNav() {
  const buckets = h("ul", { class: "sidenav__buckets" });
  const nav = h(
    "aside",
    { class: "sidenav", "aria-label": "S3" },
    h(
      "div",
      { class: "sidenav__header" },
      h("h2", {}, "S3"),
      h("button", { type: "button", class: "sidenav__close", "aria-label": "Close navigation", onclick: toggleNav }, icon("close", { size: 16 })),
    ),
    h("ul", { class: "sidenav__links" }, h("li", {}, h("a", { href: "#/buckets", dataset: { nav: "buckets" } }, "General purpose buckets"))),
    h("div", { class: "sidenav__section" }, "Buckets"),
    buckets,
    h("div", { class: "sidenav__section" }, "Server endpoint"),
    h("div", { class: "sidenav__endpoint" }, h("code", {}, location.origin), copyButton(location.origin, { title: "Copy endpoint" })),
    h("div", { class: "sidenav__section" }, "Region"),
    h("div", { class: "sidenav__endpoint" }, h("code", {}, state.session.region), state.session.version ? h("span", { class: "sidenav__meta" }, `v${state.session.version}`) : null),
  );
  nav.bucketList = buckets;
  return nav;
}

export function ensureShell() {
  if (shell && document.body.contains(shell.root)) return shell;
  const app = document.getElementById("app");
  const nav = sideNav();
  const crumbs = h("div", { class: "layout__crumbs" });
  const flashbar = h("div", { class: "flashbar", "aria-live": "polite" });
  const content = h("main", { class: "layout__content", id: "content", tabindex: "-1" });
  const root = h(
    "div",
    { class: "layout" },
    topBar(),
    h(
      "div",
      { class: "layout__body" },
      nav,
      h("div", { class: "layout__scrim", onclick: closeMobileNav }),
      h("div", { class: "layout__main" }, crumbs, flashbar, content),
    ),
  );
  mount(app, root);
  document.body.classList.toggle("nav-collapsed", navCollapsed());
  attachFlashbar(flashbar);
  shell = { root, nav, crumbs, flashbar, content };
  drawBucketNav();
  if (!state.buckets) refreshBuckets().catch(() => undefined);
  return shell;
}

export function teardownShell() {
  shell = null;
  document.body.classList.remove("nav-open");
}

/** Show a page: setPage({crumbs: [{label, href}], content, title}). */
export function setPage({ crumbs = [], content, title }) {
  if (!shell || !state.session.authenticated) return;
  mount(shell.crumbs, crumbs.length ? breadcrumbs(crumbs) : "");
  mount(shell.content, content);
  document.title = `${title ? title + " | " : ""}S3 console`;
  highlightNav();
}

export function highlightNav() {
  if (!shell) return;
  const { path } = current();
  const m = /^\/buckets\/([^/?]+)/.exec(path);
  const active = m ? m[1] : "";
  shell.nav.querySelectorAll("a[data-nav]").forEach((a) => {
    const on = a.dataset.nav === "buckets" ? path === "/buckets" || path === "/create-bucket" : a.dataset.nav === active;
    a.classList.toggle("is-active", on);
    if (on) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function drawBucketNav() {
  if (!shell) return;
  const list = state.buckets || [];
  const max = 25;
  mount(
    shell.nav.bucketList,
    list.slice(0, max).map((b) => h("li", {}, h("a", { href: href(`/buckets/${seg(b.name)}`), dataset: { nav: seg(b.name) }, title: b.name }, icon("bucket", { size: 14 }), h("span", {}, b.name)))),
    list.length > max ? h("li", {}, h("a", { href: "#/buckets", class: "sidenav__more" }, `View all ${list.length} buckets`)) : null,
    state.buckets && !list.length ? h("li", { class: "sidenav__empty" }, "No buckets yet") : null,
  );
  highlightNav();
}

/** Reload the bucket list (ListBuckets) and redraw the navigation. */
export async function refreshBuckets() {
  const data = await api("ListBuckets");
  state.buckets = data.buckets || [];
  drawBucketNav();
  return state.buckets;
}
