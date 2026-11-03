# Google Cloud Functions provider (`gcp`)

Search terms: gcp, google cloud, google cloud functions, cloud functions gen2, cloud run, gcloud, application default
credentials, GOOGLE_CLOUD_PROJECT, service account, project id, deploy to gcp, us-central1, cloud logging

The `gcp` provider deploys pskit functions as **Cloud Functions (2nd gen)**, which run on Cloud Run. pskit writes
Terraform JSON for the `hashicorp/google` plug-in (`>= 5.20`) and runs Terraform.

| Fact | Value |
|---|---|
| Tier | **stable** |
| Default region | `us-central1` |
| Python runtimes | `python3.9` to `python3.13` (GCP ids `python39` ... `python313`; default `python3.12`) |
| Node.js runtimes | `nodejs18`, `nodejs20`, `nodejs22` |
| Max timeout | 3600 s for HTTP functions, 540 s for event-triggered functions |
| Triggers | `http`, `schedule`, `queue`, `storage`, `topic` |
| Workflows | native: Google Cloud Workflows |
| Dependencies | built remotely by Cloud Build from `requirements.txt` (`functions-framework>=3.5` is added); Node.js from `package.json` (`@google-cloud/functions-framework` is added) |

This page covers credentials, the `provider` block, deploy / info / remove and logs. Triggers, resources and
workflows are in [triggers-and-resources.md](triggers-and-resources.md).

## Set up Google Cloud credentials for pskit

The GCP provider signs in with Application Default Credentials (ADC) or a service account key, like the `google`
Terraform plug-in.

1. Install Terraform and the gcloud CLI. `pskit doctor -p gcp` prints the commands for your OS
   (`winget install Google.CloudSDK`, `brew install --cask google-cloud-sdk`, or the install script).
2. Sign in, either way:

   | Way | Commands |
   |---|---|
   | Your user account (ADC) | `gcloud auth application-default login` |
   | Service account key | `GOOGLE_APPLICATION_CREDENTIALS=/path/key.json` (or `GOOGLE_CREDENTIALS` with the JSON) |

3. Set the project. pskit needs `provider.options.project`; `pskit init -p gcp` writes
   `project: ${env:GOOGLE_CLOUD_PROJECT}`:

```bash
gcloud config set project <project id>
export GOOGLE_CLOUD_PROJECT=<project id>       # PowerShell: $env:GOOGLE_CLOUD_PROJECT = "<project id>"
```

4. Enable the Google APIs the deployment uses. pskit does not enable APIs for you. A typical project needs Cloud
   Functions, Cloud Run, Cloud Build, Artifact Registry, Cloud Storage and IAM, plus Eventarc and Pub/Sub for event
   triggers, Cloud Scheduler for schedules and Workflows for workflows. Enable them in the console (**APIs &
   Services → Enable APIs and services**) or with `gcloud services enable`.
5. Run the check:

```bash
pskit doctor -p gcp
```

6. Optional, on your machine only: `pip install google-cloud-logging` for `pskit logs`,
   `pip install google-cloud-pubsub google-cloud-storage` for `pskit trigger` / `pskit resources send`, and
   `pip install "py-serverless-kit[gcp]"` (google-cloud-workflows) for workflow executions.

## Set up Google Cloud credentials in studio

The studio **Setup & credentials** page checks gcloud, ADC and the project.

1. Run `pskit studio --open` in the project folder.
2. Sidebar **Setup & credentials** → **Provider**: pick **Google Cloud Functions**.
3. On the **Google Cloud credentials** check, click **Sign in (gcloud ADC)**. It runs
   `gcloud auth application-default login`, opens a browser, and shows the output in **Running: ...**.
4. In **Environment variables**, set `GOOGLE_CLOUD_PROJECT` (or `GOOGLE_APPLICATION_CREDENTIALS` for a key file) and
   click **Set for this session**.
5. The **provider.options.project** check turns OK when the project resolves. Click **Check again** until the badge says
   **ready to deploy to Google Cloud Functions**.

## Write the GCP provider block in pskit.yml

The GCP `provider` block selects GCP; `options.project` is required.

