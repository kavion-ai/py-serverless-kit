# SMTP (e-mail) trigger

Search terms: smtp, email, e-mail, mail trigger, inbound mail, receive email, MX record, mail server, attachments, SES event, on-premises mail

The pskit `smtp` trigger runs a function every time an e-mail arrives for your domain. It is on-premises only: the
mail is received by an SMTP server that pskit runs as an on-prem service (an `smtp` resource), which parses each mail
and posts it to the pskit host. The handler gets sender, recipients, subject, text and HTML body, headers and
attachments, plus the same mail as an Amazon SES event.

## Write an SMTP trigger in pskit.yml

The pskit `smtp` trigger has one required key, `resource`: the key of a `resources:` entry of type `smtp`.

```yaml
provider:
  name: onprem

resources:
  inbound-mail:
    type: smtp
    external: true
    connection: {host: 203.0.113.10, port: 25, domains: inbound.example.com, hostname: mail.inbound.example.com}

functions:
  on-mail:
    handler: handler.on_mail
    events:
      - smtp: {resource: inbound-mail}     # or the shorthand: - smtp: inbound-mail
```

| Key | Meaning |
|---|---|
| `resource` | required: the `smtp` resource (the SMTP server that receives the mail) |
| `name` | filled in by pskit from the resource; you do not set it |

You normally do not write the resource by hand: creating the SMTP server (next sections) adds it. Several functions
may have an `smtp` trigger on the same server; each runs for every mail.

## Read the mail in the handler

For an `smtp` trigger `event.type == "smtp"` and `event.data` is the parsed mail.

```python
import base64
import email


def on_mail(event, ctx):
    mail = event.data
    ctx.logger.info("mail", extra={"from": mail["from"], "to": mail["to"], "subject": mail["subject"]})
    body = mail["text"] or mail["html"]
    for att in mail["attachments"]:
        data = base64.b64decode(att["content"])                   # bytes
        ctx.logger.info("attachment", extra={"file": att["filename"], "size": att["size"]})
    ses = mail["Records"][0]["ses"]                                 # code written for Amazon SES works too
    raw = email.message_from_bytes(base64.b64decode(mail["content"]))   # the raw MIME message
    return {"ok": True}
```

| Field | Meaning |
|---|---|
| `from`, `from_name` | sender address and display name |
| `to`, `cc`, `reply_to` | address lists from the headers |
| `bcc` | recipients of this delivery not in To / Cc |
| `subject`, `date`, `message_id`, `in_reply_to`, `references` | header values (`date` in ISO 8601) |
| `text`, `html` | the body (`""` when missing) |
| `headers` | `{lower-case name: value}` |
| `attachments` | `[{filename, content_type, disposition, size, content_id, checksum, content}]`, `content` in base64 |
| `envelope` | `{mail_from, rcpt_to}`, the SMTP envelope |
| `remote_ip`, `helo`, `tls`, `size`, `received_at`, `server`, `id` | about the delivery |
| `Records` | the Amazon SES receipt event (`Records[0].ses.mail`, `.ses.receipt`) |
| `content`, `content_encoding` | the raw message in base64 |

If any attached function fails, or none is attached, the sender gets a temporary error (451) and retries later: a
function may see the same mail twice. pskit does not check spam, viruses, SPF, DKIM or DMARC.

## Add an SMTP trigger in studio

The pskit studio flow creates the SMTP server and the trigger together.

1. Make sure the provider is **onprem** (the **+ SMTP server** button is disabled otherwise).
2. Sidebar **Resources** → **+ SMTP server**.
3. Fill **Resource key** (e.g. `inbound-mail`), **Domains** (e.g. `inbound.example.com`), **Where** (an SSH server,
   usually the functions' server, or this machine), **Port** (keep `25`), and tick the functions under
   **Trigger functions**. **Advanced** has **pskit host URL** and **Largest mail (MB)** (default 25, max 100).
4. Click **Create** and wait for the job to finish. The **DNS guide** opens with the records to add.
5. Or add the trigger to an existing function: **Functions** → open it → **2 Triggers** → card **E-mail (SMTP)** →
   pick the server in **SMTP server** (required). The card is shown only on premises.
6. **Save**, then deploy (**Deploy** page or `pskit deploy`) so the host knows the trigger.

## Add an SMTP trigger from the terminal

1. Create the SMTP server and attach a function:

   ```bash
   pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com \
     --attach on-mail --ssh ubuntu@203.0.113.10
   ```

   Other flags: `--server <saved server>`, `--local`, `--port`, `--functions-url`.
2. This writes the `resources:` entry and `- smtp: {resource: inbound-mail}` on `on-mail`. To add another function
   later, add the same line to it.
3. `pskit deploy`.
4. Add the DNS records (next section) and open port 25.

## DNS records and port 25 for the SMTP trigger

Mail reaches the pskit SMTP server only after two DNS records exist at your domain provider:

| Type | Name | Value |
|---|---|---|
| A | `mail.inbound.example.com` | the server's public IP |
| MX | `inbound.example.com` | `10 mail.inbound.example.com` |

Use a subdomain such as `inbound.example.com` if your root domain already receives mail (Microsoft 365, Google
Workspace). Allow inbound TCP 25 in the server's firewall. On Cloudflare set the A record to DNS only. Full setup,
architecture and troubleshooting: [../smtp/README.md](../smtp/README.md).

## Test an SMTP trigger

- Locally: `pskit invoke -f on-mail -t smtp -d '{"from": "a@b.org", "to": ["x@inbound.example.com"], "subject": "Hi", "text": "Hello"}'`.
  The short mail is expanded into the full event (headers, envelope, SES records).
- Studio: **Test** → the function → the `smtp <name>` card → edit the sample mail → **▶ Run locally**, or
  **☁ Send to <provider> / <stage>**: the test mail goes to the deployed host as if the SMTP server received it and
  runs every function attached to that server.
- Deployed: `pskit trigger -f on-mail -e 0`.
- Through the real server: send with Python's `smtplib` to the server's IP and port 25, or a real mail once DNS works.
- Logs: `pskit resources onprem logs inbound-mail` (what the SMTP server received) and `pskit logs -f --function on-mail`.

## Common SMTP trigger errors

| Message or symptom | Fix |
|---|---|
| `smtp event needs 'resource' (an smtp resource: the SMTP server that receives the mail)` | set `resource` |
| `function 'x' uses unknown resource 'y'` | create the SMTP server first |
| `<Provider> does not support 'smtp' events in pskit` | SMTP triggers need `provider.name: onprem` |
| warning `no function has an smtp trigger on this SMTP server: its mail is refused (451) until one does` | attach a function and deploy |
| senders get `451` | no function deployed with the trigger, a function failed, or the host is unreachable (check **pskit host URL**) |
| senders get `550 relay not permitted` | the address is not in **Domains** |

## See also

- [README.md](README.md)
- [../smtp/README.md](../smtp/README.md)
- [../onprem/services/README.md](../onprem/services/README.md)
- [../onprem/resources.md](../onprem/resources.md)
- [../functions/invoke-and-test.md](../functions/invoke-and-test.md)
