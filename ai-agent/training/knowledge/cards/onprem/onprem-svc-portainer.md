# On-premises service: Portainer (Docker UI)

The catalog id is `portainer`. Kind is service. Group is Tools. Image is portainer/portainer-ce:2.21.4. Published port is 9000. Extra ports are 9443. Roles are custom. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Portainer. GUI login choices are none.

Catalog notes: Manage the server's containers, images, volumes and networks in the browser. Create the admin account within 5 minutes of the first start (otherwise restart it).

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-portainer --service portainer
pskit resources onprem status sample-portainer
```

pskit resources onprem usage sample-portainer prints how to connect. pskit resources onprem logs sample-portainer shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
