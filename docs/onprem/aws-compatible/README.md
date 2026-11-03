# AWS-compatible servers (S3 and Secrets Manager on premises)

Search terms: AWS compatible, self-hosted S3, S3 compatible server, Secrets Manager compatible server, boto3
endpoint_url, on-prem AWS, s3-node, secretsmanager-node, SigV4, aws folder, LocalStack alternative

pskit ships two servers that speak an AWS API: an **Amazon S3 compatible server** and an **AWS Secrets Manager
compatible server**. Code written for AWS (boto3, the AWS SDK for JavaScript v3, the AWS CLI, any other AWS SDK) runs
against them on your own machines with only an endpoint change. Each server exists in two interchangeable
implementations, one in Python and one in Node.js.

| Page | What it covers |
|---|---|
| [s3.md](s3.md) | The S3 server: create it, the web console, clients (boto3, JavaScript, AWS CLI, handlers), troubleshooting |
| [s3-api-reference.md](s3-api-reference.md) | Every supported S3 operation, authentication, settings, error codes, data layout |
| [secretsmanager.md](secretsmanager.md) | The Secrets Manager server: create it, API coverage, encryption at rest, clients, troubleshooting |

## Why pskit has its own AWS-compatible servers

The AWS-compatible servers let a program written for AWS run on premises unchanged. The only difference is the
endpoint (and the keys):

```python
import boto3

# On AWS
s3 = boto3.client("s3")

# On premises, against pskit's S3 compatible server: the same code from here on
s3 = boto3.client("s3", endpoint_url="http://10.0.0.5:9000", region_name="us-east-1",
                  aws_access_key_id="pskit", aws_secret_access_key="<the service password>")
```

Compared with an emulator such as LocalStack (also in the on-prem catalog, see
[../services/localstack.md](../services/localstack.md)), these servers:

- **check every request's signature** (AWS Signature Version 4, and Version 2 for S3), so a wrong secret key, an
  unknown access key or a request more than 15 minutes old is refused, the way AWS refuses it;
- keep their data on disk in a volume, with a backup button;
- have their own web console at `/ui/`;
- have no dependencies: the Python server uses only the standard library, the Node.js server uses no npm packages.

They are made for production use on your own servers, not only for tests. Put them behind TLS (a reverse proxy) when
clients reach them over a network you do not trust: SigV4 protects the keys and the request from changes, not the data
in the response.

## The four AWS-compatible service names

The AWS-compatible servers appear in the on-prem service catalog (`pskit resources onprem catalog`) under four names:

| pskit service | Studio card | Implementation | Default port | Use as (resource type) |
|---|---|---|---|---|
| `s3` | Object storage > **Amazon S3 compatible (Python)** | `aws/s3/python/server.py` | 9000 | Bucket (`storage`) |
| `s3-node` | Object storage > **Amazon S3 compatible (Node.js)** | `aws/s3/nodejs/server.js` | 9000 | Bucket (`storage`) |
| `secretsmanager` | Secret managers > **AWS Secrets Manager compatible (Python)** | `aws/secretsmanager/python/server.py` | 4584 | Secret manager (`custom`) |
| `secretsmanager-node` | Secret managers > **AWS Secrets Manager compatible (Node.js)** | `aws/secretsmanager/nodejs/server.js` | 4584 | Secret manager (`custom`) |

## Python or Node.js: how to choose an implementation

The Python and Node.js implementations of each AWS-compatible server are line-for-line ports of each other. They have
the same operations, the same environment variables, the same web console page (`ui/index.html`), the same error
codes and the same data format on disk, so you can stop one and start the other on the same data volume.

| | Python (`s3`, `secretsmanager`) | Node.js (`s3-node`, `secretsmanager-node`) |
|---|---|---|
| Needs | Python 3.9+, standard library only | Node.js 18+, no npm packages |
| Image pskit uses | `python:3.12-alpine` | `node:22-alpine` |
| Crypto (Secrets Manager) | AES, GCM, ChaCha20 and Poly1305 written out in `server.py` | Node.js `crypto` |

How to pick:

- Pick the language your team already runs and can read when something goes wrong. Behaviour is the same.
- For the Secrets Manager server with encryption at rest, the Node.js version uses the native `crypto` module, while
  the Python version does the cipher work in pure Python. Both read what the other wrote.
- When you run the server without Docker, pick the runtime that is already installed on the server.

## How pskit runs the AWS-compatible servers

pskit runs the AWS-compatible servers without building or pushing an image (code in `core/onprem_s3.py` and
`core/onprem_secretsmanager.py`):

1. The wheel ships the repository folder `aws/` as `py_serverless_kit/aws` (`pyproject.toml`,
   `[tool.hatch.build.targets.wheel.force-include]`). A source checkout reads `aws/` in place.
2. `docker create` makes a container from the stock `python:3.12-alpine` or `node:22-alpine` image, named
   `pskit-<project>-<key>`, with the label `pskit.service=<service>`, `--restart unless-stopped` and the data volume
   mounted at `/data`.
3. `docker cp` copies the server file and `index.html` into `/app` in the container. Over SSH the files go to the
   server with `scp` first.
