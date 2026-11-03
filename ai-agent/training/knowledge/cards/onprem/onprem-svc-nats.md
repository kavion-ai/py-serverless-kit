# On-premises service: NATS JetStream

The catalog id is `nats`. Kind is service. Group is Queues and streams. Image is nats:2.10-alpine. Published port is 4222. Extra ports are 8222. Roles are queue. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Monitoring (JSON). GUI login choices are none.

Catalog notes: A JetStream stream with a durable pull consumer, through a driver class pskit adds to your app (needs nats-py). Monitoring on port 8222.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-nats --service nats
pskit resources onprem status sample-nats
```

pskit resources onprem usage sample-nats prints how to connect. pskit resources onprem logs sample-nats shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
