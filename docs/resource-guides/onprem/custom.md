# Other on-premises services (`type: custom`)

`custom` covers anything else functions talk to: an SMTP server, LDAP / Active Directory, an internal REST API, an
Elasticsearch cluster, a file share. pskit only hands `connection` values to handlers (`external: true` is required).

Not to be confused with the **custom driver** (`options.driver: custom`), which plugs your own class into a `queue` or
`storage` resource so it can trigger functions: see [queue.md](queue.md#rabbitmq-or-kafka-nats--via-a-custom-driver).

## The recipe

1. Find the service's address and a service account in its admin console.
2. Keep secrets in the host's environment (see [README](README.md#secrets-name_env)).
3. Put everything else, plus the secret's variable **name**, in `connection`.

## Example: SMTP server

Collect from the mail server's admin (Postfix, Exchange, Microsoft 365, SendGrid, ...): host, port (587 for STARTTLS,
465 for TLS), a user and its password or app password.

```yaml
resources:
  mail:
    type: custom
    external: true
    connection:
      host: smtp.internal
      port: 587
      user: noreply@example.com
      from_address: noreply@example.com
      password_env: SMTP_PASSWORD
    functions: [notify]
```

```python
import smtplib
from email.message import EmailMessage

from py_serverless_kit import resource


def notify(event, ctx):
    mail = resource("mail")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = mail["from_address"], "ops@example.com", "Order paid"
    msg.set_content(str(event.json()))
    with smtplib.SMTP(mail["host"], int(mail["port"])) as smtp:
        smtp.starttls()
        smtp.login(mail["user"], ctx.env[mail["password_env"]])
        smtp.send_message(msg)
```

## Example: an internal REST API

```yaml
resources:
  erp:
    type: custom
    external: true
    connection:
      base_url: https://erp.internal/api/v2
      timeout_seconds: 10
      token_env: ERP_TOKEN
```

```python
import json
import urllib.request

from py_serverless_kit import resource


def sync(event, ctx):
    erp = resource("erp")
    req = urllib.request.Request(erp["base_url"] + "/orders",
                                 headers={"Authorization": f"Bearer {ctx.env[erp['token_env']]}"})
    with urllib.request.urlopen(req, timeout=float(erp["timeout_seconds"])) as resp:
        return json.load(resp)
```

## Test

```bash
pskit validate
pskit resources send --list    # PSKIT_RESOURCE_* variables and a Python / Node.js snippet per custom resource
SMTP_PASSWORD=... pskit invoke -f notify -d '{"order_id": 1}'
pskit deploy
```
