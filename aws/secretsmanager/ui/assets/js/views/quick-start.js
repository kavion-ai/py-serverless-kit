// Quick start: how to reach this server from code.

import { h } from "../core/dom.js";
import { session } from "../core/state.js";
import { alert } from "../components/alert.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { codeSamples } from "../components/code-samples.js";
import { container } from "../components/container.js";
import { keyValue } from "../components/key-value.js";
import { pageHeader } from "../components/page-header.js";
import { showPage } from "./shell.js";

export function renderQuickStart() {
  const origin = window.location.origin;
  showPage(
    breadcrumbs([{ label: "Secrets Manager", href: "#/secrets" }, { label: "Quick start" }]),
    pageHeader({
      title: "Quick start",
      description: "This server speaks the AWS Secrets Manager API. Point any AWS SDK, the AWS CLI or pskit's get_secret() at "
        + "the endpoint below and sign with an access key it knows. Code written for AWS runs unchanged.",
    }),
    container({ title: "Connection" }, keyValue([
      [{ label: "Endpoint URL", value: origin, copy: origin, mono: true }],
      [{ label: "Region", value: "Any. ARNs carry the region you sign with." }],
      [{ label: "Authentication", value: session.auth ? "AWS Signature Version 4 (access key ID + secret access key)" : "Off (development only)" }],
    ])),
    container({ title: "Read a secret", description: "Replace prod/db with your secret's name." }, codeSamples("prod/db")),
    container({ title: "Good to know" }, h("ul", { style: "margin:0;padding-left:18px", class: "stack" },
      h("li", {}, "Every request is checked with SigV4: a wrong secret key, an unknown access key or a request more than "
        + "15 minutes old is refused."),
      h("li", {}, "Saving a new value creates a new version labelled AWSCURRENT; the previous one becomes AWSPREVIOUS."),
      h("li", {}, "Deleted secrets can be restored during the recovery window (7-30 days)."),
      h("li", {}, "Rotation and replica regions are not supported by this server."))),
    session.auth ? null : alert("warning", "Authentication is off", "Anyone who can reach this port can read every secret. "
      + "Set SM_SECRET_ACCESS_KEY and remove SM_AUTH=off for anything but local development."));
}
