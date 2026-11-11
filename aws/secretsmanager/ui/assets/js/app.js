// Bootstraps the console: theme, session check, then the sign-in page or the shell + routes.

import { loadSession } from "./core/api.js";
import { h } from "./core/dom.js";
import { navigate, resolve, route, start } from "./core/router.js";
import { on, session } from "./core/state.js";
import { applyTheme } from "./core/theme.js";
import { alert } from "./components/alert.js";
import { renderLogin } from "./views/login.js";
import { renderNotFound } from "./views/not-found.js";
import { renderQuickStart } from "./views/quick-start.js";
import { renderSecret } from "./views/secret-detail.js";
import { renderSecretsList } from "./views/secrets-list.js";
import { renderShell } from "./views/shell.js";
import { renderStoreSecret } from "./views/store-secret.js";

const root = document.getElementById("app");

route(/^\/?$/, () => navigate("/secrets", { replace: true }));
route(/^\/secrets\/?$/, () => renderSecretsList());
route(/^\/store-secret\/?$/, () => renderStoreSecret());
route(/^\/secrets\/(.+)$/, (m, query) => renderSecret(decodeURIComponent(m[1]), query.get("tab")));
route(/^\/quick-start\/?$/, () => renderQuickStart());
route(/.*/, () => renderNotFound());

let started = false;

function enter() {
  renderShell(root);
  if (started) resolve();
  else {
    started = true;
    start();
  }
}

on("signed-out", (message) => renderLogin(root, { message, onSignedIn: enter }));

async function boot() {
  applyTheme();
  try {
    await loadSession();
  } catch (err) {
    root.replaceChildren(h("div", { class: "center-page" }, h("div", { class: "login-card" },
      alert("error", "The server did not answer", err.message || String(err)))));
    return;
  }
  if (session.authenticated) enter();
  else renderLogin(root, { onSignedIn: enter });
}

boot();
