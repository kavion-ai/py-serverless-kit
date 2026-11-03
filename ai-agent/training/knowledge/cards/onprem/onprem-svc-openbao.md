# On-premises service: OpenBao (Vault-compatible secrets)

The catalog id is `openbao`. Kind is service. Group is Secrets. Image is openbao/openbao:2.1.0. Published port is 8200. Extra ports are none. Roles are secrets. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: A secret manager with the HashiCorp Vault API (KV v2 at secret/): get_secret() / put_secret(), hvac, node-vault and the vault / bao CLI. The password is the access token. OpenBao's release images ship without its web UI, so use Browse secrets (pskit's UI: folders, versions, add / edit / delete). Backups hold the data and the unseal key: keep them safe.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-openbao --service openbao
pskit resources onprem status sample-openbao
```

pskit resources onprem usage sample-openbao prints how to connect. pskit resources onprem logs sample-openbao shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
