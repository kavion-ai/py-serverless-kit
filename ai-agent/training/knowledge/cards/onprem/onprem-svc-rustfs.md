# On-premises service: RustFS (S3-compatible)

The catalog id is `rustfs`. Kind is service. Group is Object storage. Image is rustfs/rustfs:latest. Published port is 9000. Extra ports are 9001. Roles are storage. Backup is no. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Console. GUI login choices are none.

Catalog notes: An S3-compatible object store with a web console (port 9001), an alternative to MinIO: the s3 driver, boto3 and the AWS CLI work with its endpoint.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-rustfs --service rustfs
pskit resources onprem status sample-rustfs
```

pskit resources onprem usage sample-rustfs prints how to connect. pskit resources onprem logs sample-rustfs shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