4. `docker start` runs `python /app/server.py` or `node /app/server.js`. The health check is
   `python /app/server.py --check` / `node /app/server.js --check`.
5. pskit writes the credentials to the project's env file (default `.env.onprem`) and adds the resource to
   `pskit.yml` (with `--save` on the CLI, or *Add to pskit.yml* / the automatic add in studio).

The container gets these settings from pskit; you do not set them yourself:

| S3 server | Secrets Manager server | Value |
|---|---|---|
| `S3_PORT` | `SM_PORT` | `9000` / `4584` inside the container (the published port can differ) |
| `S3_BIND` | `SM_BIND` | `0.0.0.0` inside the container (the published port's interface decides who reaches it) |
| `S3_DATA_DIR` | `SM_DATA_DIR` | `/data` |
| `S3_REGION` | `SM_REGION` | `us-east-1` |
| `S3_ACCESS_KEY_ID` | `SM_ACCESS_KEY_ID` | the service's *User* (default `pskit`) |
| `S3_SECRET_ACCESS_KEY` | `SM_SECRET_ACCESS_KEY` | the service's *Password* (generated when empty) |
| | `SM_MASTER_KEY` | a generated 32-byte key, kept in the env file as `PSKIT_<KEY>_MASTER_KEY` |

The data lives in the Docker volume `pskit-<project>-<key>-data`, or in `<data_dir>/pskit-<project>-<key>` when the
saved server has a data directory.

## Credentials of the AWS-compatible servers

The AWS-compatible servers use the service's *User* as the **access key ID** and its *Password* as the **secret access
key**. The same pair signs in to the web console. Rules for the values (checked by pskit before it creates anything):

- User: 3-64 characters, a letter first, then letters, digits, `_`, `.` or `-`. Default `pskit`.
- Password: 8-128 characters of letters, digits and `!#%*+,.:=?@^_~-`. Empty means a strong random one.

The values go to the env file, never into `pskit.yml`:

```bash
# .env.onprem, for an S3 service with key "files"
PSKIT_FILES_ACCESS_KEY=pskit
PSKIT_FILES_SECRET_KEY=...
PSKIT_FILES_URL=http://127.0.0.1:9000
```

The on-prem host loads the env file (shipped to the host as `host.env`), so handlers see these variables in
`os.environ`. `pskit resources onprem usage <key> --reveal` prints them.

## Switch between the Python and Node.js implementation

The Python and Node.js implementations of an AWS-compatible server read the same data, so you can switch without
moving data. With pskit:

1. Copy the service's lines from `.env.onprem` somewhere safe (for Secrets Manager the line
   `PSKIT_<KEY>_MASTER_KEY=...` is essential; see the warning below).
2. Remove the service and **keep the data**: `pskit resources onprem remove <key>` (no `--delete-data`), or *Remove*
   > *Remove, keep data* in studio.
3. Put the `PSKIT_<KEY>_MASTER_KEY=...` line back into `.env.onprem` (Secrets Manager only).
4. Create it again with the same key and the other service name, for example
   `pskit resources onprem create secrets --service secretsmanager-node --save`.

The volume name depends only on the project and the key, so the new container mounts the same data.

**Warning (Secrets Manager).** Removing a service deletes its variables from the env file, including
`PSKIT_<KEY>_MASTER_KEY`, even when you keep the data. A new service then generates a new master key and the server
refuses to start on the old data. pskit reuses a master key that is already in the env file, so restore that line
before you create the service again. Keep a copy of the master key apart from the data at all times.

## Run the AWS-compatible servers without pskit

The AWS-compatible servers run on their own too. Each folder has a `docker-compose.yml` with a `python` and a `nodejs`
service, and a Dockerfile per implementation. The images run as an unprivileged user (uid 10001), keep data in
`/data` and have a health check.

```bash
cd aws/s3
S3_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d s3-python       # or s3-nodejs

cd aws/secretsmanager
SM_SECRET_ACCESS_KEY='a-long-random-secret' docker compose up -d secretsmanager-python   # or secretsmanager-nodejs
```

Details: [s3.md](s3.md#run-the-s3-server-standalone-with-docker-compose) and
[secretsmanager.md](secretsmanager.md#run-the-secrets-manager-server-standalone-with-docker-compose).

## See also

- [s3.md](s3.md), [s3-api-reference.md](s3-api-reference.md), [secretsmanager.md](secretsmanager.md)
- [../services/s3.md](../services/s3.md) and [../services/secretsmanager.md](../services/secretsmanager.md): the
  catalog entries, step by step
- [../services/README.md](../services/README.md): every on-prem service
- [../resources.md](../resources.md): use an on-prem service as a resource
- [../servers.md](../servers.md): saved SSH servers
- [../../resource-guides/onprem/storage.md](../../resource-guides/onprem/storage.md) and
  [../../resource-guides/onprem/secrets.md](../../resource-guides/onprem/secrets.md)
- The server READMEs in the repository: `aws/README.md`, `aws/s3/README.md`, `aws/secretsmanager/README.md`
