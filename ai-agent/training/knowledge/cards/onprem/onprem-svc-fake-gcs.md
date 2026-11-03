# On-premises service: fake-gcs-server (Cloud Storage emulator)

The catalog id is `fake-gcs`. Kind is service. Group is Object storage. Image is fsouza/fake-gcs-server:1.52. Published port is 4443. Extra ports are none. Roles are storage. Backup is no. Persistent data is yes. Auth is no. Default user is pskit. Companion UI is none. Web UI names are none. GUI login choices are none.

Catalog notes: Google Cloud Storage JSON API: the gcs driver (emulator mode) and the google-cloud-storage library work with its endpoint. No authentication. For development and tests.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-fake-gcs --service fake-gcs
pskit resources onprem status sample-fake-gcs
```

pskit resources onprem usage sample-fake-gcs prints how to connect. pskit resources onprem logs sample-fake-gcs shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
