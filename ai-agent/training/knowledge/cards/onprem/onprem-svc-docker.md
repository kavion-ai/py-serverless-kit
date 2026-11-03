# On-premises service: Docker

The catalog id is `docker`. Kind is runtime. Group is Languages and Docker. Image is n/a. Published port is none. Extra ports are none. Roles are none. Backup is no. Persistent data is no. Auth is no. Default user is n/a. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: Installs and starts Docker on an SSH server (needed by every service above, and by method: docker).

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-docker --service docker
pskit resources onprem status sample-docker
```

pskit resources onprem usage sample-docker prints how to connect. pskit resources onprem logs sample-docker shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
