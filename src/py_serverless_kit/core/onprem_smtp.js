"use strict";
// pskit SMTP service: receives mail for your domains (nodemailer's smtp-server), parses it (mailparser) and
// POSTs it to the pskit host, which runs every function with an `smtp` trigger on this resource.
//
// The JSON a handler gets (event.data) has simple fields (from, to, cc, subject, text, html, headers,
// attachments with base64 content, ...) plus the same data in the shape Amazon SES gives Lambda:
// Records[0].ses.mail / .receipt, and `content` = the raw message in base64 (as SES -> SNS with BASE64 encoding).
//
// Settings (environment): PSKIT_SMTP_NAME (resource key), PSKIT_FUNCTIONS_URL (the pskit host),
// PSKIT_ADMIN_TOKEN (the host's admin_token, if set), PSKIT_SMTP_DOMAINS (comma list; mail for other domains is
// refused, so this is never an open relay), PSKIT_SMTP_PORT, PSKIT_SMTP_BIND, PSKIT_SMTP_HOSTNAME, PSKIT_SMTP_MAX_MB.

const crypto = require("crypto");
const http = require("http");
const https = require("https");
const net = require("net");

const env = process.env;
const KEY = env.PSKIT_SMTP_NAME || "smtp";
const PORT = Number(env.PSKIT_SMTP_PORT || 25);
const BIND = env.PSKIT_SMTP_BIND || "0.0.0.0";
const HOSTNAME = env.PSKIT_SMTP_HOSTNAME || undefined;
const MAX_BYTES = Math.round(Number(env.PSKIT_SMTP_MAX_MB || 25) * 1024 * 1024);
const DOMAINS = (env.PSKIT_SMTP_DOMAINS || "")
  .split(",")
  .map((d) => d.trim().toLowerCase())
  .filter(Boolean);
const TARGET = `${(env.PSKIT_FUNCTIONS_URL || "http://127.0.0.1:8080").replace(/\/+$/, "")}/__pskit/smtp/${encodeURIComponent(KEY)}`;
const TOKEN = env.PSKIT_ADMIN_TOKEN || "";

if (process.argv[2] === "--check") {
  // Health check: is the SMTP port accepting connections?
  const host = BIND === "0.0.0.0" ? "127.0.0.1" : BIND;
  const sock = net.connect(PORT, host);
  sock.setTimeout(2000, () => process.exit(1));
  sock.on("connect", () => process.exit(0));
  sock.on("error", () => process.exit(1));
  return;
}

const { SMTPServer } = require("smtp-server");
const { simpleParser } = require("mailparser");

function log(...parts) {
  console.log(new Date().toISOString(), ...parts);
}

function smtpError(code, message) {
  const err = new Error(message);
  err.responseCode = code;
  return err;
}

/** Mail for one of DOMAINS or a subdomain of it (every domain when the list is empty). */
function accepted(address) {
  if (!DOMAINS.length) return true;
  const domain = String(address || "").split("@").pop().toLowerCase();
  return DOMAINS.some((d) => domain === d || domain.endsWith(`.${d}`));
}

/** AddressObject(s) from mailparser -> [{address, name}] (groups flattened). */
function addresses(obj) {
  const out = [];
  const visit = (list) => {
    for (const item of list || []) {
      if (item.group) visit(item.group);
      else if (item.address) out.push({ address: item.address, name: item.name || "" });
    }
  };
  for (const o of Array.isArray(obj) ? obj : obj ? [obj] : []) visit(o.value);
  return out;
}

const formatted = (a) => (a.name ? `${a.name} <${a.address}>` : a.address);

/** Raw header lines -> [{name, value}] (unfolded, not decoded), as SES lists them. */
function headerList(parsed) {
  return (parsed.headerLines || []).map(({ line }) => {
    const at = line.indexOf(":");
    return { name: line.slice(0, at).trim(), value: line.slice(at + 1).replace(/\r?\n[ \t]+/g, " ").trim() };
  });
}

