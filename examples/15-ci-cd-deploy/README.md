# 15 · CI/CD: deploy per stage from GitHub Actions

`deploy.github-workflow.yml` is a complete pipeline:

| Trigger | Deploys |
| --- | --- |
| push to `main` | `dev` |
| tag `v*` | `staging`, then `prod` (after a manual approval on the `prod` environment) |
| manual run | any stage you pick |

Each deploy job does the following:

1. authenticates with **OIDC**, so there are no long-lived cloud keys in GitHub;
2. `pskit validate --stage <stage>`;
3. `pskit deploy --stage <stage>`: Terraform plan + apply against **remote state**;
4. smoke-tests `GET /health` using the endpoint from `pskit info --json`;
5. uploads the dashboard (`.pskit/dashboard/index.html`) and the deployment record as build artifacts.

## One-time setup (AWS)

1. **State bucket + lock table** (once per account):
   ```bash
   aws s3api create-bucket --bucket acme-terraform-state
   aws s3api put-bucket-versioning --bucket acme-terraform-state --versioning-configuration Status=Enabled
   aws dynamodb create-table --table-name terraform-locks --billing-mode PAY_PER_REQUEST \
     --attribute-definitions AttributeName=LockID,AttributeType=S --key-schema AttributeName=LockID,KeyType=HASH
   ```
2. **OIDC role:** add the GitHub OIDC provider (`token.actions.githubusercontent.com`) to IAM
   and create a role whose trust policy allows `repo:<org>/<repo>:environment:<stage>`.
   Grant it the permissions Terraform needs (Lambda, API Gateway, IAM roles for the
   service, CloudWatch Logs, plus SQS/SNS/S3/Step Functions if you use them).
3. **GitHub:** create environments `dev`, `staging`, `prod` (add reviewers to `prod`), and set
   the variables `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET` and `TF_LOCK_TABLE`.

## GCP / Azure

The workflow contains commented steps for both:

- **GCP:** `google-github-actions/auth@v2` with Workload Identity Federation; state in a GCS
  bucket (`providers.gcp.state` in `pskit.yml`). Deploy with `pskit deploy --provider gcp`.
- **Azure:** `azure/login@v2` with a federated credential; Terraform needs
  `ARM_USE_OIDC=true`, `ARM_CLIENT_ID`, `ARM_TENANT_ID` and `ARM_SUBSCRIPTION_ID`. State goes in a
  storage account (`providers.azure.state`).

## Why remote state matters

Terraform state records which cloud resources belong to this service. With the default
local state (`.pskit/<provider>-<stage>/terraform.tfstate`), every CI run would start empty
and try to create everything again. The `state:` block points every run, and every
developer, at the same file, and the lock table prevents two applies at once.

## Try it locally

```bash
pskit invoke -f health
pskit validate --stage prod
pskit package --stage prod --skip-deps     # inspect .pskit/aws-prod/main.tf.json (backend "s3" included)
```

Expected output of `pskit invoke -f health`:

```json
{"status": 200, "body": {"status": "ok", "stage": "dev", "version": "local"}}
```
