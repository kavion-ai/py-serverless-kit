# On-premises service: Mailpit (SMTP)

The catalog id is `mailpit`. Kind is service. Group is Tools. Image is axllent/mailpit:latest. Published port is 1025. Extra ports are 8025. Roles are custom. Backup is no. Persistent data is no. Auth is no. Default user is pskit. Companion UI is none. Web UI names are Mailbox. GUI login choices are none.

Catalog notes: An SMTP server that keeps every mail for inspection (web UI on port 8025). For development and tests.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-mailpit --service mailpit
pskit resources onprem status sample-mailpit
```

pskit resources onprem usage sample-mailpit prints how to connect. pskit resources onprem logs sample-mailpit shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