```yaml
provider:
  name: gcp
  region: europe-west1             # default us-central1
  stage: dev
  runtime: python3.12
  memory: 512                      # Cloud Functions available_memory "512M"
  timeout: 60                      # max 3600 (HTTP) / 540 (event-triggered)
  environment:
    LOG_LEVEL: INFO
  tags:
    team: payments                 # become GCP labels (lowercased, invalid characters -> "_")
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT}                               # required
    service_account: runtime@my-project.iam.gserviceaccount.com        # optional runtime identity
```

| Option | Default | What it does |
|---|---|---|
| `project` | none (validation error) | GCP project id; also written into the Terraform `provider "google"` block |
| `service_account` | the project's default compute service account | email of an existing service account the functions run as (`service_config.service_account_email`) |

`concurrency` becomes `max_instance_count`. `architecture`, `log_retention_days` and `iam` are not used on GCP;
`iam.statements` warn: grant roles to `options.service_account` instead. `functions.<fn>.options` is merged as-is into
that function's `google_cloudfunctions2_function` resource.

In studio, **Overview & provider → Google Cloud Functions options** shows **Project** and **Service account**.

## What pskit creates on GCP

The GCP provider creates these Terraform resources:

| Resource | Purpose |
|---|---|
| `google_storage_bucket.source` + `google_storage_bucket_object.source` | the source zip (`source-<hash>.zip`), bucket `<service>-<stage>-src-<hash>` |
| `google_cloudfunctions2_function` | one or more per pskit function (see the split rule below) |
| `google_service_account.invoker` | `<prefix>-inv`: Cloud Scheduler, Eventarc and Workflows call the functions as this account |
| `google_cloud_run_service_iam_member` | `roles/run.invoker` for the invoker on every function; `allUsers` when an HTTP event has `auth: none` |
| `google_project_iam_member` | `roles/eventarc.eventReceiver` for the invoker (event triggers); `roles/pubsub.publisher` for the Cloud Storage service agent (storage triggers) |
| `google_pubsub_topic`, `google_storage_bucket` | queue/topic events and storage events, plus standalone resources |
| `google_cloud_scheduler_job` | schedule events |
| `google_workflows_workflow` | native workflows |

Every function gets `PSKIT_GCP_PROJECT` and the label `pskit-function: <name>`.

## GCP splits a function with several triggers

A Cloud Function (2nd gen) has at most one event trigger and an event-triggered function can't serve HTTP, so pskit
deploys one pskit function as one or more Cloud Functions that share the bundle and handler. `PSKIT_FUNCTION` is the
pskit name in all of them.

- `<name>`: the HTTP deployment (entry point `pskit_http`). It exists when the function has `http` events, has no
  event trigger, is a workflow task (Cloud Workflows needs a URL), or has schedules but no Pub/Sub trigger.
- `<name>-queue0`, `<name>-topic0`, `<name>-storage0`, ...: one per event trigger (entry point `pskit_event`). A storage
  event with `events: [created, deleted]` becomes two.
- A function with exactly one trigger and no HTTP deployment is simply named `<name>`.

`pskit package` and `pskit deploy` print a warning that names the Cloud Functions of a split function. The bundle's
root `main.py` is generated, so don't put your own `main.py` at the source root.

## Deploy to GCP from the terminal

Deploying to GCP runs `terraform init` and `terraform apply` in `.pskit/gcp-<stage>/`.

```bash
pskit init my-api --provider gcp          # writes options.project: ${env:GOOGLE_CLOUD_PROJECT}
cd my-api
export GOOGLE_CLOUD_PROJECT=<project id>
pskit validate
pskit plan -s dev                         # optional
pskit deploy -s dev                       # or --confirm
pskit info -s dev
```

Cloud Build installs your requirements during the deploy, so the first deploy of each function takes a few minutes.

## Deploy to GCP from studio

Deploying to GCP from studio uses the credentials of the machine running studio.

1. Sidebar **Overview & provider** → **Provider** → click the **Google Cloud Functions** card, then confirm the switch.
2. Under **Defaults for every function**, pick the **Region**. In **Google Cloud Functions options** fill **Project**
   (default `${env:GOOGLE_CLOUD_PROJECT}`) and optionally **Service account**.
3. Click **Save** in the top bar.
4. Check the top bar: **validate & deploy as** **Google Cloud Functions**, and the **stage**.
5. Sidebar **Deploy** → **Validate** → **Plan** → **Deploy**. A `prod*` stage asks you to type `gcp/<stage>`.
6. Click **Info** for the function URLs.

## Find the GCP URLs and console links

