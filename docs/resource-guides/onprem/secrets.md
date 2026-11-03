# Secret managers on premises

Keep API keys, database passwords and certificates in a secret manager instead of files, and read them from handlers
with **one call that works on every provider**:

```python
from py_serverless_kit import get_secret, get_secrets, put_secret

def handler(event, ctx):
    password = get_secret("db-password")              # a plain secret
    webhook = get_secret("stripe", "webhook")         # one field of a JSON secret
    every = get_secrets("stripe")                     # {"key": "...", "webhook": "..."}
    put_secret("last-run", ctx.request_id)            # create or update (Vault / Secrets Manager)
```

```js
const { getSecret, getSecrets, putSecret } = require("pskit");

exports.handler = async (event, ctx) => {
  const password = await getSecret("db-password");
  const webhook = await getSecret("stripe", "webhook");
  const fallback = await getSecret("optional", { default: "" });
};
```

No extra library: the calls are part of the pskit runtime (Python standard library, Node.js built-ins). Values are
cached for 60 seconds per function instance.

## One click: OpenBao, pskit's Secrets Manager or LocalStack

*Resources → On-prem services → + Create service → Secret managers* (or the CLI):

| Service | API it speaks | Use it from | Keeps data |
|---|---|---|---|
| **OpenBao** (`openbao`) | HashiCorp Vault (KV v2 at `secret/`) | `get_secret`, `hvac`, `node-vault`, `vault` / `bao` CLI, Terraform's vault provider | yes: file storage in a volume, unsealed automatically on start |
| **AWS Secrets Manager compatible** (`secretsmanager` in Python, `secretsmanager-node` in Node.js) | AWS Secrets Manager, every request checked with SigV4 | `get_secret`, boto3, `@aws-sdk/client-secrets-manager`, the AWS CLI; its own web console at `/ui/` | yes: one JSON file in a volume (backups: `.tar.gz`) |
| **LocalStack** (`localstack`, *Use as: Secret manager*) | AWS Secrets Manager + SSM Parameter Store | `get_secret`, boto3, `@aws-sdk/client-secrets-manager`, the AWS CLI | yes (`PERSISTENCE=1`), for development and tests |

```bash
pskit resources onprem create secrets --service openbao --save                    # this machine
pskit resources onprem create secrets --service openbao --server edge1 --save     # a saved SSH server
pskit resources onprem create aws-secrets --service secretsmanager --user AKIAPROD --save   # SigV4, console
pskit resources onprem create aws-secrets --service localstack --role secrets --save
```

Name it **`secrets`** and handlers need no `store=`: it is the default store. Another key works too:
`get_secret("db-password", store="aws-secrets")` / `getSecret("db-password", { store: "aws-secrets" })`.

Creating it writes the connection to the env file (`.env.onprem`), which the host loads:

```bash
PSKIT_SECRETS_DRIVER=vault
PSKIT_SECRETS_URL=http://10.0.0.5:8200
PSKIT_SECRETS_TOKEN=...            # the service password is the OpenBao token
PSKIT_SECRETS_MOUNT=secret
```

OpenBao's password (from the create form, or generated) becomes a root token. Its first start initialises it with one
unseal key, kept in the data volume so every restart unseals by itself. That is convenient on one server; the volume
and backups then hold the key, so protect them like the secrets. For a hardened cluster (several unseal keys, auto-unseal
with a KMS, policies per app), run OpenBao or Vault yourself and point pskit at it (below).

## pskit's AWS Secrets Manager compatible server

`secretsmanager` (Python) and `secretsmanager-node` (Node.js) run pskit's own Secrets Manager server, whose code is in
[`aws/secretsmanager`](../../../aws/secretsmanager/README.md). The two are interchangeable and keep the same data file.
Unlike LocalStack it **checks every request's signature** (AWS Signature Version 4): the service's *user* is the access
key ID and its *password* the secret access key. Code written for AWS runs unchanged with `endpoint_url`:

```python
import os, boto3

sm = boto3.client("secretsmanager", endpoint_url=os.environ["PSKIT_AWS_SECRETS_URL"], region_name="us-east-1",
                  aws_access_key_id=os.environ["PSKIT_AWS_SECRETS_ACCESS_KEY"],
                  aws_secret_access_key=os.environ["PSKIT_AWS_SECRETS_SECRET_KEY"])
sm.create_secret(Name="prod/db", SecretString='{"user": "app", "password": "s3cret"}')
print(sm.get_secret_value(SecretId="prod/db")["SecretString"])
```

Creating it writes `PSKIT_<KEY>_DRIVER=aws`, `_URL`, `_REGION`, `_ACCESS_KEY` and `_SECRET_KEY` to the env file, so
`get_secret()` / `getSecret()` read it too. It supports CreateSecret, GetSecretValue, BatchGetSecretValue,
PutSecretValue, UpdateSecret, DescribeSecret, ListSecrets (filters, paging), DeleteSecret (7-30 day recovery window or
force), RestoreSecret, ListSecretVersionIds, UpdateSecretVersionStage (AWSCURRENT / AWSPREVIOUS), tags,
GetRandomPassword and resource policies (stored, not enforced). Rotation and replica regions are not supported.

Its **web console** (`http://<server>:4584/ui/`, *Web UI → Secrets console* on the service) signs in with the same
user and password: list and filter secrets, create one (key/value or plaintext, *Generate password*), show and copy
values, edit (each save is a new version), pick an old version and make it current, edit the description and tags,
delete with a recovery window and restore. The session is an HttpOnly cookie; ten wrong passwords lock that address
out for five minutes. The data file is not encrypted at rest: protect the server's disk and the backups.

