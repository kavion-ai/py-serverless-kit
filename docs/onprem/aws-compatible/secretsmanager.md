# AWS Secrets Manager compatible server (secretsmanager, secretsmanager-node)

Search terms: Secrets Manager compatible server, self-hosted Secrets Manager, secretsmanager-node, get_secret,
put_secret, boto3 secretsmanager endpoint_url, client-secrets-manager, master key, encryption at rest, secrets console,
AWSCURRENT AWSPREVIOUS, InvalidSignatureException

The AWS Secrets Manager compatible server is pskit's own implementation of the AWS Secrets Manager API, in the
repository folder `aws/secretsmanager` (`python/server.py` and `nodejs/server.js`, both with the console page
`ui/index.html`). boto3, the AWS SDKs, the AWS CLI and pskit's `get_secret()` / `getSecret()` work with it unchanged
once they point at its endpoint and sign with a key it knows. Unlike LocalStack, it checks every request's SigV4
signature and encrypts the values at rest.

## Secrets Manager server at a glance

The Secrets Manager compatible server has these properties (from `core/onprem_secretsmanager.py` and the server code):

| | |
|---|---|
| pskit service | `secretsmanager` (Python) or `secretsmanager-node` (Node.js), interchangeable |
| Port | `4584` |
| Protocol | AWS JSON 1.1: `POST /` with `X-Amz-Target: secretsmanager.<Operation>` |
| Authentication | AWS Signature Version 4 in the `Authorization` header (no presigned URLs, no SigV2) |
| Access key ID / secret key | the service's *User* (default `pskit`) / *Password* |
| Region | any region; ARNs carry the region you sign with |
| Web console | `http://<address>:<port>/ui/` |
| Health | `GET /health` or `/healthz` |
| Data | one JSON file `/data/secretsmanager.json` (mode 600); values encrypted with a master key pskit generates |
| Not supported | rotation (`RotateSecret`, `CancelRotateSecret`) and replica regions |

## Secrets Manager server API coverage

The Secrets Manager server supports these operations (the `OPERATIONS` table in both implementations):

| Operation | Notes |
|---|---|
| CreateSecret, PutSecretValue, UpdateSecret | `SecretString` or `SecretBinary` (base64, up to 64 KB), `ClientRequestToken` idempotency, tags, description, `KmsKeyId` (picks the master key) |
| GetSecretValue, BatchGetSecretValue | by name, full ARN, or ARN without the random suffix; `VersionId` / `VersionStage` |
| DescribeSecret, ListSecrets | filters `name`, `description`, `tag-key`, `tag-value`, `all` (prefix match, `!` negates), `MaxResults` / `NextToken`, `SortOrder`, `IncludePlannedDeletion` |
| DeleteSecret, RestoreSecret | `RecoveryWindowInDays` 7-30 (default 30) or `ForceDeleteWithoutRecovery` (not both) |
| ListSecretVersionIds, UpdateSecretVersionStage | `AWSCURRENT` / `AWSPREVIOUS` move like AWS; up to 100 versions per secret are kept |
| TagResource, UntagResource | |
| GetRandomPassword | `PasswordLength` 1-4096 (default 32) and the usual exclude options |
| PutResourcePolicy, GetResourcePolicy, DeleteResourcePolicy, ValidateResourcePolicy | stored and returned, **not enforced** |

`RotateSecret`, `CancelRotateSecret`, `ReplicateSecretToRegions`, `RemoveRegionsFromReplication` and
`StopReplicationToReplica` answer `InvalidRequestException`. Any other operation answers `UnknownOperationException`.
Request bodies are limited to 1 MiB.

Error responses are JSON (`{"__type": "<code>", "message": "..."}` and the `x-amzn-ErrorType` header), as on AWS:

