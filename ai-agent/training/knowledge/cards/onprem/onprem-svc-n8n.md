# On-premises service: n8n (workflow automation)

The catalog id is `n8n`. Kind is service. Group is Automation. Image is n8nio/n8n:latest. Published port is 5678. Extra ports are none. Roles are custom. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are n8n. GUI login choices are none.

Catalog notes: Visual workflow automation with 400+ integrations; call your pskit functions with its HTTP node or the Lambda-compatible invoke API. Create the owner account on the first visit.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-n8n --service n8n
pskit resources onprem status sample-n8n
```

pskit resources onprem usage sample-n8n prints how to connect. pskit resources onprem logs sample-n8n shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
