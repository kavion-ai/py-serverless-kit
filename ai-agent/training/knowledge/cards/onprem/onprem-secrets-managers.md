# Secret managers on premises

Keep API keys, database passwords and certificates in a secret manager instead of files, and read them from handlers with **one call that works on every provider**: No extra library: the calls are part of the pskit runtime (Python standard library, Node.js built-ins). Values are cached for 60 seconds per function instance.
## One click: OpenBao, pskit's

Secrets Manager or LocalStack *Resources → On-prem services → + Create service → Secret managers* (or the CLI): | Service | API it speaks | Use it from | Keeps data | |---|---|---|---| | **OpenBao** (`openbao`) | HashiCorp Vault (KV v2 at `secret/`) | `get_secret`, `hvac`, `node-vault`, `vault` / `bao` CLI, Terraform's vault provider | yes: file storage in a volume, unsealed automatically on start | | **AWS Secrets Manager compatible** (`secretsmanager` in Python, `secretsmanager-node` in Node.js) | AWS Secrets Manager, every request checked with SigV4 | `get_secret`, boto3, `@aws-sdk/client-secrets-manager`, the AWS CLI; its own web console at `/ui/` | yes: one JSON file in a volume (backups: `.tar.gz`) | | **LocalStack** (`localstack`, *Use as: Secret manager*) | AWS Secrets Manager + SSM Parameter Store | `get_secret`, boto3, `@aws-sdk/client-secrets-manager`, the AWS CLI | yes (`PERSISTENCE=1`), for development and tests | Name it **`secrets`** and handlers need no `store=`: it is the default store. Another key works too: `get_secret("db-password", store="aws-secrets")` / `getSecret("db-password", { store: "aws-secrets" })`. Creating it writes the connection to the env file (`.env.onprem`), which the host loads: OpenBao's password (from the create form, or generated) becomes a root token. Its first start initialises it with one unseal key, kept in the data volume so every restart unseals by itself. That is convenient on one server; the volume and backups then hold the key, so protect them like the secrets. For a hardened cluster (several unseal keys, auto-unseal with a KMS, policies per app), run OpenBao or Vault yourself and point pskit at it (below).
## pskit's AWS Secrets Manager compatible server `secretsmanager` (Python)

and `secretsmanager-node` (Node.js) run pskit's own Secrets Manager server, whose code is in `aws/secretsmanager`. The two are interchangeable and keep the same data file. Unlike LocalStack it **checks every request's signature** (AWS Signature Version 4): the service's *user* is the access key ID and its *password* the secret access key. Code written for AWS runs unchanged with `endpoint_url`: Creating it writes `PSKIT_<KEY>_DRIVER=aws`, `_URL`, `_REGION`, `_ACCESS_KEY` and `_SECRET_KEY` to the env file, so `get_secret()` / `getSecret()` read it too.

```python
from py_serverless_kit import get_secret, get_secrets, put_secret

def handler(event, ctx):
    password = get_secret("db-password")              # a plain secret
    webhook = get_secret("stripe", "webhook")         # one field of a JSON secret
    every = get_secrets("stripe")                     # {"key": "...", "webhook": "..."}
    put_secret("last-run", ctx.request_id)            # create or update (Vault / Secrets Manager)
```
