// The signed-in layout: top bar, side navigation, flashbar and the page area that views render into.

import { logout } from "../core/api.js";
import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { current } from "../core/router.js";
import { emit, on, prefs, session } from "../core/state.js";
import { cycleTheme, currentTheme, THEME_ICON, THEME_LABEL } from "../core/theme.js";
import { copyButton } from "../components/copy-button.js";
import { clearFlash, flashArea } from "../components/flash.js";
import { DELIVERY_LABEL, serverInfo } from "./common.js";

let pageEl = null;
let offRoute = null;
let offInfo = null;

/** Render a page (replaces the previous one). */
export function showPage(...nodes) {
  if (!pageEl) return;
  pageEl.replaceChildren(...nodes.flat().filter(Boolean));
  window.scrollTo({ top: 0 });
}

export function renderShell(root) {
  const narrow = () => window.matchMedia("(max-width: 900px)").matches;
  const nav = h("nav", { class: "sidenav", "aria-label": "Simple Email Service", id: "sidenav" });
  const scrim = h("div", { class: "scrim", onclick: () => setNav(false) });
  let navOpen = !narrow() && prefs.get("nav", "open") !== "closed";

  function setNav(open, remember = true) {
    navOpen = open;
    nav.classList.toggle("open", open);
    nav.classList.toggle("collapsed", !open);
    scrim.classList.toggle("show", open && narrow());
    menuBtn.setAttribute("aria-expanded", String(open));
    if (remember && !narrow()) prefs.set("nav", open ? "open" : "closed");
  }

  const themeBtn = h("button", { type: "button", class: "tb-btn", onclick: () => drawTheme(cycleTheme()) });
  const drawTheme = (t) => {
    themeBtn.replaceChildren(icon(THEME_ICON[t]));
    themeBtn.title = THEME_LABEL[t];
    themeBtn.setAttribute("aria-label", `${THEME_LABEL[t]} (change)`);
  };
  drawTheme(currentTheme());

  const menuBtn = h("button", {
    type: "button", class: "tb-btn", "aria-label": "Show or hide the navigation", title: "Navigation",
    "aria-controls": "sidenav", onclick: () => setNav(!navOpen),
  }, icon("menu"));

  const topbar = h("header", { class: "topbar" },
    menuBtn,
    h("a", { class: "brand", href: "#/account" }, h("span", { class: "logo" }, icon("mail")), "SES", h("span", { class: "brand-sub" }, "Simple Email Service")),
    h("span", { class: "spacer" }),
    themeBtn,
    session.auth
      ? [h("span", { class: "who", title: session.user }, session.user ? `Signed in as ${session.user}` : "Signed in"),
        h("button", {
          type: "button", class: "tb-btn",
          onclick: async () => {
            try {
              await logout();
            } finally {
              emit("signed-out", "You signed out.");
            }
          },
        }, icon("signOut"), "Sign out")]
      : h("span", { class: "who" }, "Authentication off"));

  const link = (href, label, match) => h("a", { class: "nav", href, dataset: { match } }, label);
  const regionBox = h("span", {}, "…");
  const deliveryBox = h("span", {}, "…");
  nav.append(
    h("h2", {}, "Amazon SES"),
    link("#/account", "Account dashboard", "^/account"),
    h("div", { class: "section" }, "Configuration"),
    link("#/identities", "Identities", "^/identities"),
    link("#/templates", "Templates", "^/templates"),
    link("#/configuration-sets", "Configuration sets", "^/configuration-sets"),
    link("#/suppression", "Suppression list", "^/suppression"),
    link("#/smtp", "SMTP settings", "^/smtp"),
    link("#/delivery", "Delivery settings", "^/delivery"),
    h("div", { class: "section" }, "Sending"),
    link("#/send", "Send test email", "^/send"),
    link("#/messages", "Messages", "^/messages"),
    h("div", { class: "section" }, "Server endpoint"),
    h("div", { class: "endpoint" }, h("span", {}, window.location.origin), copyButton(window.location.origin, { label: "Copy endpoint" })),
    h("div", { class: "section" }, "Region"),
    h("div", { class: "endpoint" }, regionBox),
    h("div", { class: "section" }, "Delivery mode"),
    h("a", { class: "endpoint endpoint-link", href: "#/delivery", title: "Change the delivery mode" }, deliveryBox));
  const drawInfo = (info) => {
    regionBox.textContent = info.Region || "-";
    deliveryBox.textContent = `${DELIVERY_LABEL[info.Delivery] || info.Delivery || "-"}${info.DeliverySource === "console" ? " (set in the console)" : ""}`;
  };
  if (offInfo) offInfo();
  offInfo = on("server-info", drawInfo);
  serverInfo().then(drawInfo).catch(() => {
    regionBox.textContent = "-";
    deliveryBox.textContent = "-";
  });

  const highlight = () => {
    const { path } = current();
    for (const a of nav.querySelectorAll("a.nav")) a.classList.toggle("active", new RegExp(a.dataset.match).test(path));
  };
  if (offRoute) offRoute();
  offRoute = on("route", () => {
    highlight();
    clearFlashOnNavigate();
    if (narrow()) setNav(false, false);
  });

  pageEl = h("div", { class: "page", id: "page" });
  const content = h("main", { class: "content", id: "main" }, h("div", { class: "content-inner" }, flashArea(), pageEl));
  root.replaceChildren(h("div", { class: "shell" }, topbar, h("div", { class: "body" }, nav, scrim, content)));
  setNav(navOpen, false);
  highlight();
}

// Notifications are cleared when you move to another page, except right after keepFlash() (e.g. "Identity created"
// shown on the page you land on).
let keep = false;
function clearFlashOnNavigate() {
  if (keep) keep = false;
  else clearFlash();
}

/** Call before navigating when a notification should stay on the next page. */
export function keepFlash() {
  keep = true;
}
