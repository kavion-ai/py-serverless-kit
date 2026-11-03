# On-premises service: Apache Kafka (KRaft, single node)

The catalog id is `apache-kafka`. Kind is service. Group is Queues and streams. Image is apache/kafka:3.8.1. Published port is 9092. Extra ports are none. Roles are queue. Backup is yes. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is Kafka UI. Web UI names are none. GUI login choices are password, none.

Catalog notes: The Apache Kafka distribution (no ZooKeeper), consumed through the Kafka driver class pskit adds (needs kafka-python). No authentication: keep the port on a private network.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-apache-kafka --service apache-kafka
pskit resources onprem status sample-apache-kafka
```

pskit resources onprem usage sample-apache-kafka prints how to connect. pskit resources onprem logs sample-apache-kafka shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
