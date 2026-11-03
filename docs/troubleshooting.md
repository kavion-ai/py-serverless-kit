# Troubleshooting & FAQ

Add `-v` to any command to see the full traceback. Start with `pskit validate`, which catches most provider limits before Terraform runs.

## Installation and tooling

Run `pskit doctor` (or `pskit doctor -p <provider>`) first: it reports missing tools, credentials and provider
options with the install steps for your OS.

**`Neither terraform nor tofu was found on PATH`**
: Install Terraform ≥ 1.5 or OpenTofu, or point `PSKIT_TERRAFORM_BIN` (or `provider.terraform.binary`) at the binary.

**`pip install failed while vendoring dependencies`**
: For vendoring providers (aws, alibaba, ibm, digitalocean, tencent, huawei), pskit downloads **Linux** wheels (`manylinux2014_<arch>`, `--only-binary=:all:`) for the target Python version. A package with no such wheel fails. Fixes:
  - pin a version that publishes manylinux wheels;
  - add flags with `package.pip_args`;
  - for pure-Python packages, check that they ship a wheel at all.

  `pskit package --skip-deps` lets you test packaging without dependencies.

**Paths too long on Windows** (`FileNotFoundError` / `[WinError 206]` while building, or while unpacking a bundled CPython for an on-premises deploy)
: Some providers copy the bundle into nested folders (DigitalOcean especially). Enable long paths, either with `git config --system core.longpaths true` for git, or system-wide with:

  ```powershell
  New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
  ```

  Or keep the project in a short path such as `C:\src\app`.

## Configuration

**`unresolved variables: env:FOO`**
: Set the variable, or give a default: `${env:FOO, fallback}`.

**`each event must be a single-key mapping`**
: Write `- http: {path: /x}` and `- queue: jobs` as separate list items, not two keys in one item.

**`route GET /x is used by both 'a' and 'b'`**
: Each `METHOD /path` may belong to one function only (`/x` and `/x/` count as the same path).

**`<provider> does not support python3.12`**
: You pinned `runtime:`. Remove it so pskit picks a supported version, or choose one the provider supports (`pskit providers --json`).

**Values from a parent file win over my child file**
: Child values beat a parent's `providers.<cloud>` block. Check the [precedence order](configuration.md#precedence-later-wins). Lists replace rather than merge.

## Deploy and state

**State conflicts / "resource already exists" after deploying from another machine**
: The default state lives in `.pskit/` on one machine. Configure `provider.state` with a remote backend (S3 + DynamoDB lock, GCS, `azurerm`, …), then `terraform init -migrate-state` via `pskit tf -- init -migrate-state`.

**Changed nothing but Terraform wants to update the function**
: The artifact is deterministic, so a real diff means a source file, dependency or `pskit_manifest.json` changed. Inspect `.pskit/<provider>-<stage>/build/`.

**Provider plugin downloads are slow in CI**
: Set `TF_PLUGIN_CACHE_DIR` and cache that directory.

## HTTP

**CORS errors in the browser**
: Add `cors: true` (or a `cors:` mapping) to the route. With `allow_credentials: true` the runtime echoes the request's `Origin` instead of `*`, so list explicit `origins` to restrict who may call. Preflights are answered by the runtime (and by API Gateway on AWS).

**405 Method Not Allowed**
: The path matched a route but not the method. The `allow` header lists the valid methods. Use `method: ANY` to accept everything.

**404 locally but works in the cloud (or the other way round)**
: `pskit dev` matches routes exactly. Check the printed route list. Path templates use `{id}` and `{path+}` (last segment only).

**500 with only a request id**
: Look in the provider's logs for that `request_id`. Locally, or temporarily, set `PSKIT_DEBUG=1` to include the exception text.

**Cold starts**
: Keep bundles small (exclude data files, avoid heavy imports at module level), increase memory (more CPU on most clouds), or use provider options such as provisioned concurrency through `functions.<fn>.options`.

## Provider gotchas

