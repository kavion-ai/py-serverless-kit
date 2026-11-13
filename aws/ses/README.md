# Amazon SES compatible server

A self-hosted mail-sending service that speaks the **Amazon SES API** (v1 and v2) and has an **SES-style SMTP
endpoint**, in two interchangeable implementations:

| | Path | Needs | Docker image (build it) |
|---|---|---|---|
| Python | `python/server.py` + `python/sesserver/` | Python 3.9+, standard library only | `python/Dockerfile` (`python:3.12-alpine`) |
| C++ | `cpp/` (`Makefile`, `src/`, `start.sh`) | C++17 compiler, OpenSSL | `cpp/Dockerfile` (`alpine`) |
| Web console | `ui/index.html` + `ui/assets/` (ES modules, no build step) | served by both at `/ui/` | included in both images |

How the code is laid out and the rules that keep the two servers identical: [ARCHITECTURE.md](ARCHITECTURE.md).

boto3 (`ses` and `sesv2`), the AWS SDKs (JavaScript v3, Java, Go, .NET ...), the AWS CLI, nodemailer's SES transport
and any SMTP client work with it unchanged: give them its endpoint and an access key / secret key it knows. Every API
request is checked with **AWS Signature Version 4**, as AWS does.

pskit runs it as a one-click on-prem service (`ses` / `ses-cpp`, see
[docs/onprem/services/ses.md](../../docs/onprem/services/ses.md)). You can also run it on its own, as below.

## What it does

- **Sending**: `SendEmail` (simple content with attachments and custom headers, raw MIME, templates),
  `SendBulkEmail`, and the v1 `SendEmail`, `SendRawEmail`, `SendTemplatedEmail`, `SendBulkTemplatedEmail`.
- **SMTP endpoint** (port 2587): `AUTH PLAIN` / `LOGIN` with the access key ID and its **SES SMTP password** (the
  same derivation AWS uses, so existing SMTP credentials scripts work) or the secret key; STARTTLS with your
  certificate.
- **Identities**: domains and addresses, verification (`SES_VERIFY`), **DKIM signing** with a key generated per
  domain (or your own: BYODKIM), DNS checks of the DKIM and `_amazonses` records, custom MAIL FROM domains.
- **Delivery** with a queue and retries: through a **relay** (Microsoft 365, Google Workspace, Postfix, SendGrid
  ...), **direct** to the recipients' MX hosts, or **capture** (keep, send nothing). 4xx answers are retried after
  1, 5, 15, 30, then every 60 minutes for `SES_RETRY_HOURS`; 5xx answers bounce.
- **Templates** (the Handlebars subset SES uses), **configuration sets** (sending on/off, TLS policy, suppression
  override, event destinations), the account **suppression list** (permanent bounces are added), **sending quotas**
  (24-hour and per-second), **tags**, the **mailbox simulator** (`success@`, `bounce@`, `complaint@`, `ooto@`,
  `suppressionlist@simulator.amazonses.com`), sending statistics.
- **Events** (`Send`, `Delivery`, `Bounce`, `Complaint`, `DeliveryDelay`) per message, and POSTed as JSON in the SES
  event publishing format to `SES_EVENTS_URL`.
- **Web console** at `/ui/`: account dashboard, identities with their DNS records, send test email, the message log
  with per-recipient results, events and previews, templates, configuration sets, suppression list, SMTP settings.

Not supported: dedicated IPs, contact lists, the deliverability dashboard, receiving mail (use pskit's `smtp`
service), open / click tracking, and delivering events to real SNS / EventBridge / Firehose (destinations are stored;
events go to `SES_EVENTS_URL`).

## Run it

```bash
cd aws/ses

# Docker (Python or C++; build from this folder so the console is included)
docker build -f python/Dockerfile -t pskit/ses:python .
docker run -d --name ses -p 127.0.0.1:4579:4579 -p 127.0.0.1:2587:2587 -v ses-data:/data \
  -e SES_ACCESS_KEY_ID=AKIAPROD -e SES_SECRET_ACCESS_KEY='a-long-random-secret' \
  -e SES_DELIVERY=relay -e SES_RELAY_HOST=smtp.office365.com -e SES_RELAY_USER=app@corp.com \
  -e SES_RELAY_PASSWORD='...' pskit/ses:python

# or docker compose (pick one of the two services)
SES_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d ses-cpp

# or no Docker at all
SES_SECRET_ACCESS_KEY='a-long-random-secret' SES_DELIVERY=capture python python/server.py
make -C cpp && SES_SECRET_ACCESS_KEY='a-long-random-secret' cpp/build/ses-server
```

Then:

```python
import boto3

ses = boto3.client("sesv2", endpoint_url="http://127.0.0.1:4579", region_name="us-east-1",
                   aws_access_key_id="AKIAPROD", aws_secret_access_key="a-long-random-secret")
ses.create_email_identity(EmailIdentity="example.com")      # then publish the DNS records the console lists
ses.send_email(FromEmailAddress="no-reply@example.com", Destination={"ToAddresses": ["user@example.org"]},
               Content={"Simple": {"Subject": {"Data": "Hi"}, "Body": {"Text": {"Data": "Hello"}}}})
```

`python server.py --smtp-password` (or `ses-server --smtp-password`) prints the SMTP password of
`SES_SECRET_ACCESS_KEY` for `SES_REGION`.

