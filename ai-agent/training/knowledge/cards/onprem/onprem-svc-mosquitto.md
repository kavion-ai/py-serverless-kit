# On-premises service: Eclipse Mosquitto (MQTT broker)

The catalog id is `mosquitto`. Kind is service. Group is Queues and streams. Image is eclipse-mosquitto:2. Published port is 1883. Extra ports are none. Roles are custom. Backup is no. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: MQTT for IoT devices and sensors. Anonymous access: keep it on a private network.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-mosquitto --service mosquitto
pskit resources onprem status sample-mosquitto
```

pskit resources onprem usage sample-mosquitto prints how to connect. pskit resources onprem logs sample-mosquitto shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