After a GCP deploy, `pskit info` prints per function the Cloud Function name (`id`), its URL for HTTP functions, the
console link `https://console.cloud.google.com/functions/details/<region>/<name>?project=<project>`, and `extra` with
the other Cloud Functions of a split function.

- **HTTP endpoint:** each HTTP function has its own Cloud Run URL. Your paths are appended to it, for example
  `https://hello-gcp-dev-hello-abc123-ew.a.run.app/hello`. There is no shared `endpoint` for the service.
- **auth: iam** functions need an identity token:
  `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" <url>/hello`.
- **Workflows:** the workflow id and its console link.

## Read GCP logs with pskit logs and studio

GCP function logs are in Cloud Logging (resource types `cloud_run_revision` and `cloud_function`). `pskit logs` reads
them with `google-cloud-logging` and your ADC, for the project in `pskit.yml` (or `GOOGLE_CLOUD_PROJECT`).

```bash
pip install google-cloud-logging
pskit logs -s dev                          # last 15 minutes
pskit logs -f --function worker
pskit logs --level error -q "order 42"
```

The logs of every Cloud Function of a split function are shown under the pskit function name. GCP logs are read only:
pskit can't delete entries; set a retention on the log bucket instead. In studio, open **Logs** in the sidebar.

## Remove a GCP deployment

Removing a GCP stage runs `terraform destroy` in `.pskit/gcp-<stage>/`.

```bash
pskit remove -s dev --yes
pskit remove -s dev --keep-resources       # keep Cloud Storage buckets and Pub/Sub topics with their data
```

The source bucket is always destroyed (`force_destroy`). In studio: **Deploy** → set the remove switch → **Remove** →
type `gcp/<stage>`.

## GCP limits and gotchas

The GCP provider rejects or changes these settings:

- `options.project` missing is a validation error.
- HTTP `auth: jwt` and `auth: key` are errors; use `none` (public, `allUsers` invoker) or `iam`.
- Event-triggered functions are limited to 540 s.
- `queue.dead_letter` and `queue.fifo` are not applied (warnings); `batch_size` and `batch_window` are not used.
- `topic.filter` is not applied by Pub/Sub triggers (warning at package time): filter in the handler.
- Storage `prefix` / `suffix` are not Eventarc filters: the function receives every object event of the bucket and the
  pskit runtime drops the ones that don't match.
- pskit grants no roles for your resources: give the runtime service account the roles it needs in **IAM & Admin**.
- Bucket names are global: pick a unique `storage` bucket name.

## Complete minimal GCP example project

The minimal GCP project below has an HTTP function, a Cloud Scheduler job and a Pub/Sub queue worker.

```yaml
service: hello-gcp

provider:
  name: gcp
  region: europe-west1
  stage: dev
  timeout: 15
  options:
    project: ${env:GOOGLE_CLOUD_PROJECT}

functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello

  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: {cron: "0 2 * * *", timezone: Europe/Brussels, input: {report: daily}}

  worker:
    handler: app.handlers.worker
    events:
      - queue: hello-gcp-jobs
```

Use the same `app/handlers.py` as the [AWS example](../aws/README.md#handler-code-and-commands-for-the-minimal-aws-example).

```bash
export GOOGLE_CLOUD_PROJECT=<project id>
pskit invoke -f hello --path "/hello?name=Ada"
pskit deploy -s dev
pskit trigger -f worker -e 0 -d '{"order_id": 1}'     # publishes to Pub/Sub topic hello-gcp-jobs
pskit logs -f --function worker
pskit remove -s dev --yes
```

This config creates 13 Terraform resources: three Cloud Functions, the source bucket and object, the invoker service
account and its bindings, the `hello-gcp-jobs` topic and the scheduler job.

## See also

- [triggers-and-resources.md](triggers-and-resources.md): triggers, resources, Cloud Workflows
- [GCP resource guides](../../resource-guides/gcp/README.md): console walkthroughs for Pub/Sub, Cloud Storage, Cloud
  SQL, Memorystore
- [providers.md](../../providers.md#gcp-google-cloud-functions-2nd-gen), [events.md](../../events.md#gcp-multi-trigger-functions-are-split-automatically)
- [Deploy, remove and info](../../deployment/deploy-remove-info.md), [Logs](../../deployment/logs.md)
- [All providers](../README.md), [AWS](../aws/README.md), [Azure](../azure/README.md)