function toEvent(raw, parsed, session, started) {
  const id = crypto.randomBytes(20).toString("hex");
  const now = new Date();
  const from = addresses(parsed.from);
  const to = addresses(parsed.to);
  const cc = addresses(parsed.cc);
  const replyTo = addresses(parsed.replyTo);
  const mailFrom = (session.envelope.mailFrom && session.envelope.mailFrom.address) || "";
  const recipients = session.envelope.rcptTo.map((r) => r.address);
  const listed = new Set([...to, ...cc].map((a) => a.address.toLowerCase()));
  const headers = headerList(parsed);
  const firstHeaders = {};
  for (const h of headers) {
    const name = h.name.toLowerCase();
    if (!(name in firstHeaders)) firstHeaders[name] = h.value;
  }
  const rawHeader = (name) => (headers.find((h) => h.name.toLowerCase() === name) || {}).value;
  const references = parsed.references ? [].concat(parsed.references) : [];
  const attachments = (parsed.attachments || []).map((a) => ({
    filename: a.filename || "",
    content_type: a.contentType || "application/octet-stream",
    disposition: a.contentDisposition || "attachment",
    size: a.size || (a.content ? a.content.length : 0),
    content_id: a.cid || "",
    checksum: a.checksum || "",
    content: a.content ? a.content.toString("base64") : "",
  }));
  const commonHeaders = {
    returnPath: mailFrom,
    from: from.map(formatted),
    date: rawHeader("date") || now.toUTCString(),
    to: to.map(formatted),
    messageId: parsed.messageId || "",
    subject: parsed.subject || "",
  };
  if (cc.length) commonHeaders.cc = cc.map(formatted);
  if (replyTo.length) commonHeaders.replyTo = replyTo.map(formatted);
  const notChecked = { status: "GRAY" }; // pskit does not scan for spam / viruses or check SPF, DKIM, DMARC
  return {
    id,
    server: KEY,
    received_at: now.toISOString(),
    from: from.length ? from[0].address : mailFrom,
    from_name: from.length ? from[0].name : "",
    to: to.map((a) => a.address),
    cc: cc.map((a) => a.address),
    bcc: recipients.filter((r) => !listed.has(r.toLowerCase())),
    reply_to: replyTo.map((a) => a.address),
    subject: parsed.subject || "",
    date: parsed.date ? parsed.date.toISOString() : null,
    message_id: parsed.messageId || "",
    in_reply_to: parsed.inReplyTo || "",
    references,
    text: parsed.text || "",
    html: parsed.html || "",
    headers: firstHeaders,
    attachments,
    envelope: { mail_from: mailFrom, rcpt_to: recipients },
    remote_ip: session.remoteAddress || "",
    helo: session.hostNameAppearsAs || "",
    tls: Boolean(session.secure),
    size: raw.length,
    // Amazon SES compatible: the event SES gives a Lambda receipt-rule action, and the raw message as an SNS
    // action with encoding BASE64 delivers it.
    Records: [
      {
        eventSource: "aws:ses",
        eventVersion: "1.0",
        ses: {
          mail: {
            timestamp: now.toISOString(),
            source: mailFrom,
            messageId: id,
            destination: recipients,
            headersTruncated: false,
            headers,
            commonHeaders,
          },
          receipt: {
            timestamp: now.toISOString(),
            processingTimeMillis: Date.now() - started,
            recipients,
            spamVerdict: notChecked,
            virusVerdict: notChecked,
            spfVerdict: notChecked,
            dkimVerdict: notChecked,
            dmarcVerdict: notChecked,
            action: { type: "Lambda", invocationType: "RequestResponse" },
          },
        },
      },
    ],
    content: raw.toString("base64"),
    content_encoding: "BASE64",
  };
}

/** POST the mail to the pskit host -> {status, body}. */
function forward(event) {
  const body = Buffer.from(JSON.stringify(event), "utf8");
  const url = new URL(TARGET);
  const headers = { "content-type": "application/json", "content-length": body.length };
  if (TOKEN) headers["x-pskit-token"] = TOKEN;
  return new Promise((resolve, reject) => {
    const req = (url.protocol === "https:" ? https : http).request(url, { method: "POST", headers, timeout: 15 * 60 * 1000 }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString("utf8") }));
    });
    req.on("timeout", () => req.destroy(new Error("the pskit host did not answer in 15 minutes")));
    req.on("error", reject);
    req.end(body);
  });
}

const server = new SMTPServer({
  name: HOSTNAME,
  banner: "pskit SMTP",
  size: MAX_BYTES,
  authOptional: true,
  disabledCommands: ["AUTH"], // receive only: nobody logs in and nothing is relayed
  logger: false,
  onRcptTo(address, session, callback) {
    if (!accepted(address.address)) {
      log(`refused ${address.address} from ${session.remoteAddress}: not one of ${DOMAINS.join(", ")}`);
      return callback(smtpError(550, `5.7.1 ${address.address}: relay not permitted`));
    }
    callback();
  },
  onData(stream, session, callback) {
    const started = Date.now();
    const chunks = [];
    stream.on("data", (c) => chunks.push(c));
    stream.on("error", (err) => callback(err));
    stream.on("end", async () => {
      if (stream.sizeExceeded) return callback(smtpError(552, `5.3.4 message larger than ${MAX_BYTES} bytes`));
      const raw = Buffer.concat(chunks);
      let event;
      try {
        event = toEvent(raw, await simpleParser(raw), session, started);
      } catch (err) {
        log(`unreadable mail from ${session.remoteAddress}: ${err.message}`);
        return callback(smtpError(554, "5.6.0 the message could not be parsed"));
      }
      const summary = `mail ${event.id} from ${event.from} to ${event.envelope.rcpt_to.join(", ")} "${event.subject}" ` +
        `${raw.length} bytes, ${event.attachments.length} attachment(s)`;
      try {
        const res = await forward(event);
        if (res.status >= 200 && res.status < 300) {
          log(`${summary} -> delivered ${res.body.slice(0, 300)}`);
          return callback(null, `2.0.0 Ok: queued as ${event.id}`);
        }
        log(`${summary} -> host answered ${res.status}: ${res.body.slice(0, 300)}`);
      } catch (err) {
        log(`${summary} -> ${TARGET} failed: ${err.message}`);
      }
      // A temporary error: the sending server keeps the mail and retries later.
      callback(smtpError(451, "4.3.0 temporary failure, try again later"));
    });
  },
});

server.on("error", (err) => log(`smtp error: ${err.message}`));
server.listen(PORT, BIND, () => {
  log(`pskit SMTP ${KEY} listening on ${BIND}:${PORT} for ${DOMAINS.length ? DOMAINS.join(", ") : "every domain"} -> ${TARGET}`);
});
