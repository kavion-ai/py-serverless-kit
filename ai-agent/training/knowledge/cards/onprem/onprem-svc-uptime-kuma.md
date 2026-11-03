# On-premises service: Uptime Kuma (uptime monitor)

The catalog id is `uptime-kuma`. Kind is service. Group is Monitoring. Image is louislam/uptime-kuma:1. Published port is 3001. Extra ports are none. Roles are custom. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Uptime Kuma. GUI login choices are none.

Catalog notes: Checks HTTP, TCP, DNS, Docker containers ... every minute and alerts by mail, Slack, Telegram. Create the admin account on the first visit.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-uptime-kuma --service uptime-kuma
pskit resources onprem status sample-uptime-kuma
```

pskit resources onprem usage sample-uptime-kuma prints how to connect. pskit resources onprem logs sample-uptime-kuma shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