Run it without pskit with the Dockerfiles in `aws/secretsmanager` (see its README).

## Infisical (secrets manager with a web UI)

`pskit resources onprem create vault --service infisical --save` (or *Secret managers → Infisical* in the studio)
starts Infisical with its own PostgreSQL and Redis. Then:

1. Open the web UI (`http://<server>:8080`) and create the admin account.
2. Create a project, then a **machine identity** with **Universal Auth**, and give it access to the project.
3. Fill these values in the env file (`.env.onprem`) and deploy:

```bash
PSKIT_VAULT_DRIVER=infisical            # written by pskit
PSKIT_VAULT_URL=http://10.0.0.5:8080    # written by pskit
PSKIT_VAULT_CLIENT_ID=...               # the machine identity
PSKIT_VAULT_CLIENT_SECRET=...
PSKIT_VAULT_PROJECT_ID=...              # Project settings -> Project ID
PSKIT_VAULT_ENVIRONMENT=dev             # dev / staging / prod (the environment slug)
# PSKIT_VAULT_PATH=/                    # folder, default /
# PSKIT_VAULT_TOKEN=...                 # instead of client id / secret: a service or access token
```

`get_secret("DB_PASSWORD", store="vault")` / `getSecret("DB_PASSWORD", { store: "vault" })` reads the secret's
value. A JSON object value becomes fields (`get_secret("db", "password", store="vault")`). `put_secret` creates or
updates one. The same driver works with Infisical Cloud: set `_URL` to `https://app.infisical.com`.

## Browse secrets in the studio

OpenBao's release images have no web UI ("OpenBao UI is not available in this binary"). Use **Browse secrets** on the
service's row (*Resources → On-prem services*). It shows folders and secrets (values hidden until *Show values*), and
lets you copy values, see versions, and add, edit (a new version) or delete secrets. LocalStack, LocalEmu and
pskit's Secrets Manager server get the same browser for Secrets Manager.

## Add and read secrets

| Where | How |
|---|---|
| Studio | *On-prem services → Console* on the service: `kv put secret/db-password value=S3cret`, `kv get secret/db-password` (OpenBao) or `secretsmanager create-secret --name db-password --secret-string S3cret` (LocalStack) |
| Web UI | OpenBao at `http://<host>:8200/ui/`, sign in with *Token* = the password (`PSKIT_<KEY>_TOKEN`); pskit's Secrets Manager at `http://<host>:4584/ui/` with the user and password |
| CLI | `pskit resources onprem console secrets "kv put secret/stripe key=sk_1 webhook=wh_2"` |
| Code | `put_secret("stripe", {"key": "sk_1", "webhook": "wh_2"})` |
| Any program | `vault kv get -address=http://host:8200 secret/db-password`, `hvac`, boto3 with `endpoint_url` |

A secret with one field named `value` is a plain secret: `get_secret(name)` returns it. With several fields,
`get_secret(name, field)` picks one and `get_secrets(name)` returns all of them.

## An existing Vault, OpenBao or AWS Secrets Manager

Set the store variables yourself (env file, `functions.*.environment`, or the host's environment):

| Store | Variables |
|---|---|
| Vault / OpenBao | `PSKIT_SECRETS_DRIVER=vault`, `PSKIT_SECRETS_URL=https://vault.internal:8200`, `PSKIT_SECRETS_TOKEN` (or `token_env` in your own tooling), optional `PSKIT_SECRETS_MOUNT` |
| AWS Secrets Manager | `PSKIT_SECRETS_DRIVER=aws`, optional `PSKIT_SECRETS_REGION`; credentials from `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`, or `PSKIT_SECRETS_ACCESS_KEY` / `_SECRET_KEY`. `PSKIT_SECRETS_URL` for a compatible endpoint |
| Environment only | nothing: `get_secret("db-password")` reads `PSKIT_SECRET_DB_PASSWORD`, then `DB_PASSWORD` |

## On the clouds

The same handler code runs everywhere:

- **AWS Lambda**: set `PSKIT_SECRETS_DRIVER: aws` in the function's `environment` and allow
  `secretsmanager:GetSecretValue` (and `PutSecretValue` / `CreateSecret` for `put_secret`) in its role. Lambda's
  credentials are used:

  ```yaml
  functions:
    api:
      handler: app.handlers.api
      environment: {PSKIT_SECRETS_DRIVER: aws}
      iam:
        statements:
          - {effect: Allow, actions: ["secretsmanager:GetSecretValue"], resources: ["arn:aws:secretsmanager:*:*:secret:*"]}
  ```
- **Other clouds** (Azure Key Vault, GCP Secret Manager, ...): map the secret into the function's environment with the
  provider's own reference, and the `env` driver reads it (`PSKIT_SECRET_<NAME>` or `<NAME>`). Or run OpenBao on a
  server and use the `vault` driver.

## Troubleshooting

| Message | Fix |
|---|---|
| `secret 'x' not found: set PSKIT_SECRET_X ...` | no store is configured for this function: check the env file has `PSKIT_SECRETS_URL` / `_TOKEN`, and that `provider.options.env_file` points to it |
| `vault: reading 'x' failed (403)` | wrong token: `PSKIT_<KEY>_TOKEN` must match the OpenBao password |
| `secret store host:8200 is unreachable` | the functions' server cannot reach the port: same server, or open 8200 from the functions' server to the secrets server |
| `secretsmanager: ... AccessDenied` | add the Secrets Manager permissions to the function's role |
