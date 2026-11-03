# On-premises service: MinIO (S3-compatible)

The catalog id is `minio`. Kind is service. Group is Object storage. Image is bitnamilegacy/minio:2025.7.23. Published port is 9000. Extra ports are 9001. Roles are storage. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Console. GUI login choices are none.

Catalog notes: Buckets watched through the minio driver. Console on port 9001.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-minio --service minio
pskit resources onprem status sample-minio
```

pskit resources onprem usage sample-minio prints how to connect. pskit resources onprem logs sample-minio shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
