# Amazon SES compatible server (Python / C++)

Search terms: Amazon SES compatible, send email on premises, SES SMTP endpoint, sesv2, send_email, DKIM, relay,
smarthost, ses-cpp, mail server, transactional email

pskit ships its own Amazon SES compatible server for **sending** mail, in two flavors: **Amazon SES compatible
(Python)** (`--service ses`) and **(C++)** (`--service ses-cpp`). boto3 (`ses` / `sesv2`), the AWS SDKs, nodemailer,
the AWS CLI and any SMTP client work with it. API requests are signed with SigV4: the service's user is the access key
ID, its password the secret access key. The SMTP endpoint takes the same user with the SES SMTP password. This page
covers creating it and using it as a resource; the API coverage, delivery and DNS are in [the SES compatible server
reference](../aws-compatible/ses.md). To **receive** mail and run functions with it, use the [SMTP server](smtp.md).

## Amazon SES compatible at a glance

| | |
|---|---|
| `--service` | `ses` / `ses-cpp` |
| Studio card | **Mail** > **Amazon SES compatible (Python)** / **Amazon SES compatible (C++)** |
| Docker image | `python:3.12-alpine` / `alpine:3.20` (the C++ server is compiled in the container on its first start, a few minutes, and kept in the volume) |
| Ports | `4579` (API and console), `2587` (SMTP endpoint; moves with the main port) |
| Use as | `custom` (resource type `custom`, connection driver `ses`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | SES console on port `4579` at `/ui/` (the service's user and password) |

## Create it from the terminal

```bash
# Development: mail is kept in the console, nothing is sent (the default)
pskit resources onprem create mail --service ses --save

# Production through your mail provider (Microsoft 365, Google Workspace, SendGrid, Postfix ...)
export RELAY_PW='...'
pskit resources onprem create mail --service ses --server prod1 \
  --relay smtp.office365.com:587 --relay-user app@corp.com --relay-password-env RELAY_PW --save

# Production straight to the recipients' mail servers (needs outbound port 25 and DNS, see the reference)
pskit resources onprem create mail --service ses-cpp --server prod1 --ses-delivery direct \
  --helo-name mail.corp.com --ses-verify dns --save
```

| Option | |
|---|---|
| `--ses-delivery capture\|direct\|relay` | default `capture`, or `relay` when `--relay` is given |
| `--relay HOST[:PORT]` | the relay; port 587 by default |
| `--relay-user`, `--relay-password-env NAME` | the relay's login (the password goes to the env file, never to `pskit.yml`) |
| `--relay-tls starttls\|tls\|none` | default `tls` on port 465, else `starttls` |
| `--ses-verify auto\|dns\|manual\|off` | how sender identities are verified (default `auto`: at once) |
| `--helo-name NAME` | the name it greets other mail servers with (match the server's reverse DNS) |

To change these later, remove the service and create it again with the same key; the data volume (identities, DKIM
keys, templates, messages) stays.

## What the resource gives your code

The env file (`.env.onprem`) gets, for key `mail`:

| Variable | |
|---|---|
| `PSKIT_MAIL_URL`, `PSKIT_MAIL_REGION` | the API endpoint and region (`us-east-1`) |
| `PSKIT_MAIL_ACCESS_KEY`, `PSKIT_MAIL_SECRET_KEY` | the SigV4 keys |
| `PSKIT_MAIL_SMTP_HOST`, `PSKIT_MAIL_SMTP_PORT` | the SMTP endpoint |
| `PSKIT_MAIL_SMTP_USER`, `PSKIT_MAIL_SMTP_PASSWORD` | the SMTP login (the SES SMTP password of the secret key) |

```python
import os

import boto3


def handler(event, context):
    ses = boto3.client("sesv2", endpoint_url=os.environ["PSKIT_MAIL_URL"], region_name="us-east-1",
                       aws_access_key_id=os.environ["PSKIT_MAIL_ACCESS_KEY"],
                       aws_secret_access_key=os.environ["PSKIT_MAIL_SECRET_KEY"])
    out = ses.send_email(FromEmailAddress="no-reply@example.com",
                         Destination={"ToAddresses": [event.data["email"]]},
                         Content={"Template": {"TemplateName": "welcome",
                                               "TemplateData": '{"name": "%s"}' % event.data["name"]}})
    return {"message_id": out["MessageId"]}
```

*How to use* (studio or `pskit resources onprem usage mail`) shows the same for the AWS SDK for JavaScript, SMTP and
the AWS CLI, with your service's values.

## First steps after creating it

1. Open the console (`http://<address>:4579/ui/`, the service's user and password).
2. **Identities > Create identity**: your domain. Publish the DKIM, SPF and DMARC records it lists.
3. **Send test email** to `success@simulator.amazonses.com` (never leaves the server) and to yourself.
4. **Messages** shows each message, its per-recipient result (the receiving server's answer) and its events.
