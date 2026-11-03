# AWS Secrets Manager compatible server (Python / Node.js)

Search terms: AWS Secrets Manager compatible, secrets server, get_secret, put_secret, SigV4, secretsmanager-node,
master key, secrets console

pskit ships its own AWS Secrets Manager compatible server, in two flavors: **AWS Secrets Manager compatible (Python)**
(`--service secretsmanager`) and **(Node.js)** (`--service secretsmanager-node`). boto3, the AWS SDKs, the AWS CLI and
`get_secret()` work with its endpoint. Requests are signed with SigV4: the service's user is the access key ID, its
password the secret access key. Values are encrypted at rest with a generated master key. This page covers creating it
and using it as a resource; the API coverage, the Python and Node.js implementations and SDK examples are in [the
Secrets Manager compatible server reference](../aws-compatible/secretsmanager.md).

## AWS Secrets Manager compatible at a glance

The AWS Secrets Manager compatible service in the on-prem catalog has these settings (read from
`core/onprem_services.py`):

| | |
|---|---|
| `--service` | `secretsmanager` / `secretsmanager-node` |
| Studio card | **Secret managers** > **AWS Secrets Manager compatible (Python)** / **AWS Secrets Manager compatible (Node.js)** |
| Docker image | `python:3.12-alpine` / `node:22-alpine` |
| Port | `4584` |
| Use as | `secrets` (Secret manager, resource type `custom`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | Secrets console on port `4584` at `/ui/` (the service's user and password) |
| Console | aws secretsmanager (helper) |
| Generated keys | `PSKIT_<KEY>_MASTER_KEY` (kept in the env file and reused when you create the service again) |

## Create AWS Secrets Manager compatible in studio

The studio creates AWS Secrets Manager compatible from the *Resources* page, with a form that checks every field
before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Secret managers**, click the **AWS Secrets Manager compatible (Python)**
   or **AWS Secrets Manager compatible (Node.js)** card. The drawer title changes to *Create AWS Secrets Manager
   compatible (Python)*.
4. **Resource key**: type `secrets` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `4584`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Secrets console); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create AWS Secrets Manager compatible from the terminal

`pskit resources onprem create KEY --service secretsmanager` starts AWS Secrets Manager compatible and prints the
`pskit.yml` entry; add `--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`,
`--server`, `--cluster` or `--local` it goes where the functions deploy (`provider.options.cluster`, then
`provider.options.deploy`), else this machine.

```bash
pskit resources onprem create secrets --service secretsmanager --save                 # here, or the deploy target
pskit resources onprem create secrets --service secretsmanager-node --save                 # here, or the deploy target
pskit resources onprem create secrets --service secretsmanager --server edge1 --save   # a saved server
pskit resources onprem create secrets --service secretsmanager --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export SECRETS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create secrets --service secretsmanager --user app --password-env SECRETS_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for AWS Secrets Manager compatible

Creating AWS Secrets Manager compatible adds a resource to `pskit.yml` and, when there are credentials, writes them to
the on-prem env file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use
address `10.0.0.5` and the defaults.

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      driver: aws
      url: http://10.0.0.5:4584
      region: us-east-1
      access_key_env: PSKIT_SECRETS_ACCESS_KEY
      secret_key_env: PSKIT_SECRETS_SECRET_KEY
      console_url: http://10.0.0.5:4584/ui/
```

```text
# .env.onprem
PSKIT_SECRETS_DRIVER=aws
PSKIT_SECRETS_URL=http://10.0.0.5:4584
PSKIT_SECRETS_REGION=us-east-1
PSKIT_SECRETS_ACCESS_KEY=pskit
PSKIT_SECRETS_SECRET_KEY=<password>
PSKIT_SECRETS_MASTER_KEY=<generated>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use AWS Secrets Manager compatible from a handler

A handler reaches AWS Secrets Manager compatible through `resource("secrets")`, which returns the connection values
pskit passes to bound functions; a value ending in `_env` is the **name** of a variable from the env file, read with
`ctx.env[...]`.

As a secret manager, `get_secret()` and `put_secret()` read the `PSKIT_SECRETS_*` variables pskit wrote to the env
file. With the key `secrets` it is the default store; with another key pass `store="<key>"`:

```python
from py_serverless_kit import get_secret, put_secret


def handler(event, ctx):
    api_key = get_secret("api-key")                 # one value
    db_password = get_secret("prod/db", "password") # one field of a JSON secret
    put_secret("last-run", ctx.request_id)
    return {"has_key": bool(api_key), "has_db_password": bool(db_password)}
```

Node.js handlers use `getSecret("api-key")` from the `pskit` package. More: [secrets
guide](../../resource-guides/onprem/secrets.md).

`pskit resources usage secrets` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage secrets` shows how to connect from any other
program.

## Open the AWS Secrets Manager compatible web UI, console and terminal

The AWS Secrets Manager compatible row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Secrets console on port `4584` at `/ui/` (the
  service's user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Browse secrets** opens pskit's own browser (Secrets Manager secrets).
- **Console** runs one command at a time with **aws secretsmanager (helper)** and the service's credentials, for
  example `secretsmanager list-secrets`, `secretsmanager create-secret --name api-key --secret-string abc123`,
  `secretsmanager get-secret-value --secret-id api-key`. Switch to *Shell in the container* for `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status secrets --reveal      # state, health, endpoint, credentials
pskit resources onprem usage secrets                # connect from any program
pskit resources onprem logs secrets -n 100
pskit resources onprem gui secrets                  # print the web UI links (starts a companion)
pskit resources onprem gui secrets --check
pskit resources onprem console secrets "secretsmanager list-secrets"
pskit resources onprem terminal secrets
pskit resources onprem tunnel secrets                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove AWS Secrets Manager compatible

AWS Secrets Manager compatible backups stream a dump out of the container into `.pskit/backups/secrets-<time>.tar.gz`
on this machine (also from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty =
`.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup secrets
pskit resources onprem backup secrets --dir ~/backups
```

To remove AWS Secrets Manager compatible: **Remove** on the row, then **Remove, keep data** or **Delete data too**.
The container is deleted, its variables leave the env file, and the resource and its triggers leave the draft (click
**Save**). On the Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or
*Delete service and data*.

```bash
pskit resources onprem remove secrets --save                 # keep the data volume
pskit resources onprem remove secrets --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Existing secrets guide](../../resource-guides/onprem/secrets.md)
- [Secrets Manager compatible server reference](../aws-compatible/secretsmanager.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
