# On-premises service: ClickHouse (analytics database)

The catalog id is `clickhouse`. Kind is service. Group is Databases. Image is clickhouse/clickhouse-server:24.8. Published port is 8123. Extra ports are 9000. Roles are database. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are SQL playground. GUI login choices are none.

Catalog notes: Column-store SQL for analytics and logs. HTTP on the port (SQL playground at /play), native protocol on 9000.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-clickhouse --service clickhouse
pskit resources onprem status sample-clickhouse
```

pskit resources onprem usage sample-clickhouse prints how to connect. pskit resources onprem logs sample-clickhouse shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
