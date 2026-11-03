# Infisical (secrets manager with web UI)

Search terms: Infisical, secrets manager, machine identity, Universal Auth, client id, client secret, project id, web
UI, 8080

Infisical is an open-source secrets manager with a web UI (projects, environments, versions, audit log). pskit starts
it with its own PostgreSQL and Redis next to it (sidecar containers on a private Docker network). You create the admin
account on the first visit, then a machine identity for `get_secret()`.

## Infisical at a glance

The Infisical service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `infisical` |
| Studio card | **Secret managers** > **Infisical (secrets manager with web UI)** |
| Docker image | `infisical/infisical:latest` |
| Port | `8080` |
| Use as | `secrets` (Secret manager, resource type `custom`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | not persisted (a restart empties it) |
| Backup | no |
| Web UI | Infisical on port `8080` at `/` (create the admin account on the first visit) |
| Console | no client: use *Shell in the container* (`sh`) |
| Extra containers | `<container>-db` (postgres:16-alpine), `<container>-redis` (redis:7-alpine) |
| Generated keys | `PSKIT_<KEY>_ENCRYPTION_KEY`, `PSKIT_<KEY>_AUTH_SECRET` (kept in the env file and reused when you create the service again) |

## Create Infisical in studio

The studio creates Infisical from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Secret managers**, click the **Infisical (secrets manager with web UI)**
   card. The drawer title changes to *Create Infisical (secrets manager with web UI)*.
4. **Resource key**: type `secrets` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `8080`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Infisical); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Infisical from the terminal

`pskit resources onprem create KEY --service infisical` starts Infisical and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create secrets --service infisical --save                 # here, or the deploy target
pskit resources onprem create secrets --service infisical --server edge1 --save   # a saved server
pskit resources onprem create secrets --service infisical --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export SECRETS_PASSWORD='Str0ng.pass-1'
pskit resources onprem create secrets --service infisical --user app --password-env SECRETS_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Infisical

Creating Infisical adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      driver: infisical
      url: http://10.0.0.5:8080
      client_id_env: PSKIT_SECRETS_CLIENT_ID
      client_secret_env: PSKIT_SECRETS_CLIENT_SECRET
      project_id_env: PSKIT_SECRETS_PROJECT_ID
```

```text
# .env.onprem
PSKIT_SECRETS_DRIVER=infisical
PSKIT_SECRETS_URL=http://10.0.0.5:8080
PSKIT_SECRETS_CLIENT_ID=
PSKIT_SECRETS_CLIENT_SECRET=
PSKIT_SECRETS_PROJECT_ID=
PSKIT_SECRETS_ENVIRONMENT=dev
PSKIT_SECRETS_ENCRYPTION_KEY=<generated>
PSKIT_SECRETS_AUTH_SECRET=<generated>
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Infisical from a handler

A handler reaches Infisical through `resource("secrets")`, which returns the connection values pskit passes to bound
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

## Open the Infisical web UI, console and terminal

The Infisical row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Infisical on port `8080` at `/` (create the
  admin account on the first visit). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status secrets --reveal      # state, health, endpoint, credentials
pskit resources onprem usage secrets                # connect from any program
pskit resources onprem logs secrets -n 100
pskit resources onprem gui secrets                  # print the web UI links (starts a companion)
pskit resources onprem gui secrets --check
pskit resources onprem terminal secrets
pskit resources onprem tunnel secrets                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Infisical

Infisical has no backup command in pskit (it keeps data in memory only).

To remove Infisical: **Remove** on the row, then **Remove, keep data**. The container is deleted, its variables leave
the env file, and the resource and its triggers leave the draft (click **Save**). On the Resources table, **Delete**
on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove secrets --save                 # keep the data volume
pskit resources onprem remove secrets --delete-data --save   # delete it too
```

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Existing secrets guide](../../resource-guides/onprem/secrets.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
