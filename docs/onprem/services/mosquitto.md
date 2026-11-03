# Eclipse Mosquitto (MQTT broker)

Search terms: Mosquitto, MQTT broker, IoT, sensors, 1883, Eclipse Mosquitto, publish subscribe

Eclipse Mosquitto is an MQTT broker for IoT devices and sensors. In this setup it allows **anonymous access**: keep it
on a private network. pskit adds it as a `custom` resource with its `mqtt://` URL; use an MQTT client library such as
`paho-mqtt` in your handlers.

## Eclipse Mosquitto at a glance

The Eclipse Mosquitto service in the on-prem catalog has these settings (read from `core/onprem_services.py`):

| | |
|---|---|
| `--service` | `mosquitto` |
| Studio card | **Queues & streams** > **Eclipse Mosquitto (MQTT broker)** |
| Docker image | `eclipse-mosquitto:2` |
| Port | `1883` |
| Use as | `custom` (Service, resource type `custom`) |
| Login | none in this setup (keep it on `127.0.0.1` or a private network) |
| Data | kept in `/mosquitto/data` (a Docker volume, or `<data_dir>/<container>` on a server with a data directory) |
| Backup | no |
| Web UI | none |
| Console | no client: use *Shell in the container* (`sh`) |

## Create Eclipse Mosquitto in studio

The studio creates Eclipse Mosquitto from the *Resources* page, with a form that checks every field before it starts:

1. Open the **Resources** page in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card lower on the
   page).
3. In the *Create a service* drawer, under **Queues & streams**, click the **Eclipse Mosquitto (MQTT broker)** card.
   The drawer title changes to *Create Eclipse Mosquitto (MQTT broker)*.
4. **Resource key**: type `mqtt` (the form suggests a free name). Handlers and triggers use this key.
5. **Where**: **This machine** (Docker here), or **One SSH server** and pick a saved server in **Server** (or *New
   connection…* and type Host, User, SSH port and *Log in with*), or **Scaling cluster** to run it on one server of a
   cluster.
6. **Port**: leave empty for `1883`, or type another one if that port is taken.
7. **Security**: Eclipse Mosquitto runs without authentication; choose **Listen on**: *This machine only (127.0.0.1)*
   or *Network (0.0.0.0)* and limit the port with the firewall.
8. **Advanced** (optional): **Address functions use** (default: the SSH host, or 127.0.0.1 here) and **Docker image**.
9. Click **Create**. The job log streams below the form (Docker is installed on an SSH server when missing, the image
   is pulled, the container started and checked). The button turns into *Created*.
10. The resource is added to the draft. Click **Save** in the top bar to write `pskit.yml`, then deploy.

## Create Eclipse Mosquitto from the terminal

`pskit resources onprem create KEY --service mosquitto` starts Eclipse Mosquitto and prints the `pskit.yml` entry; add
`--save` to write it into `pskit.yml` (comments in the file are not kept). Without `--ssh`, `--server`, `--cluster` or
`--local` it goes where the functions deploy (`provider.options.cluster`, then `provider.options.deploy`), else this
machine.

```bash
pskit resources onprem create mqtt --service mosquitto --save                 # here, or the deploy target
pskit resources onprem create mqtt --service mosquitto --server edge1 --save   # a saved server
pskit resources onprem create mqtt --service mosquitto --ssh ubuntu@10.0.0.5 --pem ~/.ssh/key.pem --save
```

- `--port`, `--image`, `--address`, `--bind` and `--sudo` change the defaults; see `pskit resources onprem create
  --help`.

## What pskit writes for Eclipse Mosquitto

Creating Eclipse Mosquitto adds a resource to `pskit.yml` and, when there are credentials, writes them to the on-prem
env file (`provider.options.env_file`, default `.env.onprem`), never into `pskit.yml`. The examples use address
`10.0.0.5` and the defaults.

```yaml
resources:
  mqtt:
    type: custom
    external: true
    connection:
      url: mqtt://10.0.0.5:1883
```

```text
# .env.onprem
PSKIT_MQTT_URL=mqtt://10.0.0.5:1883
```

When the main provider is not `onprem`, the resource goes under `providers.onprem.resources` so the other clouds are
not affected. Created services are recorded in `.pskit/onprem-services.json`.

## Use Eclipse Mosquitto from a handler

A handler reaches Eclipse Mosquitto through `resource("mqtt")`, which returns the connection values pskit passes to
bound functions; a value ending in `_env` is the **name** of a variable from the env file, read with `ctx.env[...]`.

```python
import paho.mqtt.publish as publish

from py_serverless_kit import resource


def send_reading(event, ctx):
    r = resource("mqtt")
    host_port = r["url"].split("://", 1)[1]              # mqtt://<address>:<port>
    host, port = host_port.rsplit(":", 1)
    publish.single("sensors/temp", "21.5", hostname=host, port=int(port))
    return {"published": True}
```

Add `paho-mqtt` to `requirements.txt`.

`pskit resources usage mqtt` (studio: **How to use** on the resource row) prints the same code for Python and Node.js
with the libraries to install, and `pskit resources onprem usage mqtt` shows how to connect from any other program.

## Open the Eclipse Mosquitto web UI, console and terminal

The Eclipse Mosquitto row in the *On-prem services* card (Resources page) has these buttons:

- **Details** shows the state, health, endpoint, credentials (**Show values**) and **Show logs**.
- **Console** has no client for this service: it runs each line with `sh -c` in the container.
- **Terminal** opens a full terminal in the browser (ttyd in Docker on this machine): `sh` in the container.

```bash
pskit resources onprem status mqtt --reveal      # state, health, endpoint, credentials
pskit resources onprem usage mqtt                # connect from any program
pskit resources onprem logs mqtt -n 100
pskit resources onprem terminal mqtt
pskit resources onprem tunnel mqtt                # firewalled port: reach it on 127.0.0.1
```

More: [terminal and software](../terminal-and-software.md).

## Back up and remove Eclipse Mosquitto

Eclipse Mosquitto has no backup command in pskit; copy its data volume yourself if you need one.

To remove Eclipse Mosquitto: **Remove** on the row, then **Remove, keep data** or **Delete data too**. The container
is deleted, its variables leave the env file, and the resource and its triggers leave the draft (click **Save**). On
the Resources table, **Delete** on the resource offers *pskit.yml only*, *Stop service, keep data* or *Delete service
and data*.

```bash
pskit resources onprem remove mqtt --save                 # keep the data volume
pskit resources onprem remove mqtt --delete-data --save   # delete it too
```

A kept volume is reused when you create the service again with the same key (to change the password, remove with *keep
data* and create it again with the new password).

## See also

- [On-prem services overview](README.md)
- [On-prem resources and drivers](../resources.md)
- [Saved servers](../servers.md)
- [Terminal, console and software](../terminal-and-software.md)
- [Full reference: one-click services](../../resource-guides/onprem/services.md)
