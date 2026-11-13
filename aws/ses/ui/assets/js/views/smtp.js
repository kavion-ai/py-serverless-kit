// SMTP settings: the SMTP endpoint (host, port, STARTTLS), the SMTP credentials (the password is derived from the
// secret access key the way SES does it; masked until revealed) and sample code. The password never goes into the
// samples: they read it from an environment variable.

import { call } from "../core/api.js";
import { h } from "../core/dom.js";
import { icon } from "../core/icons.js";
import { pageId } from "../core/router.js";
import { alert } from "../components/alert.js";
import { badge } from "../components/badge.js";
import { breadcrumbs } from "../components/breadcrumbs.js";
import { codeSamples } from "../components/code-samples.js";
import { container } from "../components/container.js";
import { copyButton } from "../components/copy-button.js";
import { flash } from "../components/flash.js";
import { keyValue } from "../components/key-value.js";
import { pageHeader } from "../components/page-header.js";
import { loadingPanel, serverInfo } from "./common.js";
import { showPage } from "./shell.js";

function samples({ host, port, startTls, username, region }) {
  const user = username || "<SMTP username>";
  const origin = window.location.origin;
  return [
    {
      id: "python", label: "Python (smtplib)", code: [
        "import os",
        "import smtplib",
        "from email.message import EmailMessage",
        "",
        "msg = EmailMessage()",
        'msg["From"] = "sender@example.com"   # a verified identity',
        'msg["To"] = "success@simulator.amazonses.com"',
        'msg["Subject"] = "Hello from SES"',
        'msg.set_content("It works.")',
        "",
        `with smtplib.SMTP(${JSON.stringify(host)}, ${port}) as smtp:`,
        ...(startTls ? ["    smtp.starttls()"] : ["    # The server offers no STARTTLS (no certificate configured)."]),
        `    smtp.login(${JSON.stringify(user)}, os.environ["SES_SMTP_PASSWORD"])`,
        "    smtp.send_message(msg)",
      ].join("\n"),
    },
    {
      id: "node", label: "Node.js (nodemailer)", code: [
        'import nodemailer from "nodemailer";',
        "",
        "const transport = nodemailer.createTransport({",
        `  host: ${JSON.stringify(host)},`,
        `  port: ${port},`,
        "  secure: false,",
        `  requireTLS: ${startTls ? "true" : "false"},`,
        `  auth: { user: ${JSON.stringify(user)}, pass: process.env.SES_SMTP_PASSWORD },`,
        "});",
        "",
        "await transport.sendMail({",
        '  from: "sender@example.com",',
        '  to: "success@simulator.amazonses.com",',
        '  subject: "Hello from SES",',
        '  text: "It works.",',
        "});",
      ].join("\n"),
    },
    {
      id: "boto3", label: "Python (boto3 sesv2)", code: [
        "import boto3",
        "",
        "ses = boto3.client(",
        '    "sesv2",',
        `    endpoint_url=${JSON.stringify(origin)},`,
        `    region_name=${JSON.stringify(region || "us-east-1")},`,
        '    aws_access_key_id="<access key id>",',
        '    aws_secret_access_key="<secret access key>",',
        ")",
        "out = ses.send_email(",
        '    FromEmailAddress="sender@example.com",',
        '    Destination={"ToAddresses": ["success@simulator.amazonses.com"]},',
        '    Content={"Simple": {"Subject": {"Data": "Hello from SES"}, "Body": {"Text": {"Data": "It works."}}}},',
        ")",
        'print(out["MessageId"])',
      ].join("\n"),
    },
  ];
}

export async function renderSmtp() {
  const crumbs = breadcrumbs([{ label: "Amazon SES", href: "#/account" }, { label: "SMTP settings" }]);
  const header = pageHeader({ title: "SMTP settings", description: "Send mail through this server from any application that speaks SMTP." });
  showPage(crumbs, header, loadingPanel());
  const me = pageId();
  let info;
  let creds;
  try {
    [info, creds] = await Promise.all([serverInfo(), call("GetSmtpCredentials")]);
  } catch (err) {
    if (me !== pageId()) return;
    if (err.status !== 401) flash.error("Couldn't load the SMTP settings", err);
    showPage(crumbs, header);
    return;
  }
  if (me !== pageId()) return;
  const smtp = info.Smtp || {};
  const host = smtp.Host || window.location.hostname;
  const port = smtp.Port || 2587;
  const startTls = Boolean(smtp.StartTls);

  const endpoint = container({ title: "SMTP endpoint" }, keyValue([
    [{ label: "SMTP endpoint", value: host, copy: host, mono: true },
      { label: "Port", value: String(port), copy: String(port), mono: true }],
    [{ label: "Transport Layer Security (TLS)", value: startTls ? badge("success", "STARTTLS offered") : badge("stopped", "Not available (no certificate)") },
      { label: "TLS required", value: smtp.RequireTls ? "Yes: login and mail only after STARTTLS" : "No" }],
    [{ label: "SMTP service", value: smtp.Enabled === false ? badge("stopped", "Off (SES_SMTP=off)") : badge("success", "Running") },
      { label: "Authentication", value: "AUTH PLAIN / LOGIN" }],
  ]));

  let credsPanel;
  if (!creds.Username) {
    credsPanel = container({ title: "SMTP credentials" }, alert("info", "No credentials needed",
      creds.Note || "Authentication is off: the SMTP endpoint takes any login."));
  } else {
    let shown = false;
    const pwText = h("span", { class: "mono masked" });
    const reveal = h("button", { type: "button", class: "btn icon" });
    const drawPw = () => {
      pwText.textContent = shown ? creds.Password : "•".repeat(Math.min(24, creds.Password.length || 12));
      pwText.classList.toggle("masked", !shown);
      reveal.replaceChildren(icon(shown ? "eyeOff" : "eye"));
      reveal.title = shown ? "Hide password" : "Show password";
      reveal.setAttribute("aria-label", reveal.title);
      reveal.setAttribute("aria-pressed", String(shown));
    };
    reveal.addEventListener("click", () => {
      shown = !shown;
      drawPw();
    });
    drawPw();
    credsPanel = container({
      title: "SMTP credentials",
      description: "The SMTP user name is your access key ID; the password is derived from its secret access key "
        + `for the ${creds.Region || info.Region} region (the SES SMTP password algorithm), so it works with real SES tooling.`,
    }, keyValue([
      [{ label: "SMTP user name", value: creds.Username, copy: creds.Username, mono: true }],
      [{ label: "SMTP password", value: h("span", { class: "pw-row" }, pwText, reveal, copyButton(() => creds.Password, { label: "Copy SMTP password" })) }],
    ]),
    h("div", { style: "margin-top:16px" }, alert("warning", "Keep the password secret",
      "Anyone with it can send mail as you. It changes when the secret access key changes.")));
  }

  showPage(crumbs, header,
    smtp.Enabled === false ? alert("warning", "The SMTP endpoint is off", "Start the server with SES_SMTP=on to accept mail over SMTP.") : null,
    endpoint,
    credsPanel,
    container({ title: "Sample code", description: "Set SES_SMTP_PASSWORD in the environment to the SMTP password above." },
      codeSamples(samples({ host, port, startTls, username: creds.Username, region: creds.Region || info.Region }))));
}
