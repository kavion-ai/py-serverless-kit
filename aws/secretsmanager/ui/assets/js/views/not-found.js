// Unknown routes.

import { h } from "../core/dom.js";
import { navigate } from "../core/router.js";
import { alert } from "../components/alert.js";
import { button } from "../components/button.js";
import { pageHeader } from "../components/page-header.js";
import { showPage } from "./shell.js";

export function renderNotFound(message = "This page doesn't exist.") {
  showPage(
    pageHeader({ title: "Page not found" }),
    alert("warning", message, h("div", { style: "margin-top:8px" },
      button("Go to secrets", { variant: "primary", onClick: () => navigate("/secrets") }))));
}
