# Deploy, remove and inspect a stage

Search terms: pskit deploy, pskit remove, pskit info, pskit plan, pskit package, destroy, teardown, delete stage,
keep resources, --keep-resources, kept buckets, pskit resources delete, pskit tf, terraform state, deployment.json

This page covers the commands that change or read one deployment (one provider and stage): `package`, `plan`,
`deploy`, `info`, `remove`, `resources list|delete` and `tf`. Each section shows the terminal command and the studio
button that does the same. For the deployment types and the pipeline, start with [deployment types](README.md).

## Build the bundle without deploying with pskit package

`pskit package` validates the project, builds `.pskit/<provider>-<stage>/artifact.zip` and writes `main.tf.json`.
It makes no cloud calls, so it is safe to run anywhere (CI, a laptop without credentials).

```bash
pskit package -s dev
pskit package -p gcp -s prod --skip-deps     # do not pip-install requirements into the bundle
```

The output names the bundle (`artifact artifact.zip: N files, ... KiB, sha256 ...`), any provider warnings, and the
number of Terraform resources. The bundle is byte-reproducible: unchanged inputs give the same sha256.

In studio: **Deploy** → **Package**.

## Review changes first with pskit plan

`pskit plan` packages the project, runs `terraform init` and `terraform plan`, and prints what would be created,
changed or destroyed. Nothing is applied.

```bash
pskit plan -s prod
pskit plan -s prod --destroy      # what `pskit remove` would destroy
```

In studio: **Deploy** → **Plan**.

## Deploy a stage with pskit deploy

`pskit deploy` packages, runs `terraform init` and `terraform apply`, writes `deployment.json` and regenerates the
dashboard.

1. Check the machine once: `pskit doctor` (studio: **Setup & credentials**).
2. Deploy:

   ```bash
   pskit deploy -s dev
   ```

3. Read the result. The last lines look like this:

   ```text
   Deployed orders (dev) to AWS Lambda eu-west-1
   endpoint: https://abc123.execute-api.eu-west-1.amazonaws.com
   functions:
     hello                    http          GET /hello
         GET    https://abc123.execute-api.eu-west-1.amazonaws.com/hello

   Dashboard: file:///.../.pskit/dashboard/index.html
   ```

