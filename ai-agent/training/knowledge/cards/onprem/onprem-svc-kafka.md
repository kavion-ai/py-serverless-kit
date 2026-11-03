# On-premises service: Kafka (Redpanda, single node)

The catalog id is `kafka`. Kind is service. Group is Queues and streams. Image is redpandadata/redpanda:v24.3.6. Published port is 9092. Extra ports are none. Roles are queue. Backup is yes. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is Kafka UI. Web UI names are none. GUI login choices are password, none.

Catalog notes: Kafka API (Redpanda, no ZooKeeper). Consumed through a driver class pskit adds to your app (needs kafka-python). No authentication: keep the port on a private network.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-kafka --service kafka
pskit resources onprem status sample-kafka
```

pskit resources onprem usage sample-kafka prints how to connect. pskit resources onprem logs sample-kafka shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
