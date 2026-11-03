## 1. Install Requirements: - **Python ≥ 3.9** for the CLI.

- **Terraform ≥ 1.5 (<https://developer.hashicorp.com/terraform/install>) or **OpenTofu**. pskit finds `terraform` or `tofu` on `PATH`; to use a specific binary, set `PSKIT_TERRAFORM_BIN` or `provider.terraform.binary`. - Credentials for the cloud you deploy to (see step 6). You don't need Terraform or credentials for local development, `pskit validate` or `pskit package`. `pskit doctor -p <provider>` checks all of this (and the cloud's CLI, required provider options, and SSH / Docker for on-premises) and prints install steps and links for your OS.
## 3. Write a handler

A handler is any function that takes `(event, ctx)` or just `(event)`: Wire them up in `pskit.yml`: See the handler API and the configuration reference.
## 6. Configure cloud credentials pskit runs

Terraform, so credentials come from each Terraform provider's standard sources. Set them up for the cloud you deploy to: | Provider | Quickest setup | |---|---| | `aws` | `aws configure` or `aws sso login`, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_PROFILE`. Optional `options.profile` / `options.assume_role_arn` | | `gcp` | `gcloud auth application-default login`, or `GOOGLE_APPLICATION_CREDENTIALS=key.json`. `options.project` is required | | `azure` | `az login` and `ARM_SUBSCRIPTION_ID` (or `options.subscription_id`). Service principals: `ARM_CLIENT_ID` / `ARM_CLIENT_SECRET` / `ARM_TENANT_ID` | | `alibaba` | `ALICLOUD_ACCESS_KEY` / `ALICLOUD_SECRET_KEY`, or an `aliyun` CLI profile via `options.profile` | | `oracle` | `~/.oci/config` (`oci setup config`). Optional `options.config_file_profile`. Docker is needed if you use `options.image_repository` | | `ibm` | `IC_API_KEY` | | `digitalocean` | `doctl auth init` (doctl must be on `PATH`). `options.namespace` is required | | `tencent` | `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`, or `options.profile` | | `huawei` | `HW_ACCESS_KEY` / `HW_SECRET_KEY` (+ `HW_REGION_NAME`), or `options.profile` | | `cloudflare` | `CLOUDFLARE_API_TOKEN`. `options.account_id` is required | | `onprem` | local: nothing to configure (the Python that runs `pskit` starts the host). Remote: OpenSSH and `options.deploy.method: ssh` (or `scp`) with an optional `.pem`, or Docker with `method: docker`, `host`, and a `.pem`. `pskit deploy` asks for the `.pem` on a terminal. The image is built locally, Docker is installed on the server when it is missing, and deploy waits until `/__pskit/health` answers. Servers without Python: `python: bundle` or Docker | Provider-specific required options are listed in providers.md.
## 7. Deploy After deploying, pskit prints endpoints and resource ids, writes

`.pskit/<provider>-<stage>/deployment.json`, and regenerates the dashboard. > Terraform state is stored locally in `.pskit/<provider>-<stage>/` by default. For team use, configure a remote backend (`provider.state`); see configuration.md.

```bash
pip install py-serverless-kit          # CLI: `pskit` (alias: `py-serverless-kit`)
pip install "py-serverless-kit[aws]"   # optional: boto3, needed for invoke() on AWS
```
