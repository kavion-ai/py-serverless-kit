# Keycloak (login, SSO, OAuth2 / OIDC)

Search terms: Keycloak, identity provider, SSO, OAuth2, OpenID Connect, OIDC, login, issuer, realm, 8080

Keycloak is an identity provider: users, groups, social login, MFA and OpenID Connect / OAuth2 tokens for your APIs.
pskit runs it in dev mode (H2 database in the volume, plain HTTP) with the admin user you set; put it behind HTTPS for
production.

## Keycloak at a glance

The Keycloak service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `keycloak` |
| Studio card | **Identity & search** > **Keycloak (login, SSO, OAuth2 / OIDC)** |
| Docker image | `quay.io/keycloak/keycloak:26.0` |
| Port | `8080` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | user (default `pskit`) and password (generated when empty) |
| Data | kept in `/opt/keycloak/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | Admin console on port `8080` at `/admin/` (the service's user and password) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Keycloak in studio

The studio creates Keycloak from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Identity & search**, click the **Keycloak (login, SSO, OAuth2 / OIDC)**
   card. The drawer title changes to *Create Keycloak (login, SSO, OAuth2 / OIDC)*.
4. **Resource key**: type `auth` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `8080`, or type another one if that port is taken.
7. **Security**: **User** (empty = default), **Password** (empty = generated; **Generate** and **Show** help),
   **Listen on**: *This machine only (127.0.0.1)* or *Network (0.0.0.0)*.
8. **Web UI**: built in (Admin console); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Keycloak from the terminal

`pskit resources onprem create KEY --service keycloak` starts Keycloak and prints the `pskit.yml` entry; add `--save`
to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create auth --service keycloak --save                 # here, or the deploy target
pskit resources onprem create auth --service keycloak --server edge1 --save   # a saved server
pskit resources onprem create auth --service keycloak --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
export AUTH_PASSWORD='Str0ng.pass-1'
pskit resources onprem create auth --service keycloak --user app --password-env AUTH_PASSWORD --bind 127.0.0.1 --local --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Keycloak

Creating Keycloak adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  auth:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:8080
      issuer: http://10.0.0.5:8080/realms/master
      user: pskit
      password_env: PSKIT_AUTH_PASSWORD
```

```text
# .env.onprem
PSKIT_AUTH_URL=http://10.0.0.5:8080
PSKIT_AUTH_USER=pskit
PSKIT_AUTH_PASSWORD=<password>
PSKIT_AUTH_ISSUER=http://10.0.0.5:8080/realms/master
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Keycloak from a handler

A handler reaches Keycloak through `resource("auth")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("auth")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

Other connection values: `issuer`, `user`, `password_env`.

`pskit resources usage auth` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage auth` shows how to connect from any other program.

## Open the Keycloak web UI, console and terminal

The Keycloak row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Admin console on port `8080` at `/admin/` (the
  service's user and password). **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status auth --reveal      # state, health, endpoint, credentials
pskit resources onprem usage auth                # connect from any program
pskit resources onprem logs auth -n 100
pskit resources onprem gui auth                  # print the web UI links (starts a companion)
pskit resources onprem gui auth --check
pskit resources onprem terminal auth
pskit resources onprem tunnel auth                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Keycloak

Keycloak has no backup command in pskit; copy its data volume yourself if you need one.

To remove Keycloak: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container is
deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On the
Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and
data*.

```bash
pskit resources onprem remove auth --save                 # keep the data volume
pskit resources onprem remove auth --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
