# On-premises service: RabbitMQ

The catalog id is `rabbitmq`. Kind is service. Group is Queues and streams. Image is rabbitmq:3-management-alpine. Published port is 5672. Extra ports are 15672. Roles are queue. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Management UI. GUI login choices are none.

Catalog notes: AMQP with manual acks through a small driver class pskit adds to your app (needs pika). Management UI on port 15672. Backups hold definitions (queues, users), not messages.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-rabbitmq --service rabbitmq
pskit resources onprem status sample-rabbitmq
```

pskit resources onprem usage sample-rabbitmq prints how to connect. pskit resources onprem logs sample-rabbitmq shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