| Code | When |
|---|---|
| `MissingAuthenticationTokenException` | no `Authorization` header |
| `IncompleteSignatureException` | malformed `Authorization`, credential or `X-Amz-Date` |
| `UnrecognizedClientException` | unknown access key ID |
| `InvalidSignatureException` | wrong secret key, clock more than 15 minutes off, wrong scope (service must be `secretsmanager`), bad `SignedHeaders`, body hash mismatch |
| `ResourceNotFoundException` | the secret or version does not exist |
| `ResourceExistsException` | CreateSecret on an existing name, or a reused `ClientRequestToken` with another value |
| `InvalidParameterException`, `InvalidRequestException` | a bad parameter, or an operation not allowed in the secret's state (for example scheduled for deletion) |
| `MalformedPolicyDocumentException` | a resource policy that is not JSON |
| `SerializationException`, `UnknownOperationException` | body not a JSON object or too large; unknown `X-Amz-Target` |
| `InternalServiceError` | an unexpected server error (HTTP 500) |

## Create the Secrets Manager server in studio

The Secrets Manager server is created from the *Resources* page in studio:

1. Open **Resources** in the sidebar.
2. Click **+ On-prem service** in the page header (or **+ Create service** in the *On-prem services* card).
3. Under **Secret managers**, click **AWS Secrets Manager compatible (Python)** or **AWS Secrets Manager compatible
   (Node.js)**.
4. **Resource key**: the form suggests `secrets`. Keep `secrets`: it is the default store, so handlers call
   `get_secret("name")` without `store=`.
5. **Use as**: *Secret manager*.
6. **Where**: *This machine*, *One SSH server* (a saved **Server**, or **Host** / **User** / **SSH port** / **Log in
   with**), or *Scaling cluster*.
7. **Port**: empty means `4584`.
8. **Security**: **User** becomes the access key ID (empty: `pskit`), **Password** the secret access key (empty:
   generated). **Listen on**: `127.0.0.1` or `0.0.0.0`.
9. **Web UI** shows *Secrets console* (built in).
10. Click **Create**, wait for *Created*, then click **Save** in the top bar to write `pskit.yml`.

## Create the Secrets Manager server from the terminal

The Secrets Manager server is created with `pskit resources onprem create`:

```bash
pskit resources onprem create secrets --service secretsmanager --save                   # Python, this machine
pskit resources onprem create secrets --service secretsmanager-node --server edge1 --save
pskit resources onprem create aws-secrets --service secretsmanager --user AKIAPROD --password-env SM_PW --save
```

Options are the same as for every on-prem service (`--user`, `--password` / `--password-env`, `--port`, `--bind`,
`--ssh`, `--pem`, `--server`, `--cluster`, `--save`; see `pskit resources onprem create --help`). Then:

```bash
pskit resources onprem status secrets                                 # state, health, console link
pskit resources onprem usage secrets --reveal                         # endpoint, keys, code snippets
pskit resources onprem console secrets "secretsmanager list-secrets"  # AWS CLI in a helper container
pskit resources onprem backup secrets                                 # .tar.gz of /data
```

## What the Secrets Manager server adds to pskit.yml and the env file

Creating the Secrets Manager server writes a `custom` resource with the connection, and the credentials to the env
file. For key `secrets`:

```yaml
resources:
  secrets:
    type: custom
    external: true
    connection:
      driver: aws
      url: http://127.0.0.1:4584
      region: us-east-1
      access_key_env: PSKIT_SECRETS_ACCESS_KEY
      secret_key_env: PSKIT_SECRETS_SECRET_KEY
      console_url: http://127.0.0.1:4584/ui/
```

```bash
# .env.onprem
PSKIT_SECRETS_DRIVER=aws
PSKIT_SECRETS_URL=http://127.0.0.1:4584
PSKIT_SECRETS_REGION=us-east-1
PSKIT_SECRETS_ACCESS_KEY=pskit
PSKIT_SECRETS_SECRET_KEY=...
PSKIT_SECRETS_MASTER_KEY=...        # encrypts the values at rest; back it up apart from the data
```

`get_secret()` picks its store from `PSKIT_<STORE>_*` variables, and the default store is `secrets`. That is why the
key `secrets` needs no `store=` argument; any other key is used as `store="<key>"`.

## Use the Secrets Manager server from a pskit handler

