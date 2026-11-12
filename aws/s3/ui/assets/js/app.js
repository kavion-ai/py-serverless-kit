// Bootstraps the console: reads the session, shows the sign-in page or the shell, and starts the hash router.

import { h, mount } from "./core/dom.js";
import { state } from "./core/state.js";
import { getSession, onUnauthorized, errorText } from "./core/api.js";
import { route, start, beforeEach, onNavigate, setNotFound, navigate, reload } from "./core/router.js";
import { ageFlashes, clearFlashes } from "./components/toast.js";
import { alert } from "./components/alert.js";
import { ensureShell, teardownShell, closeMobileNav, setSignOutHandler, refreshBuckets } from "./views/shell.js";
import { renderLogin } from "./views/login.js";
import { applyTheme } from "./core/theme.js";
import * as buckets from "./views/buckets.js";
import * as createBucket from "./views/create-bucket.js";
import * as bucketDanger from "./views/bucket-danger.js";
import * as bucket from "./views/bucket.js";
import * as upload from "./views/upload.js";
import * as object from "./views/object.js";
import * as objectEdit from "./views/object-edit.js";
import * as deleteObjects from "./views/delete-objects.js";
import * as bucketSettings from "./views/bucket-settings.js";
import * as policyEditor from "./views/policy-editor.js";
import * as lifecycleRule from "./views/lifecycle-rule.js";

const app = document.getElementById("app");
applyTheme();

function showLogin(message) {
  teardownShell();
  clearFlashes();
  state.buckets = null;
  renderLogin(app, message, () => {
    refreshBuckets().catch(() => undefined);
    reload();
  });
}

function registerRoutes() {
  route("/buckets", buckets.render);
  route("/create-bucket", createBucket.render);
  route("/buckets/:bucket", bucket.render);
  route("/buckets/:bucket/upload", upload.render);
  route("/buckets/:bucket/object", object.render);
  route("/buckets/:bucket/object/edit/:what", objectEdit.render);
  route("/buckets/:bucket/delete-objects", deleteObjects.render);
  route("/buckets/:bucket/empty", bucketDanger.renderEmpty);
  route("/buckets/:bucket/delete", bucketDanger.renderDelete);
  route("/buckets/:bucket/edit/policy", policyEditor.render);
  route("/buckets/:bucket/edit/:setting", bucketSettings.render);
  route("/buckets/:bucket/lifecycle/create", lifecycleRule.render);
  route("/buckets/:bucket/lifecycle/edit", lifecycleRule.render);
  setNotFound(() => navigate("/buckets", {}, { replace: true }));
}

async function boot() {
  try {
    await getSession();
  } catch (e) {
    mount(app, h("div", { class: "login" }, h("div", { class: "login__card" }, alert({ type: "error", title: "The console could not start" }, errorText(e)))));
    return;
  }
  onUnauthorized(() => showLogin("Your session ended. Sign in again."));
  setSignOutHandler(() => showLogin("Signed out."));
  registerRoutes();
  onNavigate(() => {
    ageFlashes();
    closeMobileNav();
  });
  beforeEach(() => {
    if (!state.session.authenticated) {
      if (!document.querySelector(".login")) showLogin();
      return false;
    }
    ensureShell();
    return true;
  });
  start();
}

boot();