## Settings

| Variable | Default | |
|---|---|---|
| `SES_ACCESS_KEY_ID` | `pskit` | the access key ID clients sign with (and the SMTP user name) |
| `SES_SECRET_ACCESS_KEY` | (required) | its secret access key; also the console password |
| `SES_CREDENTIALS` | | more keys: `id1:secret1,id2:secret2` |
| `SES_AUTH` | `sigv4` | `off` turns authentication off (development only) |
| `SES_PORT` / `SES_BIND` | `4579` / `0.0.0.0` | where the HTTP API and console listen |
| `SES_DATA_DIR` | `./data` (`/data` in the images) | holds `ses.json` and `messages/` |
| `SES_REGION` / `SES_ACCOUNT_ID` | `us-east-1` / `000000000000` | for ARNs and the SMTP password |
| `SES_UI` / `SES_UI_PASSWORD` / `SES_UI_DIR` | `on` / / `ui` next to the server, else `../ui` | the web console |
| `SES_SMTP` / `SES_SMTP_PORT` / `SES_SMTP_BIND` | `on` / `2587` / `SES_BIND` | the SMTP endpoint |
| `SES_TLS_CERT` / `SES_TLS_KEY` | | PEM files: the SMTP endpoint offers STARTTLS |
| `SES_SMTP_REQUIRE_TLS` | `off` | `on`: no AUTH before STARTTLS |
| `SES_SMTP_HOST` | | the SMTP host name the console shows |
| `SES_DELIVERY` | `relay` with `SES_RELAY_HOST`, else `direct` | `relay`, `direct` or `capture`: the mode the server starts in (the console's *Delivery settings* override it) |
| `SES_RELAY_HOST` / `SES_RELAY_PORT` | / `587` | the relay (smarthost) |
| `SES_RELAY_USER` / `SES_RELAY_PASSWORD` | | the relay's login (AUTH needs TLS) |
| `SES_RELAY_TLS` / `SES_RELAY_TLS_VERIFY` | `tls` on 465, else `starttls` / `on` | `starttls`, `tls` or `none`; certificate check |
| `SES_HELO_NAME` | this host's name | the name it greets other servers with; match the server's reverse DNS |
| `SES_DIRECT_PORT` | `25` | the MX hosts' port (direct delivery) |
| `SES_DNS_SERVER` | `/etc/resolv.conf`, else `1.1.1.1` | `ip[:port]` of the DNS server for MX and TXT lookups |
| `SES_DELIVERY_THREADS` | `4` | messages delivered at once |
| `SES_RETRY_HOURS` | `12` | how long 4xx answers are retried before the recipient bounces |
| `SES_RETENTION_DAYS` | `14` | how long messages stay in the console (at least 1) |
| `SES_VERIFY` | `auto` | `auto` (new identities are verified), `dns`, `manual` (the console verifies) or `off` (any From) |
| `SES_SANDBOX` | `off` | `on`: recipients must be verified too |
| `SES_MAX_24H` / `SES_MAX_RATE` | `50000` / `14` | recipients per 24 hours / per second |
| `SES_MAX_MESSAGE_MB` | `40` | the largest message |
| `SES_DKIM_CHECK` | `on` | look up DKIM and verification records in DNS (`off`: DKIM signs at once) |
| `SES_EVENTS_URL` / `SES_EVENTS_TOKEN` | | POST every event as JSON here, with `Authorization: Bearer <token>` |

## Choosing the delivery mode in the console

**Delivery settings** in the console picks the mode: *Capture*, *Relay* (with provider presets for Microsoft 365,
Google Workspace, SendGrid, Amazon SES and Mailgun, or your own host, port, TLS and login) or *Direct* (with the
HELO name). *Test connection* tries the settings without sending anything (relay: connect, TLS, log in; direct:
reach an MX host on port 25). *Save* applies them at once, and queued or delayed mail is retried right away. The
choice is kept in `ses.json` (the relay password too, mode 600; it is never shown again) and wins over the `SES_*`
variables until *Reset to server default*.

## Sending real mail: DNS and network

1. **Create the domain identity** and publish the records its console page lists at your DNS provider: the DKIM
   TXT record `<selector>._domainkey.<domain>` (`v=DKIM1; k=rsa; p=...`), SPF (`v=spf1 a:<your HELO name> ~all`,
   or your relay's include) and DMARC (`_dmarc.<domain>`). DKIM signing starts as soon as the record is found
   (checked every 10 minutes for 72 hours, or *Check DNS now*).
2. **Direct delivery** needs outbound TCP 25 (AWS, Azure and GCP block it by default: ask them to open it, or use a
   relay), a static public IP whose reverse DNS (PTR) matches `SES_HELO_NAME`, and an IP that is not on block lists.
   A relay avoids all three.
3. **Open** the API and SMTP ports only to the machines that send (security group / firewall).

## Data

`SES_DATA_DIR/ses.json` holds the account settings, the delivery settings chosen in the console (with the relay
password), identities (with their DKIM private keys), templates, configuration sets and the suppression list (mode
600). Each message is `messages/<id>.json` (envelope, status per
recipient, events) and `messages/<id>.eml` (the message as sent). Back the folder up; both servers read and write the
same files, so you can switch between them.
