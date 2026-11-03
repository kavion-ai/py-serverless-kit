# On-premises service: AWS Secrets Manager compatible (Python)

The catalog id is `secretsmanager`. Kind is service. Group is Secrets. Image is python:3.12-alpine. Published port is 4584. Extra ports are none. Roles are secrets. Backup is yes. Persistent data is yes. Auth is yes. Default user is pskit. Companion UI is none. Web UI names are Secrets console. GUI login choices are none.

Catalog notes: pskit's own Secrets Manager server (Python, code in aws/secretsmanager): the Secrets Manager API with SigV4 authentication (user = access key ID, password = secret access key). boto3, the AWS SDKs, the AWS CLI and get_secret() work with its endpoint. Versions and stages, tags, delete with a recovery window, restore. Values are encrypted at rest (AES-256-GCM, a data key per version wrapped by a generated master key). Its own web console (/ui/) signs in with the same user and password.

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-secretsmanager --service secretsmanager
pskit resources onprem status sample-secretsmanager
```

pskit resources onprem usage sample-secretsmanager prints how to connect. pskit resources onprem logs sample-secretsmanager shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
