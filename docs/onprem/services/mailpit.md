# Mailpit (SMTP)

Search terms: Mailpit, SMTP test server, fake SMTP, mailbox, email testing, 1025, 8025

Mailpit is an SMTP server that keeps every mail for inspection in a web mailbox (port 8025). Use it to test code that
**sends** mail. It has no authentication: keep it on a private network.

## Mailpit at a glance

The Mailpit service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `mailpit` |
| Studio card | **Automation, web & tools** > **Mailpit (SMTP)** |
| Docker image | `axllent/mailpit:latest` |
| Port | `1025` (also `8025`). Extra ports move with the main port |
| Use as | `custom` (Service, resource type `custom`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | not persisted (a restart empties it) |
| Backup | no |
| Web UI | Mailbox on port `8025` at `/` (no login) |
| Console | Mailpit API (GET path) |

## Create Mailpit in studio

The studio creates Mailpit from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Automation, web & tools**, click the **Mailpit (SMTP)** card. The drawer
   title changes to *Create Mailpit (SMTP)*.
4. **Resource key**: type `mail` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `1025`, or type another one if that port is taken.
7. **Security**: Mailpit runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or
   *Network (0.0.0.0)* and limit the port with the firewall.
8. **Web UI**: built in (Mailbox); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Mailpit from the terminal

`pskit resources onprem create KEY --service mailpit` starts Mailpit and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create mail --service mailpit --save                 # here, or the deploy target
pskit resources onprem create mail --service mailpit --server edge1 --save   # a saved server
pskit resources onprem create mail --service mailpit --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Mailpit

Creating Mailpit adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  mail:
    type: custom
    external: true
    connection:
      smtp_host: 10.0.0.5
      smtp_port: 1025
      web_url: http://10.0.0.5:8025
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Mailpit from a handler

A handler reaches Mailpit through `resource("mail")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import smtplib
from email.message import EmailMessage

from py_serverless_kit import resource


def send_test_mail(event, ctx):
    r = resource("mail")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "app@example.com", "you@example.com", "Hello from pskit"
    msg.set_content("It works.")
    with smtplib.SMTP(r["smtp_host"], int(r["smtp_port"])) as smtp:
        smtp.send_message(msg)
    return {"sent": True}
```

No library to add: `smtplib` is in the standard library.

`pskit resources usage mail` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage mail` shows how to connect from any other program.

## Open the Mailpit web UI, console and terminal

The Mailpit row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Mailbox on port `8025` at `/` (no login).
  **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** runs one command at a time with **Mailpit API (GET path)** and the service's credentials, for example
  `/api/v1/info`, `/api/v1/messages?limit=5`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status mail --reveal      # state, health, endpoint, credentials
pskit resources onprem usage mail                # connect from any program
pskit resources onprem logs mail -n 100
pskit resources onprem gui mail                  # print the web UI links (starts a companion)
pskit resources onprem gui mail --check
pskit resources onprem console mail "/api/v1/info"
pskit resources onprem terminal mail
pskit resources onprem tunnel mail                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Mailpit

Mailpit has no backup command in pskit (it keeps data in memory only).

To remove Mailpit: **Remove** on the row, then **Remove, keep data**. The container is deleted, its variables leave
the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources table, **Delete**
on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove mail --save                 # keep the data volume
pskit resources onprem remove mail --delete-data --save   # delete it too
```

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
