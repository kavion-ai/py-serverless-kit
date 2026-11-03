# On-premises service: Git

The catalog id is `git`. Kind is runtime. Group is Tools. Image is n/a. Published port is none. Extra ports are none. Roles are none. Backup is no. Persistent data is no. Auth is no. Default user is n/a. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: git from the distribution's packages.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-git --service git
pskit resources onprem status sample-git
```

pskit resources onprem usage sample-git prints how to connect. pskit resources onprem logs sample-git shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
