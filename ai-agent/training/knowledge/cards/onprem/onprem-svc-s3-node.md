# On-premises service: Amazon S3 compatible (Node.js)

The catalog id is `s3-node`. Kind is service. Group is Object storage. Image is node:22-alpine. Published port is 9000. Extra ports are none. Roles are storage. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are S3 console. GUI login choices are none.

Catalog notes: pskit's own S3 server (Node.js, code in aws/s3): the S3 API with SigV4 authentication (user = access key ID, password = secret access key). boto3, the AWS SDKs, the AWS CLI and the s3 driver work with its endpoint. Versioning, multipart uploads, presigned URLs, policies, CORS, lifecycle rules, object lock, website hosting. Its own web console (/ui/) signs in with the same user and password.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-s3-node --service s3-node
pskit resources onprem status sample-s3-node
```

pskit resources onprem usage sample-s3-node prints how to connect. pskit resources onprem logs sample-s3-node shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