| Flag | Effect |
|---|---|
| `--confirm` | run `terraform plan`, then apply exactly that plan (no `-auto-approve`). "No changes." when nothing differs |
| `--skip-deps` | do not pip-install requirements into the bundle |
| `--upgrade` | `terraform init -upgrade`: update the provider plug-ins |
| `--no-dashboard` | do not regenerate `.pskit/dashboard/index.html` |
| `--server NAME` / `--cluster NAME` | on premises: where the functions run ([deployment types](README.md#where-an-on-prem-deploy-goes-and-how-the-stage-remembers-it)) |

On premises, when an SSH or remote Docker deploy has no key set, `pskit deploy` asks for the `.pem` path in the
terminal; Enter keeps the SSH agent.

In studio: **Deploy** → **Deploy**. A stage whose name starts with `prod` asks you to type `provider/stage` first.

## Read what is deployed with pskit info

`pskit info` prints the deployment record of one stage: service, stage, provider, region, status, the endpoint, each
function with its triggers, URLs and id or ARN, and each workflow with its engine and id.

```bash
pskit info -s dev
pskit info -s prod --json          # the full deployment.json record
pskit info -s prod --refresh       # read the Terraform outputs again, then print
```

The first line has the status: `deployed`, `removed`, or `not deployed` (nothing deployed yet: pskit shows the
configured functions). On premises, `deployed on:` names the machine or cluster, for example
`deployed on: cluster prod (master edge1 (10.0.0.5))`.

`--json` prints the record that the dashboard, `pskit logs` and the workflow commands read: `key`, `status`,
`service`, `stage`, `provider`, `region`, `endpoint`, `deployed_at`, `pskit_version`, `artifact` (sha256, size,
files), `functions`, `workflows`, `resources` (connection key names only, never values) and `outputs`.

In studio: **Deploy** → **Info**.

## Remove a stage with pskit remove

`pskit remove` runs `terraform destroy` for one provider and stage. By default it destroys every function, trigger
and managed resource, including buckets, queues and topics and their data. External resources (`external: true`) are
never deleted.

```bash
pskit remove -s dev               # asks: Destroy ALL resources of 'orders' stage 'dev' on AWS Lambda?
pskit remove -s dev --yes         # no question (scripts, CI)
```

After the destroy `deployment.json` gets `status: removed` and the dashboard is regenerated. The `before_remove` and
`after_remove` hooks run around it. On premises the host process, container or systemd unit is stopped, its data
folder stays, and the deployment's routes leave its load balancers.

In studio:

1. Pick the provider and stage in the top bar.
2. Open **Deploy**. Set the toggle under the action cards: *Remove also deletes buckets, queues and topics* or
   *Remove keeps buckets, queues and topics (and their data)*.
3. Click **Remove**, type `provider/stage` in the dialog and confirm.

## Keep buckets, queues and topics when you remove a stage

`pskit remove --keep-resources` destroys only the functions, triggers and gateways. Managed buckets, queues and topics
stay in the cloud with their objects and messages, and pskit stops managing them.

```bash
pskit remove -s dev --keep-resources
```

pskit takes these resources out of the Terraform state before the destroy and saves their state under
`.pskit/<provider>-<stage>/kept/`, so you can delete them later. Each kept address is printed:
`keeping aws_s3_bucket.b_uploads (delete later with pskit resources delete)`.

| Provider | Resource types kept |
|---|---|
| aws | `aws_s3_bucket`, `aws_s3_bucket_public_access_block`, `aws_sqs_queue`, `aws_sns_topic` |
| gcp | `google_storage_bucket`, `google_pubsub_topic` |
| azure | `azurerm_storage_queue`, `azurerm_storage_container`, `azurerm_servicebus_topic`, plus the storage account, Service Bus namespace and resource group that hold them |
| alibaba | `alicloud_oss_bucket`, `alicloud_message_service_topic`, `alicloud_message_service_queue` |
| tencent | `tencentcloud_cos_bucket` |
| huawei | `huaweicloud_obs_bucket`, `huaweicloud_smn_topic` |
| oracle | `oci_objectstorage_bucket` |

Only resources pskit created for `resources:` and triggers are kept (Terraform labels starting `b_`, `q_`, `t_`).
Infrastructure buckets, such as a code-upload bucket, are destroyed as usual. Other providers print that they have
nothing to keep.

## List and delete kept or deployed buckets, queues and topics

`pskit resources list` reads the Terraform state of the stage and the kept folder. `pskit resources delete` deletes
by Terraform address.

```bash
pskit resources list -s dev
pskit resources delete aws_s3_bucket.b_uploads -s dev
pskit resources delete --all-kept -s dev --yes
```

`list` prints `status` (`deployed` or `kept`), `kind`, `name` and `address`. Deleting a *deployed* resource destroys
it now; if it is still in `pskit.yml`, the next deploy creates it again, so remove it from `resources:` or the trigger
first.

In studio:

1. Open **Resources** and expand **In the cloud (provider / stage)**.
2. Click **Load** (it runs `terraform init` and reads the state).
3. Click **Delete** on a row, or tick rows and click **Delete selected (N)**, or **Delete all kept (N)**.

## Run raw Terraform with pskit tf

`pskit tf` runs any Terraform command in `.pskit/<provider>-<stage>/`. Put the Terraform arguments after `--`. The
folder must exist (run `pskit package` first).

```bash
pskit tf -s dev -- state list
pskit tf -s prod -- output -json
pskit tf -s dev -- state show aws_lambda_function.hello
```

Changing state by hand can break later deploys. Prefer `pskit remove` and `pskit resources delete`.

## Fix a failed deploy or remove

| Message | Fix |
|---|---|
| `N configuration error(s); fix them and retry` | run `pskit validate -s STAGE`; studio lists them under the problems button in the top bar |
| `hook before_deploy failed (1): ...` | the hook command failed; run it by hand in the project root |
| `nothing generated yet; run pskit package first` | `pskit tf` needs `main.tf.json` |
| `Another deploy-type job is running. Wait for it or cancel it.` (studio) | only one deploy job at a time: wait, or click **Cancel** |
| `pick one: --cluster NAME (several servers) or --server NAME (one server)` | pass only one of the two |
| Terraform plug-in errors after an upgrade | `pskit deploy --upgrade` |

Missing tools or credentials: [settings and config](settings-and-config.md#check-tools-and-credentials-with-pskit-doctor).
More: [troubleshooting](../troubleshooting.md).

## See also

- [Deployment types](README.md)
- [Stages](stages.md)
- [Logs](logs.md)
- [Monitoring and dashboard](monitoring-and-dashboard.md)
- [Invoke and test functions](../functions/invoke-and-test.md)
- Existing reference: [cli.md](../cli.md)
