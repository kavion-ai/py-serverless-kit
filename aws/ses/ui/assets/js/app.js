// Bootstraps the console: theme, session check, then the sign-in page or the shell + routes.

import { loadSession } from "./core/api.js";
import { h } from "./core/dom.js";
import { navigate, resolve, route, start } from "./core/router.js";
import { on, session } from "./core/state.js";
import { applyTheme } from "./core/theme.js";
import { alert } from "./components/alert.js";
import { renderAccount } from "./views/account.js";
import { renderConfigSet, renderConfigSets, renderCreateConfigSet } from "./views/config-sets.js";
import { renderCreateIdentity, renderIdentities } from "./views/identities.js";
import { renderIdentity } from "./views/identity-detail.js";
import { renderLogin } from "./views/login.js";
import { renderMessage } from "./views/message-detail.js";
import { renderMessages } from "./views/messages.js";
import { renderNotFound } from "./views/not-found.js";
import { renderSend } from "./views/send.js";
import { renderShell } from "./views/shell.js";
import { renderSmtp } from "./views/smtp.js";
import { renderSuppression } from "./views/suppression.js";
import { renderTemplate, renderTemplateForm, renderTemplates } from "./views/templates.js";

const root = document.getElementById("app");
const name = (m) => decodeURIComponent(m[1]);

route(/^\/?$/, () => navigate("/account", { replace: true }));
route(/^\/account\/?$/, () => renderAccount());
route(/^\/identities\/?$/, () => renderIdentities());
route(/^\/identities\/create\/?$/, () => renderCreateIdentity());
route(/^\/identities\/([^/]+)\/?$/, (m, query) => renderIdentity(name(m), query.get("tab")));
route(/^\/send\/?$/, (m, query) => renderSend(query));
route(/^\/messages\/?$/, (m, query) => renderMessages(query));
route(/^\/messages\/([^/]+)\/?$/, (m, query) => renderMessage(name(m), query.get("tab")));
route(/^\/templates\/?$/, () => renderTemplates());
route(/^\/templates\/create\/?$/, () => renderTemplateForm(null));
route(/^\/templates\/([^/]+)\/edit\/?$/, (m) => renderTemplateForm(name(m)));
route(/^\/templates\/([^/]+)\/?$/, (m) => renderTemplate(name(m)));
route(/^\/configuration-sets\/?$/, () => renderConfigSets());
route(/^\/configuration-sets\/create\/?$/, () => renderCreateConfigSet());
route(/^\/configuration-sets\/([^/]+)\/?$/, (m) => renderConfigSet(name(m)));
route(/^\/suppression\/?$/, () => renderSuppression());
route(/^\/smtp\/?$/, () => renderSmtp());
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
