# OpenBao (Vault-compatible secrets)

Search terms: OpenBao, Vault, HashiCorp Vault compatible, KV v2, secrets, bao CLI, token, 8200, get_secret

OpenBao is the open-source fork of HashiCorp Vault. pskit starts it with file storage in the volume, initialises it
with one unseal key, unseals it on every start, enables KV v2 at `secret/` and creates a token whose id is the service
password. Handlers read it with `get_secret()`. Its release images have no web UI, so use pskit's **Browse secrets**
instead.

## OpenBao at a glance

The OpenBao service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `openbao` |
| Studio card | **Secret managers** > **OpenBao (Vault-compatible secrets)** |
| Docker image | `openbao/openbao:2.1.0` |
| Port | `8200` |
| Use as | `secrets` (Secret manager, resource type `custom`) |
| Login | a token: the service password (generated when empty), in `PSKIT_<KEY>_TOKEN` |
| Data | kept in `/openbao/file` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | yes (`.tar.gz`) |
| Web UI | none |
| Console | bao (Vault CLI) |

## Create OpenBao in studio

The studio creates OpenBao from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Secret managers**, click the **OpenBao (Vault-compatible secrets)** card.
   The drawer title changes to *Create OpenBao (Vault-compatible secrets)*.
4. **Resource key**: type `secrets` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `8200`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
9. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
   is pulled, the container started and checked). The button turns into *Created*.
10. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create OpenBao from the terminal

`pskit resources onprem create KEY --service openbao` starts OpenBao and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create secrets --service openbao --save                 # here, or the deploy target
pskit resources onprem create secrets --service openbao --server edge1 --save   # a saved server
pskit resources onprem create secrets --service openbao --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export SECRETS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create secrets --service openbao --user app --password-env SECRETS_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for OpenBao

Creating OpenBao adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      driver: vault
      url: http://10.0.0.5:8200
      mount: secret
      token_env: PSKIT_SECRETS_TOKEN
```

```text
# .env.onprem
PSKIT_SECRETS_DRIVER=vault
PSKIT_SECRETS_URL=http://10.0.0.5:8200
PSKIT_SECRETS_TOKEN=<password>
PSKIT_SECRETS_MOUNT=secret
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use OpenBao from a handler

A handler reaches OpenBao through `resource("secrets")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

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

## Open the OpenBao web UI, console and terminal

The OpenBao row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Browse secrets** opens pskit's own browser (secrets (folders, versions)).
- **Console** runs one command at a time with **bao (Vault CLI)** and the service's credentials, for example `kv list
  secret`, `kv get secret/db-password`, `kv put secret/api-key value=abc123`. Switch to *Shell in the container* for
  `sh`.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status secrets --reveal      # state, health, endpoint, credentials
pskit resources onprem usage secrets                # connect from any program
pskit resources onprem logs secrets -n 100
pskit resources onprem console secrets "kv list secret"
pskit resources onprem terminal secrets
pskit resources onprem tunnel secrets                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove OpenBao

OpenBao backups stream a dump out of the container into `.pskit/backups/secrets-<time>.tar.gz` on this machine (also
from an SSH server). In studio: **Backup** on the row, *Save to folder* (empty = `.pskit/backups`), **Back up now**.

```bash
pskit resources onprem backup secrets
pskit resources onprem backup secrets --dir ~/backups
```

To remove OpenBao: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is deleted,
its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources
table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

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
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
