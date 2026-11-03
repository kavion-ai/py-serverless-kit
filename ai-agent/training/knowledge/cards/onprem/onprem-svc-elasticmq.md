# On-premises service: ElasticMQ (SQS-compatible)

The catalog id is `elasticmq`. Kind is service. Group is Queues and streams. Image is softwaremill/elasticmq-native:1.6.11. Published port is 9324. Extra ports are 9325. Roles are queue. Backup is no. Persistent data is no. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Queue browser. GUI login choices are none.

Catalog notes: Amazon SQS API, used through the sqs driver. Keeps messages in memory: a restart empties it, so use it for development and tests. UI on port 9325.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-elasticmq --service elasticmq
pskit resources onprem status sample-elasticmq
```

pskit resources onprem usage sample-elasticmq prints how to connect. pskit resources onprem logs sample-elasticmq shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
