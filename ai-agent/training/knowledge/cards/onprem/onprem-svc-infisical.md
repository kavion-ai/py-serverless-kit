# On-premises service: Infisical (secrets manager with web UI)

The catalog id is `infisical`. Kind is service. Group is Secrets. Image is infisical/infisical:latest. Published port is 8080. Extra ports are none. Roles are secrets. Backup is no. Persistent data is no. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Infisical. GUI login choices are none.

Catalog notes: Open-source secrets manager (projects, environments, versions, audit log, access control) with its own PostgreSQL and Redis next to it. Open the web UI and create the admin account, then a project and a machine identity (Universal Auth): put its client id / secret and the project id in the env file and get_secret() / getSecret() read from Infisical. ENCRYPTION_KEY stays in the env file: keep it, the data cannot be read without it.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-infisical --service infisical
pskit resources onprem status sample-infisical
```

pskit resources onprem usage sample-infisical prints how to connect. pskit resources onprem logs sample-infisical shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
