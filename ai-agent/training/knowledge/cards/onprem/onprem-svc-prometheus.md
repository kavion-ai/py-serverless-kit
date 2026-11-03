# On-premises service: Prometheus (metrics)

The catalog id is `prometheus`. Kind is service. Group is Monitoring. Image is prom/prometheus:v2.55.1. Published port is 9090. Extra ports are none. Roles are custom. Backup is no. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Prometheus UI. GUI login choices are none.

Catalog notes: Metrics database and query UI. Scrapes itself by default; add targets in /etc/prometheus/prometheus.yml (Console: sh). No login: keep it on a private network.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-prometheus --service prometheus
pskit resources onprem status sample-prometheus
```

pskit resources onprem usage sample-prometheus prints how to connect. pskit resources onprem logs sample-prometheus shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
