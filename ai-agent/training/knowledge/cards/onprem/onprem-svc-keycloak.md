# On-premises service: Keycloak (login, SSO, OAuth2 / OIDC)

The catalog id is `keycloak`. Kind is service. Group is Identity. Image is quay.io/keycloak/keycloak:26.0. Published port is 8080. Extra ports are none. Roles are custom. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Admin console. GUI login choices are none.

Catalog notes: Identity provider: users, groups, social login, MFA and OpenID Connect / OAuth2 tokens for your APIs. Runs in dev mode (H2 database in the volume, HTTP); put it behind HTTPS for production.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-keycloak --service keycloak
pskit resources onprem status sample-keycloak
```

pskit resources onprem usage sample-keycloak prints how to connect. pskit resources onprem logs sample-keycloak shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
