# On-premises service: Jaeger (tracing, OpenTelemetry)

The catalog id is `jaeger`. Kind is service. Group is Monitoring. Image is jaegertracing/all-in-one:1.62.0. Published port is 16686. Extra ports are 4317, 4318. Roles are custom. Backup is no. Persistent data is no. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Jaeger UI. GUI login choices are none.

Catalog notes: Distributed tracing: send OpenTelemetry traces to OTLP gRPC :4317 or HTTP :4318 and search them in the UI. Keeps traces in memory. No login: keep it on a private network.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-jaeger --service jaeger
pskit resources onprem status sample-jaeger
```

pskit resources onprem usage sample-jaeger prints how to connect. pskit resources onprem logs sample-jaeger shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