A pskit handler reads and writes the Secrets Manager server with `get_secret` and `put_secret`; the on-prem host loads
the env file, so no client code is needed:

```python
from py_serverless_kit import get_secret, get_secrets, put_secret


def handler(event, ctx):
    password = get_secret("prod/db", "password")          # one field of a JSON secret
    api_key = get_secret("api-key")                       # a plain string secret
    fields = get_secrets("prod/db")                       # every field as a dict
    put_secret("last-run", ctx.request_id)                # PutSecretValue, or CreateSecret the first time
    other = get_secret("prod/db", "password", store="aws-secrets")   # a service with another key
    return {"user": fields.get("user"), "has_key": bool(api_key), "same": password == other}
```

```js
const { getSecret, putSecret } = require("pskit");

exports.handler = async (event, ctx) => {
  const password = await getSecret("prod/db", "password");
  await putSecret("last-run", ctx.requestId);
  return { ok: Boolean(password) };
};
```

A JSON object secret becomes fields; any other string is the field `value`. Reads are cached for 60 seconds. The same
handler code reads AWS Secrets Manager on AWS. See [../../handlers.md](../../handlers.md#get_secret-secrets-on-every-provider).

## Use the Secrets Manager server from boto3 (Python)

boto3 works with the Secrets Manager server with `endpoint_url`, a region and the keys (no addressing option needed):

```python
import json
import os

import boto3

sm = boto3.client(
    "secretsmanager",
    endpoint_url=os.environ["PSKIT_SECRETS_URL"],          # http://127.0.0.1:4584
    region_name="us-east-1",
    aws_access_key_id=os.environ["PSKIT_SECRETS_ACCESS_KEY"],
    aws_secret_access_key=os.environ["PSKIT_SECRETS_SECRET_KEY"],
)
sm.create_secret(Name="prod/db", SecretString=json.dumps({"user": "app", "password": "s3cret"}))
sm.put_secret_value(SecretId="prod/db", SecretString=json.dumps({"user": "app", "password": "n3w"}))
print(sm.get_secret_value(SecretId="prod/db")["SecretString"])                              # the new value
print(sm.get_secret_value(SecretId="prod/db", VersionStage="AWSPREVIOUS")["SecretString"])  # the old one
for page in sm.get_paginator("list_secrets").paginate(Filters=[{"Key": "name", "Values": ["prod/"]}]):
    print([s["Name"] for s in page["SecretList"]])
sm.delete_secret(SecretId="prod/db", RecoveryWindowInDays=7)
sm.restore_secret(SecretId="prod/db")
print(sm.get_random_password(PasswordLength=24, ExcludePunctuation=True)["RandomPassword"])
```

## Use the Secrets Manager server from the AWS SDK for JavaScript v3

The AWS SDK for JavaScript v3 (`@aws-sdk/client-secrets-manager`) works with the Secrets Manager server with
`endpoint`, `region` and the keys:

```js
const {
  SecretsManagerClient, CreateSecretCommand, GetSecretValueCommand, PutSecretValueCommand,
} = require("@aws-sdk/client-secrets-manager");

const sm = new SecretsManagerClient({
  endpoint: process.env.PSKIT_SECRETS_URL,    // http://127.0.0.1:4584
  region: "us-east-1",
  credentials: { accessKeyId: process.env.PSKIT_SECRETS_ACCESS_KEY, secretAccessKey: process.env.PSKIT_SECRETS_SECRET_KEY },
});

async function main() {
  await sm.send(new CreateSecretCommand({ Name: "api-key", SecretString: "abc123" }));
  await sm.send(new PutSecretValueCommand({ SecretId: "api-key", SecretString: "def456" }));
  const out = await sm.send(new GetSecretValueCommand({ SecretId: "api-key" }));
  console.log(out.SecretString, out.VersionStages);
}
main();
```

## Use the Secrets Manager server from the AWS CLI

The AWS CLI works with the Secrets Manager server through `--endpoint-url`:

```bash
export AWS_ACCESS_KEY_ID=pskit AWS_SECRET_ACCESS_KEY='<PSKIT_SECRETS_SECRET_KEY>' AWS_DEFAULT_REGION=us-east-1
aws --endpoint-url http://127.0.0.1:4584 secretsmanager create-secret --name api-key --secret-string abc123
aws --endpoint-url http://127.0.0.1:4584 secretsmanager get-secret-value --secret-id api-key
aws --endpoint-url http://127.0.0.1:4584 secretsmanager list-secrets
aws --endpoint-url http://127.0.0.1:4584 secretsmanager list-secret-version-ids --secret-id api-key
aws --endpoint-url http://127.0.0.1:4584 secretsmanager delete-secret --secret-id api-key --force-delete-without-recovery
```

`pskit resources onprem console secrets "secretsmanager get-random-password"` runs the same commands (without `aws`
and `--endpoint-url`) in an `amazon/aws-cli` helper container with the service's keys.

## Open the Secrets Manager web console

The Secrets Manager web console is served by the server at `/ui/`:

- **In studio**: *Resources* > *On-prem services* card > **Details** on the service row > **Web UI** > **Open Secrets
  console**.
- **From the terminal**: `pskit resources onprem status secrets` prints the link.

Sign in with **Access key ID** and **Secret access key (password)**. The console lists and filters secrets, creates
them (key/value pairs or plaintext, *Generate password*), shows and copies values, saves a new version, makes an old
version current (*Make current*), edits the description and tags, deletes with a recovery window (*Recovery window
(days, 7-30)*) and restores. The session is an `HttpOnly`, `SameSite=Strict` cookie for 12 hours; ten failed sign-ins
from one address lock it out for five minutes.

Studio has its own browser as well: **Browse secrets** on the service row opens *Secrets (Secrets Manager)* with **+ New
secret**, **Refresh**, **Show values**, **Copy**, **Edit** (key/value rows, **+ Key**, **Save**) and **Delete**.

## Secrets Manager server encryption at rest

The Secrets Manager server encrypts every secret version when a master key is set, the way AWS Secrets Manager uses
KMS (envelope encryption). pskit generates the master key when it creates the service (32 random bytes, base64) and
passes it as `SM_MASTER_KEY`.

- Each version gets its own random 256-bit data key, which encrypts the value. The data key is stored wrapped
  (AES-256-GCM) by the master key, which lives only in the environment, never in the volume.
- The value is bound to `ARN|VersionId`, so a ciphertext cannot be moved to another secret, and any change to the file
  is detected: the server refuses to start rather than serve wrong data.
- Clients do not change: signed callers get the values decrypted. The disk, the volume and backups hold ciphertext.

| `SM_ENCRYPTION` | Algorithm |
|---|---|
| `aes-256-gcm` (default with a key) | AES-256-GCM, 96-bit nonce, 128-bit tag |
| `chacha20-poly1305` | ChaCha20-Poly1305 (RFC 8439) |
| `aes-256-cbc-hmac` | AES-256-CBC + HMAC-SHA256, encrypt-then-MAC, keys split with HKDF-SHA256 |
| `off` | plain file (the next start decrypts an encrypted file) |

`SM_MASTER_KEYS=id1:base64key,id2:base64key` adds named keys; `KmsKeyId` on CreateSecret / UpdateSecret picks one
(`id`, `alias/id`, or a KMS ARN ending in either; `alias/aws/secretsmanager` is the default key). To rotate the master
key, add the new key to `SM_MASTER_KEYS`, set `SM_MASTER_KEY_ID` to its id and restart: the data keys are rewrapped.
`server.py --rewrap` / `server.js --rewrap` does the same and exits. The pskit one-click service sets only
`SM_MASTER_KEY`; the other encryption variables need the standalone server.

**Keep `PSKIT_<KEY>_MASTER_KEY` safe and back it up apart from the data.** Without it the secrets cannot be read; with
a wrong one the server refuses to start. pskit reuses the value already in the env file when you create the service
again, but *Remove* deletes the line from the env file even when the data is kept (see
[README.md](README.md#switch-between-the-python-and-nodejs-implementation)).

## Run the Secrets Manager server standalone with docker compose

The Secrets Manager server runs without pskit from the `aws/secretsmanager` folder:

```bash
cd aws/secretsmanager

SM_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d secretsmanager-python    # or secretsmanager-nodejs

docker build -f python/Dockerfile -t pskit/secretsmanager:python .     # or nodejs/Dockerfile
docker run -d --name secretsmanager -p 127.0.0.1:4584:4584 -v secretsmanager-data:/data \
  -e SM_ACCESS_KEY_ID=AKIAPROD -e SM_SECRET_ACCESS_KEY='a-long-random-secret' \
  -e SM_MASTER_KEY="$(openssl rand -base64 32)" pskit/secretsmanager:python

SM_SECRET_ACCESS_KEY='a-long-random-secret' python python/server.py      # no Docker; data in ./data
```

The compose file does not set `SM_MASTER_KEY`, so add it there for encryption at rest; without it the server logs a
warning and stores values in plain text. Settings:

| Variable | Default | Meaning |
|---|---|---|
| `SM_ACCESS_KEY_ID` / `SM_SECRET_ACCESS_KEY` | `pskit` / (required) | the key pair clients sign with; also the console login |
| `SM_CREDENTIALS` | | more keys: `id1:secret1,id2:secret2` |
| `SM_AUTH` | `sigv4` | `off` turns authentication off (development only) |
| `SM_PORT` / `SM_BIND` | `4584` / `0.0.0.0` | where it listens |
| `SM_DATA_DIR` | `./data` (`/data` in the images) | holds `secretsmanager.json` |
| `SM_REGION` / `SM_ACCOUNT_ID` | `us-east-1` / `000000000000` | for ARNs (a request's own region wins) |
| `SM_UI` / `SM_UI_PASSWORD` / `SM_UI_FILE` | `on` / / | the console, another console password, another console page |
| `SM_MASTER_KEY`, `SM_MASTER_KEYS`, `SM_MASTER_KEY_ID`, `SM_ENCRYPTION` | | encryption at rest (above) |

## Troubleshoot the Secrets Manager server

| Symptom | Cause and fix |
|---|---|
| `InvalidSignatureException: ... does not match` | Wrong secret key. Use `PSKIT_<KEY>_SECRET_KEY` from the env file (`pskit resources onprem usage <key> --reveal`). |
| `InvalidSignatureException: Signature expired` | Client and server clocks differ by more than 15 minutes. Sync both with NTP. |
| `UnrecognizedClientException` | The access key ID is not the service's *User*. |
| `get_secret` reads environment variables instead | `PSKIT_<STORE>_DRIVER` is missing: the service key is not `secrets` and no `store=` was given, or the env file is not loaded (`provider.options.env_file`). |
| `InvalidRequestException: ... marked for deletion` | The secret is scheduled for deletion; `RestoreSecret` brings it back during the recovery window. After the window it is gone (`ResourceNotFoundException`). |
| Container restarts, log says it cannot decrypt | The master key changed. Put the old `PSKIT_<KEY>_MASTER_KEY` back in the env file and create the service again. |
| `InvalidRequestException` on RotateSecret | Rotation and replicas are not supported; rotate by writing a new version with `put_secret`. |
| Port 4584 not reachable from another server | **Listen on** `127.0.0.1` or a firewall; use `pskit resources onprem tunnel <key>` or open the port. |

## See also

- [README.md](README.md): the AWS-compatible servers, Python vs Node.js, switching implementations
- [s3.md](s3.md)
- [../services/secretsmanager.md](../services/secretsmanager.md): the catalog entry
- [../resources.md](../resources.md)
- [../../resource-guides/onprem/secrets.md](../../resource-guides/onprem/secrets.md)
- [../../handlers.md](../../handlers.md) and [../../nodejs.md](../../nodejs.md)
- AWS Secrets Manager API reference: <https://docs.aws.amazon.com/secretsmanager/latest/apireference/Welcome.html>
