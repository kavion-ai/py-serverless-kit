"""Category A (docs Q&A and how-to), batch 11: on-premises e-mail triggers (SMTP) and secret managers.
Hand-written; assembled by tools/assemble.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from assemble import D, S  # noqa: E402


def A(n, **kw):
    return dict(id=f"a_qa-{n:04d}", category="a_qa", **kw)


SM = "docs/smtp/README.md"
SE = "docs/resource-guides/onprem/secrets.md"

CONVERSATIONS = [
    A(201, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SM}#create-it"],
      user="Our company mail runs on Microsoft 365 for example.com. We want invoices@example.com mails to trigger a function. Should the pskit SMTP server get the MX of example.com?",
      steps=[S("search_docs", query="smtp trigger root domain microsoft 365 subdomain",
               docs=[D(SM, "create-it", end="stop every mailbox of the company from receiving mail.")])],
      final="""No. Changing the root domain's MX would stop every mailbox of the company from receiving mail. Use a **subdomain** such as `inbound.example.com` for the SMTP server [docs/smtp/README.md#create-it].

**In studio**
1. Open **Resources** and click **+ SMTP server**.
2. *Domains*: `inbound.example.com`. Pick *Where* (usually the functions' server), keep *Port* 25, and tick the function under *Trigger functions*.
3. Open the service's **DNS guide** and add the A and MX records for the subdomain.

**In the terminal**
```bash
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-invoice --server app-1 --save
pskit deploy -s prod
```

Then have invoices sent to an address like `invoices@inbound.example.com`, or set a forwarding rule in Microsoft 365 from `invoices@example.com` to it."""),

    A(202, provider="onprem", stage="prod", mode="ask", page="Resources", persona="informal_non_native",
      sources=[f"{SM}#dns-records-at-your-domain-provider"],
      user="i add MX and A record in cloudflare for my smtp trigger but mails not come. cloud icon is orange",
      steps=[S("search_docs", query="dns records smtp cloudflare proxy",
               docs=[D(SM, "dns-records-at-your-domain-provider", start="- Most providers want only", end="sometimes hours.")])],
      final="""Set the A record to **DNS only** (grey cloud). Cloudflare's proxy (orange cloud) doesn't carry mail [docs/smtp/README.md#dns-records-at-your-domain-provider].

Then check the records:
```bash
nslookup -type=mx inbound.example.com
nslookup mail.inbound.example.com
```
The MX must show the A record's name, and the A record must resolve to the server's public IP. Changes can take a few minutes, sometimes hours.

Also make sure inbound TCP 25 is open on the server."""),

    A(203, provider="onprem", stage="prod", mode="auto", page="Resources", persona="terse_expert",
      sources=[f"{SM}#port-25"],
      user="postfix already owns :25 on the box. smtp trigger server anyway?",
      steps=[S("search_docs", query="port 25 already used postfix smtp server",
               docs=[D(SM, "port-25")])],
      final="""Yes. Create the SMTP server on another port and forward 25 to it [docs/smtp/README.md#port-25]:
```bash
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --port 2525 --attach on-mail --save
sudo iptables -t nat -A PREROUTING -p tcp --dport 25 -j REDIRECT --to-port 2525
```
Other mail servers always connect to 25. If Postfix must keep receiving on 25 for other domains, use a separate IP or server for the pskit SMTP server instead."""),

    A(204, provider="onprem", stage="dev", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{SM}#what-the-handler-receives"],
      user="handler only: save every pdf attachment of the incoming mail to disk, python",
      steps=[S("search_docs", query="smtp event attachments content base64",
               docs=[D(SM, "what-the-handler-receives", end="| `envelope` |", words=400)])],
      final="""**In code**
```python
from __future__ import annotations

import base64
from pathlib import Path


def on_mail(event, ctx):
    mail = event.data
    saved = []
    for att in mail["attachments"]:
        if att["content_type"] == "application/pdf":
            path = Path("/tmp") / Path(att["filename"] or "file.pdf").name
            path.write_bytes(base64.b64decode(att["content"]))
            saved.append(str(path))
    ctx.logger.info("mail", extra={"from": mail["from"], "subject": mail["subject"], "saved": saved})
    return {"saved": saved}
```
`event.type` is `smtp`. Each attachment has `filename`, `content_type`, `size` and `content` (base64) [docs/smtp/README.md#what-the-handler-receives]. `Path(...).name` keeps a sender's file name from pointing outside the folder."""),

    A(205, provider="onprem", stage="prod", mode="ask", page="Code", persona="aws_migrator",
      sources=[f"{SM}#what-the-handler-receives"],
      user="We receive mail with Amazon SES → Lambda today and parse event['Records'][0]['ses']. If we move that Lambda to pskit on-prem with an smtp trigger, do we rewrite the parsing?",
      steps=[S("search_docs", query="smtp event amazon ses records compatible",
               docs=[D(SM, "what-the-handler-receives", start="| `Records` |", end="Those SES verdicts are `GRAY`.")])],
      final="""Mostly no. `event.data` also carries the Amazon SES receipt event: `Records[0].eventSource` is `aws:ses`, with `.ses.mail` (`source`, `destination`, `headers`, `commonHeaders`, `messageId`, `timestamp`) and `.ses.receipt` (`recipients`, verdicts, `action`) [docs/smtp/README.md#what-the-handler-receives].

**In code**
```python
from __future__ import annotations


def on_mail(event, ctx):
    ses = event.data["Records"][0]["ses"]
    return {"subject": ses["mail"]["commonHeaders"]["subject"], "to": ses["receipt"]["recipients"]}
```
The one change: read it from `event.data`, not the raw Lambda event. The raw MIME message is in `content` (base64), as an SES → SNS action with `encoding: BASE64` delivers it.

pskit doesn't check spam, viruses, SPF, DKIM or DMARC, so those verdicts are always `GRAY`."""),

    A(206, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{SM}#troubleshooting"],
      user="sender bounce says: 451 temporary failure\nsmtp server for inbound.example.com is running",
      steps=[S("search_docs", query="smtp 451 temporary failure",
               docs=[D(SM, "troubleshooting", end="| Nothing arrives |")])],
      final="""`451` means the SMTP server got the mail but the host didn't take it. Three causes [docs/smtp/README.md#troubleshooting]:
1. **No function has the trigger yet.** Deploy, so the host knows it.
2. **A function failed.** Check the host logs.
3. **The host is unreachable.** Check *pskit host URL* and `admin_token`.

**In the terminal**
```bash
pskit deploy -s prod
pskit resources onprem logs inbound-mail
pskit logs --level error
```
The first log shows every mail the SMTP server received and what the host answered. The sender retries later, so no mail is lost."""),

    A(207, provider="onprem", stage="prod", mode="ask", page="Resources", persona="pasted_error",
      sources=[f"{SM}#troubleshooting", f"{SM}#change-it"],
      user="552 message exceeds fixed maximum message size\npeople send big scans (40 MB)",
      steps=[S("search_docs", query="552 message size smtp",
               docs=[D(SM, "troubleshooting", start="| `552 message exceeds", end="| `552 message exceeds")]),
             S("search_docs", query="change smtp server settings",
               docs=[D(SM, "change-it")])],
      final="""Raise *Largest mail (MB)*. The default is 25, and it goes up to 100 [docs/smtp/README.md#troubleshooting]. To change a setting, remove the service and create it again with the same key [docs/smtp/README.md#change-it].

**In the terminal**
```bash
pskit resources onprem remove inbound-mail
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --max-size-mb 60 --attach on-mail --save
```

**In studio**
1. **Resources > On-prem services**: **Remove** the SMTP server.
2. **Resources > + SMTP server** with the same key, and set *Largest mail (MB)* under *Advanced*."""),

    A(208, provider="onprem", stage="dev", mode="auto", page="Functions", persona="terse_expert",
      sources=[f"{SM}#change-it"],
      user="second function archive-mail should also run per inbound mail. need to recreate smtp service?",
      steps=[S("search_docs", query="add another function smtp trigger",
               docs=[D(SM, "change-it")])],
      final="""No. Add the trigger to the function and deploy. The SMTP server doesn't change [docs/smtp/README.md#change-it].

**In code**
```yaml
functions:
  archive-mail:
    handler: app.mail.archive
    events:
      - smtp: {resource: inbound-mail}
```

**In the terminal**
```bash
pskit deploy -s dev
```
Recreate the service only for other domains, another port, a new host URL, or a changed `admin_token`."""),

    A(209, provider="onprem", stage="prod", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SM}#what-the-handler-receives", f"{SM}#how-it-works"],
      user="will the pskit mail server block spam for me? and can strangers use it to send mail?",
      steps=[S("search_docs", query="smtp spam spf dkim relay",
               docs=[D(SM, "what-the-handler-receives", start="pskit does not scan for spam"),
                     D(SM, "how-it-works", start="- It accepts mail only for the domains you list", end="Nobody can send mail *through* it.")])],
      final="""- **Spam**: no. pskit doesn't scan for spam or viruses, and it doesn't check SPF, DKIM or DMARC [docs/smtp/README.md#what-the-handler-receives]. Filter in your handler if you need to.
- **Sending through it**: no. It accepts mail only for the domains you list (and their subdomains), and nobody can send mail through it. It's never a relay [docs/smtp/README.md#how-it-works]."""),

    A(210, provider="onprem", stage="prod", mode="ask", page="Code", persona="detailed_spec",
      sources=[f"{SM}#how-it-works"],
      user="Our mail handler creates a ticket per mail. Can the same mail ever arrive twice, and what happens if the handler throws?",
      steps=[S("search_docs", query="smtp function fails retry same mail twice",
               docs=[D(SM, "how-it-works", start="- Each mail is posted to the pskit host", end="but a function may see the same mail twice.")])],
      final="""Yes, it can arrive twice. If a function fails, or none is attached yet, the sender gets a temporary error (`451`) and tries again later. No mail is lost, but a function may see the same mail twice [docs/smtp/README.md#how-it-works].

So make ticket creation idempotent, for example keyed on the mail's `message_id`:
```python
from __future__ import annotations


def on_mail(event, ctx):
    mail = event.data
    key = mail["message_id"] or mail["id"]
    ctx.logger.info("ticket", extra={"key": key, "subject": mail["subject"]})
    return {"ticket": key}
```
Store the key with the ticket and skip mails you already saw."""),

    A(211, provider="onprem", stage="dev", mode="ask", page="Code", persona="informal_non_native",
      sources=[f"{SE}#secret-managers-on-premises", f"{SE}#add-and-read-secrets"],
      user="my secret stripe have 2 field key and webhook. how i read only webhook in handler?",
      steps=[S("search_docs", query="get_secret field json secret",
               docs=[D(SE, "secret-managers-on-premises", end="cached for 60 seconds per function instance.", words=160),
                     D(SE, "add-and-read-secrets", start="A secret with one field named `value`")])],
      final="""Pass the field name as the second argument [docs/resource-guides/onprem/secrets.md#secret-managers-on-premises].

**In code**
```python
from __future__ import annotations

from py_serverless_kit import get_secret, get_secrets


def handler(event, ctx):
    webhook = get_secret("stripe", "webhook")
    both = get_secrets("stripe")
    return {"has_webhook": bool(webhook), "fields": sorted(both)}
```
A secret with one field named `value` is a plain secret, and `get_secret(name)` returns it. With several fields, `get_secret(name, field)` picks one [docs/resource-guides/onprem/secrets.md#add-and-read-secrets]. Values are cached for 60 seconds per function instance."""),

    A(212, provider="onprem", stage="prod", mode="ask", page="Code", persona="terse_expert",
      sources=[f"{SE}#one-click-openbao-pskits-secrets-manager-or-localstack"],
      user="two secret stores: openbao 'secrets' and aws-compatible 'aws-secrets'. how do I pick the store in get_secret?",
      steps=[S("search_docs", query="get_secret store default secrets key",
               docs=[D(SE, "one-click-openbao-pskits-secrets-manager-or-localstack", start="Name it **`secrets`**", end="getSecret(\"db-password\", { store: \"aws-secrets\" })")])],
      final="""The store keyed `secrets` is the default, so `get_secret("db-password")` reads OpenBao. For the other one, pass `store=` [docs/resource-guides/onprem/secrets.md#one-click-openbao-pskits-secrets-manager-or-localstack]:

```python
from __future__ import annotations

from py_serverless_kit import get_secret


def handler(event, ctx):
    db = get_secret("db-password")
    legacy = get_secret("db-password", store="aws-secrets")
    return {"same": db == legacy}
```
Node.js: `getSecret("db-password", { store: "aws-secrets" })`."""),

    A(213, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SE}#an-existing-vault-openbao-or-aws-secrets-manager"],
      user="We already run a hardened HashiCorp Vault at vault.example.com:8200. We don't want pskit to start another one. How do the on-prem functions read from ours with get_secret?",
      steps=[S("search_docs", query="existing vault get_secret variables",
               docs=[D(SE, "an-existing-vault-openbao-or-aws-secrets-manager")])],
      final="""Set the store variables yourself, in the env file, `functions.*.environment`, or the host's environment [docs/resource-guides/onprem/secrets.md#an-existing-vault-openbao-or-aws-secrets-manager]:
- `PSKIT_SECRETS_DRIVER`: `vault`
- `PSKIT_SECRETS_URL`: `https://vault.example.com:8200`
- `PSKIT_SECRETS_TOKEN`: a token for the functions
- optional `PSKIT_SECRETS_MOUNT`

**In code**
```yaml
provider:
  name: onprem
  options:
    env_file: .env.onprem
```
Put the four lines in `.env.onprem` (kept out of git). The host loads it at start, and `get_secret("db-password")` then reads your Vault. No handler change.

Give the token only the policy the functions need, and let the functions' server reach port 8200."""),

    A(214, provider="onprem", stage="dev", mode="ask", page="Code", persona="beginner",
      sources=[f"{SE}#an-existing-vault-openbao-or-aws-secrets-manager"],
      user="i dont have any secret manager yet. does get_secret just fail then?",
      steps=[S("search_docs", query="get_secret without secret manager environment",
               docs=[D(SE, "an-existing-vault-openbao-or-aws-secrets-manager", start="| Environment only |", end="| Environment only |")])],
      final="""No. Without a store, `get_secret("db-password")` reads the environment: first `PSKIT_SECRET_DB_PASSWORD`, then `DB_PASSWORD` [docs/resource-guides/onprem/secrets.md#an-existing-vault-openbao-or-aws-secrets-manager].

So you can start with a line in the env file (`provider.options.env_file`), and move to OpenBao later without changing the handler:
```bash
pskit resources onprem create secrets --service openbao --save
```"""),

    A(215, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{SE}#troubleshooting"],
      user="vault: reading 'db-password' failed (403)",
      steps=[S("search_docs", query="vault reading failed 403",
               docs=[D(SE, "troubleshooting")])],
      final="""The token is wrong. `PSKIT_<KEY>_TOKEN` must match the OpenBao password [docs/resource-guides/onprem/secrets.md#troubleshooting]. For the default store that's `PSKIT_SECRETS_TOKEN` in the env file.

1. See the service's credentials:
```bash
pskit resources onprem status secrets --reveal
```
2. Put the matching token in the env file, then deploy again so the host loads it:
```bash
pskit deploy -s prod
```"""),

    A(216, provider="onprem", stage="prod", mode="ask", page="Logs", persona="pasted_error",
      sources=[f"{SE}#troubleshooting"],
      user="secret store 192.0.2.50:8200 is unreachable\n\nopenbao is on db-1, functions on app-1",
      steps=[S("search_docs", query="secret store unreachable 8200",
               docs=[D(SE, "troubleshooting")])],
      final="""app-1 can't reach port 8200 on db-1. Open 8200 from the functions' server (app-1) to the secrets server (db-1), or run OpenBao on the same server as the functions [docs/resource-guides/onprem/secrets.md#troubleshooting].

```bash
pskit firewall --server db-1
```
lists the rule, with the `ufw` command."""),

    A(217, provider="onprem", stage="prod", mode="ask", page="Resources", persona="detailed_spec",
      sources=[f"{SE}#one-click-openbao-pskits-secrets-manager-or-localstack"],
      user="Security review question: the one-click OpenBao unseals itself on restart. Where is the unseal key, and is this OK for production?",
      steps=[S("search_docs", query="openbao unseal key volume production",
               docs=[D(SE, "one-click-openbao-pskits-secrets-manager-or-localstack", start="OpenBao's password", end="point pskit at it (below).")])],
      final="""The unseal key is kept in the data volume, so every restart unseals by itself. The service password becomes a root token. That's convenient on one server, but the volume and its backups then hold the key, so protect them like the secrets themselves [docs/resource-guides/onprem/secrets.md#one-click-openbao-pskits-secrets-manager-or-localstack].

For a hardened production setup (several unseal keys, auto-unseal with a KMS, policies per app), run OpenBao or Vault yourself and point pskit at it with `PSKIT_SECRETS_DRIVER` set to `vault`, `PSKIT_SECRETS_URL` and `PSKIT_SECRETS_TOKEN`. Handler code stays the same."""),

    A(218, provider="onprem", stage="dev", mode="ask", page="Resources", persona="terse_expert",
      sources=[f"{SE}#add-and-read-secrets"],
      user="cli only: write secret stripe with fields key + webhook into the openbao 'secrets' service",
      steps=[S("search_docs", query="put secret openbao console kv put",
               docs=[D(SE, "add-and-read-secrets", end="| Code |")])],
      final="""**In the terminal**
```bash
pskit resources onprem console secrets "kv put secret/stripe key=<key> webhook=<webhook>"
pskit resources onprem console secrets "kv get secret/stripe"
```
Replace the placeholders with the real values. The console runs `bao` with the service's login [docs/resource-guides/onprem/secrets.md#add-and-read-secrets]. Shell history keeps the values, so clear it afterwards or use the studio's **Browse secrets** instead."""),

    A(219, provider="onprem", stage="dev", mode="auto", page="Resources", persona="aws_migrator",
      sources=[f"{SE}#pskits-aws-secrets-manager-compatible-server"],
      user="our code uses boto3 secretsmanager.get_secret_value. is there an on-prem Secrets Manager it can talk to unchanged?",
      steps=[S("search_docs", query="aws secrets manager compatible server boto3 on-prem",
               docs=[D(SE, "pskits-aws-secrets-manager-compatible-server", end="Rotation and replica regions are not supported.", words=330)])],
      final="""Yes: pskit's **AWS Secrets Manager compatible** server. It checks every request's SigV4 signature, and code written for AWS runs unchanged with `endpoint_url` [docs/resource-guides/onprem/secrets.md#pskits-aws-secrets-manager-compatible-server].

**In the terminal**
```bash
pskit resources onprem create aws-secrets --service secretsmanager --save
```

**In code**
```python
from __future__ import annotations

import os

import boto3

env = os.environ
sk = env["PSKIT_AWS_SECRETS_SECRET_KEY"]
sm = boto3.client("secretsmanager", endpoint_url=env["PSKIT_AWS_SECRETS_URL"], region_name="us-east-1",
                  aws_access_key_id=env["PSKIT_AWS_SECRETS_ACCESS_KEY"],
                  aws_secret_access_key=sk)
value = sm.get_secret_value(**{"SecretId": "prod/db"})["SecretString"]
```
The variables come from the env file. Rotation and replica regions are not supported; resource policies are stored but not enforced."""),

    A(220, provider="onprem", stage="dev", mode="ask", page="Resources", persona="beginner",
      sources=[f"{SE}#browse-secrets-in-the-studio"],
      user="the openbao web page says UI is not available. where do i see my secrets then?",
      steps=[S("search_docs", query="openbao ui not available browse secrets studio",
               docs=[D(SE, "browse-secrets-in-the-studio")])],
      final="""OpenBao's release images have no web UI. Use the studio's browser instead [docs/resource-guides/onprem/secrets.md#browse-secrets-in-the-studio].

**In studio**
1. Open **Resources > On-prem services**.
2. Click **Browse secrets** on the OpenBao row.
3. Open a folder and a secret. Values stay hidden until you click *Show values*. You can also copy values, see versions, and add, edit or delete secrets."""),
]
