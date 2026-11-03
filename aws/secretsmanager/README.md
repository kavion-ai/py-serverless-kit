# AWS Secrets Manager compatible server

A self-hosted server that speaks the **AWS Secrets Manager API**, in two interchangeable implementations:

| | Path | Needs | Docker image (build it) |
|---|---|---|---|
| Python | `python/server.py` | Python 3.9+, standard library only | `python/Dockerfile` (`python:3.12-alpine`) |
| Node.js | `nodejs/server.js` | Node.js 18+, no npm packages | `nodejs/Dockerfile` (`node:22-alpine`) |
| Web console | `ui/index.html` | served by both at `/ui/` | included in both images |

boto3, the AWS SDKs (JavaScript v3, Java, Go, .NET ...), the AWS CLI and pskit's `get_secret()` work with it
unchanged: give them its endpoint and an access key / secret key it knows. Every request is checked with
**AWS Signature Version 4** as AWS does, so a wrong secret key, an unknown access key or a request more than
15 minutes old is refused.

pskit runs it as a one-click on-prem service (`secretsmanager` / `secretsmanager-node`, see
[docs/resource-guides/onprem/secrets.md](../../docs/resource-guides/onprem/secrets.md)). You can also run it on
its own, as below.

## Run it

```bash
cd aws/secretsmanager

# Docker (Python or Node.js; build from this folder so the console is included)
docker build -f python/Dockerfile -t pskit/secretsmanager:python .
docker run -d --name secretsmanager -p 127.0.0.1:4584:4584 -v secretsmanager-data:/data \
  -e SM_ACCESS_KEY_ID=AKIAPROD -e SM_SECRET_ACCESS_KEY='a-long-random-secret'   -e SM_MASTER_KEY="$(openssl rand -base64 32)" pskit/secretsmanager:python

# or docker compose (pick one of the two services)
SM_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d secretsmanager-nodejs

# or no Docker at all
SM_SECRET_ACCESS_KEY='a-long-random-secret' python python/server.py
SM_SECRET_ACCESS_KEY='a-long-random-secret' node nodejs/server.js
```

The images run as an unprivileged user (uid 10001), keep the data in `/data` and have a health check
(`server.py --check` / `server.js --check`, which reads `/health`).

## Settings

