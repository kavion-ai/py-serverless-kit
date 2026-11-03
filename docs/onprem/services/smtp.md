# SMTP server (receive mail, Node.js)

Search terms: SMTP server, receive mail, inbound email, MX record, DNS, smtp trigger, port 25, mail to function

The SMTP server **receives** mail for your domains and runs the functions attached to it with each mail (from, to, cc,
subject, text, html, headers and attachments, also in the Amazon SES event shape). It is a Node.js container
(`smtp-server` and `mailparser`). It never relays: mail for other domains is refused. The full guide, with the DNS
records, is [SMTP: receive mail](../../smtp/README.md).

## SMTP server at a glance

The SMTP server service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `smtp` |
| Studio card | **Mail (receive e-mail, run functions)** > **SMTP server (receive mail, Node.js)** |
| Docker image | `node:22-alpine` |
| Port | `25` |
| Use as | `smtp` (SMTP server (mail trigger), resource type `smtp`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | none |
| Console | no client: use *Shell in the container* (`sh`) |

## Create SMTP server in studio

The studio creates SMTP server from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ SMTP server** in the page header (or **+ On-prem service**, then the card below).
3. In the *Create a service* drawer, under **Mail (receive e-mail, run functions)**, click the **SMTP server (receive
   mail, Node.js)** card. The drawer title changes to *Create SMTP server (receive mail, Node.js)*.
4. **Resource key**: type `inbound-mail` (the form suggests a free name). Handlers and triggers use this key.
5. **Domains**: the domains mail is sent to, for example `inbound.example.com` (comma separated).
6. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
7. **Port**: leave empty for `25`, or type another one if that port is taken.
8. **Security**: nothing to fill in: senders do not log in and only mail for your domains is accepted.
9. **Trigger functions**: tick the functions that run for each mail. Each gets an event on `resource: inbound-mail`.
10. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker
    image**, **pskit host URL** and **Largest mail (MB)** (default 25).
11. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
12. The resource and the triggers are added to the draft. Click **Save** in the top bar to write `pskit.yml`, then
    deploy.

## Create SMTP server from the terminal

`pskit resources onprem create KEY --service smtp` starts SMTP server and prints the `pskit.yml` entry; add `--save`
to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --server edge1 --attach on-mail --save
pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --functions-url http://10.0.0.5:8080 --max-size-mb 10 --server edge1 --save
```

- `-a / --attach FUNCTION` (repeatable) adds the trigger to that function.
- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for SMTP server

Creating SMTP server adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env
file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5`
and the defaults.

```yaml
resources:
  inbound-mail:
    type: smtp
    external: true
    connection:
      host: 10.0.0.5
      port: 25
      domains: inbound.example.com
      hostname: mail.inbound.example.com
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use SMTP server from a handler

A handler reaches SMTP server through `resource("inbound-mail")`, which returns the connection values pskit passes to
bound functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
def on_mail(event, ctx):
    """Trigger: smtp: {resource: inbound-mail}. event.data is the mail."""
    mail = event.data
    ctx.logger.info("mail", extra={"from": mail["from"], "to": mail["to"], "subject": mail["subject"]})
    body = mail["text"] or mail["html"]
    return {"ok": True, "length": len(body or "")}
```

```yaml
functions:
  on-mail:
    handler: app.handlers.on_mail
    events:
      - smtp: {resource: inbound-mail}
```

The fields of `event.data` (attachments, headers, the SES shape) are listed in [SMTP: receive
mail](../../smtp/README.md) and [the smtp trigger](../../triggers/smtp.md).

`pskit resources usage inbound-mail` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage inbound-mail` shows how to connect from any
other program.

## Open the SMTP server web UI, console and terminal

The SMTP server row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status inbound-mail --reveal      # state, health, endpoint, credentials
pskit resources onprem usage inbound-mail                # connect from any program
pskit resources onprem logs inbound-mail -n 100
pskit resources onprem terminal inbound-mail
pskit resources onprem tunnel inbound-mail                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove SMTP server

SMTP server has no backup command in pskit; copy its data volume yourself if you need one.

To remove SMTP server: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove inbound-mail --save                 # keep the data volume
pskit resources onprem remove inbound-mail --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [SMTP: receive mail](../../smtp/README.md)
- [smtp trigger](../../triggers/smtp.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
