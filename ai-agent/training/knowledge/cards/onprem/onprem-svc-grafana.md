# On-premises service: Grafana (dashboards)

The catalog id is `grafana`. Kind is service. Group is Monitoring. Image is grafana/grafana:11.3.0. Published port is 3000. Extra ports are none. Roles are custom. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Grafana. GUI login choices are none.

Catalog notes: Dashboards and alerts over Prometheus, Loki, PostgreSQL, ClickHouse and 100+ data sources.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-grafana --service grafana
pskit resources onprem status sample-grafana
```

pskit resources onprem usage sample-grafana prints how to connect. pskit resources onprem logs sample-grafana shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
