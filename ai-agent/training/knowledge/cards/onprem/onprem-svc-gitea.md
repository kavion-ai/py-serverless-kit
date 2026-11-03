# On-premises service: Gitea (Git hosting)

The catalog id is `gitea`. Kind is service. Group is Tools. Image is gitea/gitea:1.22. Published port is 3000. Extra ports are none. Roles are custom. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Gitea. GUI login choices are none.

Catalog notes: Self-hosted Git with pull requests, issues, packages and Actions. Finish the install page on the first visit; the first account is the admin.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-gitea --service gitea
pskit resources onprem status sample-gitea
```

pskit resources onprem usage sample-gitea prints how to connect. pskit resources onprem logs sample-gitea shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
