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