| Provider | Gotcha |
|---|---|
| aws | `auth: key` isn't supported on HTTP APIs; API Gateway caps integrations at 30 s |
| gcp | `options.project` is required; multi-trigger functions become several Cloud Functions; event functions max 540 s; don't add your own root `main.py` |
| azure | `azurerm` 4.x needs `ARM_SUBSCRIPTION_ID` / `options.subscription_id`; environment is app-wide; blob triggers fire on create/update only; Function App and storage names get a hash suffix for global uniqueness |
| tencent | COS bucket names must end with your APPID: `uploads-1250000000`; no `PATCH`; memory 64, 128 or multiples of 128 |
| huawei | HTTP events need `provider.options.apig_instance_id` (a dedicated API Gateway); use an IAM *agency* in `iam.role` |
| oracle | needs a container image: `options.image`, or `options.image_repository` with Docker logged in to OCIR; add IAM policies for API Gateway / Events to call functions; bucket must emit object events |
| digitalocean | `doctl` must be installed and authenticated (`doctl auth init`); `options.namespace` required; set `options.api_host` to get URLs |
| ibm | HTTP only, python3.11 only, 120 s / 4 GB max; large bundles → `options.code_reference` |
| cloudflare | Pyodide: only stdlib and Pyodide packages; `options.account_id` and `CLOUDFLARE_API_TOKEN` required; non-`.py` files aren't uploaded |
| onprem | one process per service, so give each service its own `options.port`. `pskit remove` stops it and leaves `data_dir`. `auth` must be `none`. A cloud `terraform.extra` resource is omitted. Set `state.backend` empty when the file points at S3, GCS or Azure Storage. Remote SSH needs `ssh`/`scp` on the laptop; a server without Python needs `deploy.python: bundle` or `method: docker`. Remote Docker needs `deploy.pem` (asked at `pskit deploy` when unset) and builds the image locally. If the server has no `docker` command, apply installs it with apt, dnf, yum, or apk (`sudo: true`) and then loads the image. The `.pem` must work with `BatchMode` (no passphrase prompt) and must not be group-readable or OpenSSH will reject it. systemd writes `/etc/systemd/system` (`sudo: true`). Bind `options.host: 0.0.0.0` on a remote host so other machines can call it |
| alibaba / tencent / huawei | `iam.statements` aren't translated; set `iam.role` |

## FAQ

**Do I add `py-serverless-kit` to my function's `requirements.txt`?**
: No. The runtime is vendored into every bundle automatically, and such lines are stripped.

**Can I keep using cloud SDKs (boto3, google-cloud-*)?**
: Yes, but that code becomes cloud-specific. Isolate it behind your own functions.

**How do I run something pskit doesn't model?**
: Use `functions.<fn>.options`, `provider.options`, and `provider.terraform.extra` with `${tf:...}` references. See [configuration.md](configuration.md#escape-hatches).

**Can I use OpenTofu?**
: Yes: `PSKIT_TERRAFORM_BIN=tofu` or `provider.terraform.binary: tofu`.

## Security notes

- 500 responses never include exception details unless `PSKIT_DEBUG` is set.
- `.env`, Terraform state and `pskit*.yml` are excluded from bundles. `.pskit/` is git-ignored.
- `auth: none` routes are public. Embedded workflow orchestrators get a public `POST /workflows/<name>` route unless you set `options.http: false`.
- `resources:` connection values are function environment variables: they land in Terraform state and, on premises, in `pskit_host.json`. Pass the *name* of a secret variable instead of the secret ([resources.md](resources.md#secrets)).
- On premises, set `admin_token` when the host binds beyond loopback: it guards `/__pskit/*` (queues, invoke, workflows, executions, logs, stats). `pskit dashboard --serve` binds loopback and never sends that token to the browser.
- Created AWS buckets block public access. Prefer a least-privilege `iam.statements` over `"*"` resources.
- Keep secrets out of YAML: use `${env:...}` in CI or a secret manager via `${tf:...}`.
- Report vulnerabilities privately (see `SECURITY.md` in the repository root).
