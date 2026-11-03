# Jaeger (tracing, OpenTelemetry)

Search terms: Jaeger, tracing, OpenTelemetry, OTLP, 4317, 4318, 16686, distributed tracing

Jaeger is a distributed tracing backend. Send OpenTelemetry traces to OTLP gRPC (4317) or HTTP (4318) and search them
in the UI (16686). It keeps traces in memory and has **no login**: keep it on a private network.

## Jaeger at a glance

The Jaeger service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `jaeger` |
| Studio card | **Monitoring & tracing** > **Jaeger (tracing, OpenTelemetry)** |
| Docker image | `jaegertracing/all-in-one:1.62.0` |
| Port | `16686` (also `4317`, `4318`). Extra ports move with the main port |
| Use as | `custom` (Service, resource type `custom`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | not persisted (a restart empties it) |
| Backup | no |
| Web UI | Jaeger UI on port `16686` at `/` (no login) |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Jaeger in studio

The studio creates Jaeger from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Monitoring & tracing**, click the **Jaeger (tracing, OpenTelemetry)**
   card. The drawer title changes to *Create Jaeger (tracing, OpenTelemetry)*.
4. **Resource key**: type `tracing` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `16686`, or type another one if that port is taken.
7. **Security**: Jaeger runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)* or *Network
   (0.0.0.0)* and limit the port with the firewall.
8. **Web UI**: built in (Jaeger UI); *How to use* shows its address and login.
9. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
10. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
    is pulled, the container started and checked). The button turns into *Created*.
11. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Jaeger from the terminal

`pskit resources onprem create KEY --service jaeger` starts Jaeger and prints the `pskit.yml` entry; add `--save` to
write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or `--local`
it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this machine.

```bash
pskit resources onprem create tracing --service jaeger --save                 # here, or the deploy target
pskit resources onprem create tracing --service jaeger --server edge1 --save   # a saved server
pskit resources onprem create tracing --service jaeger --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Jaeger

Creating Jaeger adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem env file
(`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address `10.0.0.5` and
the defaults.

```yaml
resources:
  tracing:
    type: custom
    external: true
    connection:
      url: http://10.0.0.5:16686
      otlp_http: http://10.0.0.5:4318
      otlp_grpc: 10.0.0.5:4317
```

```text
# .env.onprem
PSKIT_TRACING_URL=http://10.0.0.5:16686
PSKIT_TRACING_OTLP_ENDPOINT=http://10.0.0.5:4318
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Jaeger from a handler

A handler reaches Jaeger through `resource("tracing")`, which returns the connection values pskit passes to bound
functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import urllib.request

from py_serverless_kit import resource


def ping(event, ctx):
    r = resource("tracing")
    url = r["url"]                                       # http://<address>:<port>
    with urllib.request.urlopen(url, timeout=5) as resp:
        return {"url": url, "status": resp.status}
```

Other connection values: `otlp_http`, `otlp_grpc`.

`pskit resources usage tracing` (studio: **How to use** on the resource row) prints the same code for Python and
Node.js with the libraries to install, and `pskit resources onprem usage tracing` shows how to connect from any other
program.

## Open the Jaeger web UI, console and terminal

The Jaeger row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, the endpoint and **Open ...** links for: Jaeger UI on port `16686` at `/` (no login).
  **Check web UI** finds out why a UI does not open (container, port, firewall).
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status tracing --reveal      # state, health, endpoint, credentials
pskit resources onprem usage tracing                # connect from any program
pskit resources onprem logs tracing -n 100
pskit resources onprem gui tracing                  # print the web UI links (starts a companion)
pskit resources onprem gui tracing --check
pskit resources onprem terminal tracing
pskit resources onprem tunnel tracing                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Jaeger

Jaeger has no backup command in pskit (it keeps data in memory only).

To remove Jaeger: **Remove** on the row, then **Remove, keep data**. The container is deleted, its variables leave the
env file, and the resource and its triggers leave the draft (click **Save**). On the Resources table, **Delete** on
the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service and data*.

```bash
pskit resources onprem remove tracing --save                 # keep the data volume
pskit resources onprem remove tracing --delete-data --save   # delete it too
```

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