| Variable | Default | |
|---|---|---|
| `SM_ACCESS_KEY_ID` | `pskit` | the access key ID clients sign with |
| `SM_SECRET_ACCESS_KEY` | (required) | its secret access key; also the console password |
| `SM_CREDENTIALS` | | more keys: `id1:secret1,id2:secret2` |
| `SM_AUTH` | `sigv4` | `off` turns authentication off (development only) |
| `SM_PORT` / `SM_BIND` | `4584` / `0.0.0.0` | where it listens |
| `SM_DATA_DIR` | `./data` (`/data` in the images) | holds `secretsmanager.json` |
| `SM_REGION` / `SM_ACCOUNT_ID` | `us-east-1` / `000000000000` | for ARNs (a request's own region wins) |
| `SM_UI` | `on` | `off` removes the web console |
| `SM_UI_PASSWORD` | | a console password other than the secret keys |
| `SM_MASTER_KEY` | | encrypts the values at rest: 32 random bytes in base64 (`openssl rand -base64 32`), key id `default` |
| `SM_MASTER_KEYS` | | more master keys: `id1:base64key,id2:base64key` (`KmsKeyId` picks one) |
| `SM_MASTER_KEY_ID` | `default` | the master key of secrets without a `KmsKeyId`; changing it rewraps on the next start |
| `SM_ENCRYPTION` | `aes-256-gcm` with a key | `chacha20-poly1305`, `aes-256-cbc-hmac`, or `off` |

The server refuses to start without a credential unless `SM_AUTH=off`.

## Use it

```python
import boto3

sm = boto3.client("secretsmanager", endpoint_url="http://127.0.0.1:4584", region_name="us-east-1",
                  aws_access_key_id="AKIAPROD", aws_secret_access_key="a-long-random-secret")
sm.create_secret(Name="prod/db", SecretString='{"user": "app", "password": "s3cret"}')
sm.put_secret_value(SecretId="prod/db", SecretString='{"user": "app", "password": "n3w"}')
print(sm.get_secret_value(SecretId="prod/db")["SecretString"])                            # the new value
print(sm.get_secret_value(SecretId="prod/db", VersionStage="AWSPREVIOUS")["SecretString"])  # the old one
```

```js
const { SecretsManagerClient, GetSecretValueCommand } = require("@aws-sdk/client-secrets-manager");

const sm = new SecretsManagerClient({
  endpoint: "http://127.0.0.1:4584",
  region: "us-east-1",
  credentials: { accessKeyId: "AKIAPROD", secretAccessKey: "a-long-random-secret" },
});
console.log((await sm.send(new GetSecretValueCommand({ SecretId: "prod/db" }))).SecretString);
```

```bash
export AWS_ACCESS_KEY_ID=AKIAPROD AWS_SECRET_ACCESS_KEY='a-long-random-secret' AWS_DEFAULT_REGION=us-east-1
aws --endpoint-url http://127.0.0.1:4584 secretsmanager list-secrets
```

### Operations

| Supported | Notes |
|---|---|
| CreateSecret, PutSecretValue, UpdateSecret | `SecretString` or `SecretBinary` (64 KB), `ClientRequestToken` idempotency, tags, description, `KmsKeyId` (picks the master key, see below) |
| GetSecretValue, BatchGetSecretValue | by name, full ARN or ARN without the random suffix; `VersionId` / `VersionStage` |
| DescribeSecret, ListSecrets | filters `name`, `description`, `tag-key`, `tag-value`, `all` (prefix match, `!` negates), `MaxResults` / `NextToken`, `SortOrder`, `IncludePlannedDeletion` |
| DeleteSecret, RestoreSecret | recovery window of 7-30 days (default 30) or `ForceDeleteWithoutRecovery` |
| ListSecretVersionIds, UpdateSecretVersionStage | `AWSCURRENT` / `AWSPREVIOUS` move like AWS; up to 100 versions are kept |
| TagResource, UntagResource, GetRandomPassword | |
| Put/Get/Delete/ValidateResourcePolicy | stored and returned, not enforced |

Not supported: RotateSecret, CancelRotateSecret and replica regions (they answer `InvalidRequestException`).

## Web console

Open `http://127.0.0.1:4584/ui/` and sign in with an access key ID and its secret access key (or the
`SM_UI_PASSWORD`). You can list and filter secrets, create them (key/value pairs or plaintext, *Generate password*),
show and copy values, save a new version, make an old version current, edit the description and tags, delete with
a recovery window and restore.

The session lives in an `HttpOnly`, `SameSite=Strict` cookie for 12 hours and every console request carries a
token only the page knows, so other sites cannot use it. Ten failed sign-ins from one address lock that address out
for five minutes. The page sets a strict Content-Security-Policy and cannot be framed.

## Encryption at rest

With a master key, every secret version is encrypted before it is written, the way AWS Secrets Manager uses KMS
(envelope encryption):

```
GetSecretValue (SigV4-signed) -> check the signature -> unwrap the version's data key with the master key
                              -> decrypt the value  -> SecretString / SecretBinary in the response
secretsmanager.json           -> only ciphertext, the wrapped data key, nonces and tags
```

- Each version gets its own random 256-bit **data key**, which encrypts the value. The data key is stored wrapped
  (AES-256-GCM) by the **master key**, which lives only in the environment, never in the volume.
- The value is bound to `ARN|VersionId` (authenticated data), so a ciphertext can't be copied to another secret or
  version, and any change to the file is detected: the server refuses to start rather than serve wrong data.
- Clients don't change. Whoever can sign requests (an access key / secret key, or the console sign-in) gets the
  values decrypted; whoever only has the disk, the volume or a backup gets ciphertext.

| `SM_ENCRYPTION` | Algorithm | Notes |
|---|---|---|
| `aes-256-gcm` (default) | AES-256 in GCM mode, 96-bit nonce, 128-bit tag | the NIST standard; what AWS KMS uses |
| `chacha20-poly1305` | ChaCha20-Poly1305 (RFC 8439) | fast without AES hardware; used by TLS 1.3 and WireGuard |
| `aes-256-cbc-hmac` | AES-256-CBC + HMAC-SHA256, encrypt-then-MAC | for policies that require CBC; keys split from the data key with HKDF-SHA256 |

Every version records its algorithm and master key id, so changing `SM_ENCRYPTION` affects only new versions.
The Python server has no third-party packages: AES, GCM, ChaCha20 and Poly1305 are written out in `server.py` and
checked against the FIPS-197, NIST SP 800-38D and RFC 8439 test vectors and against Node.js's `crypto`. The Node.js
server uses `crypto`. Both read what the other wrote.

**Several master keys.** `SM_MASTER_KEYS=team-a:<key>,team-b:<key>` adds named keys; `KmsKeyId` on CreateSecret /
UpdateSecret picks one (`team-b`, `alias/team-b` or a KMS ARN ending in either; `alias/aws/secretsmanager` means the
default). An unknown `KmsKeyId` is refused with `InvalidRequestException`.

**Rotating the master key.** Add the new key to `SM_MASTER_KEYS`, set `SM_MASTER_KEY_ID` to its id and restart:
the server rewraps every data key (the values are not re-encrypted). Then remove the old key. `server.py --rewrap`
/ `server.js --rewrap` does the same and exits, without serving.

**Turning it on or off.** A plain file is encrypted on the first start with a master key. With
`SM_ENCRYPTION=off` and the key still set, the next start writes it back in plain text.

**Keep the master key safe and back it up apart from the data.** Without it the secrets can't be read; with a wrong
one the server refuses to start. pskit generates it when it creates the service and keeps it in the env file
(`<PREFIX>_MASTER_KEY`); re-creating the service reuses it.

## Security notes

- Run it behind TLS (a reverse proxy) when clients reach it over a network you do not trust: SigV4 protects the
  keys and the request from changes, not the secret values in the response.
- The data is one JSON file (`secretsmanager.json`, mode 600), written atomically. Without `SM_MASTER_KEY` it is
  **not encrypted at rest** (the server logs a warning): protect the disk, the volume and backups like the secrets.
- Encryption at rest protects the file, the volume and backups. It doesn't protect against someone who can sign
  requests, or who can read the server's memory or environment (where the master key is).
- Resource policies are not enforced: everyone with a valid key can read and change every secret.

## Data file

The Python and Node.js servers read and write the same file format, so you can switch between them on the same
volume. Back up `/data` (`tar czf - -C /data .`), which is what pskit's *Backup* does.
