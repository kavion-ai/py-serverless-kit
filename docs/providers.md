# Providers

Run `pskit providers` (or `pskit providers --json`) to print this matrix from the installed version.

| Provider | Tier | http | schedule | queue | storage | topic | workflows | Runtimes | Max timeout |
|---|---|---|---|---|---|---|---|---|---|
| [`aws`](#aws-aws-lambda) | stable | ✓ | ✓ | ✓ | ✓ | ✓ | native | 3.9–3.13; Node.js 18, 20, 22 | 900 s |
| [`gcp`](#gcp-google-cloud-functions-2nd-gen) | stable | ✓ | ✓ | ✓ | ✓ | ✓ | native | 3.9–3.13; Node.js 18, 20, 22 | 3600 s (540 s event) |
| [`azure`](#azure-azure-functions) | stable | ✓ | ✓ | ✓ | ✓ | ✓ | embedded (native opt-in) | 3.9–3.12; Node.js 18, 20, 22 | 600 s |
| [`alibaba`](#alibaba-function-compute-30) | beta | ✓ | ✓ | – | ✓ | ✓ | embedded | 3.9, 3.10, 3.12; Node.js 18, 20 | 3600 s |
| [`tencent`](#tencent-serverless-cloud-function-scf) | beta | ✓ | ✓ | – | ✓ | – | embedded | 3.9, 3.10; Node.js 18 | 900 s |
| [`huawei`](#huawei-functiongraph) | beta | ✓ | ✓ | – | ✓ | ✓ | embedded | 3.9, 3.10, 3.12; Node.js 18 | 900 s |
| [`ibm`](#ibm-code-engine-functions) | beta | ✓ | – | – | – | – | embedded | 3.11; Node.js 18, 20 | 120 s |
| [`digitalocean`](#digitalocean-functions) | beta | ✓ | ✓ | – | – | – | embedded | 3.9, 3.11; Node.js 18 | 900 s |
| [`oracle`](#oracle-oci-functions) | experimental | ✓ | – | – | ✓ | – | embedded | 3.9, 3.11; Node.js 18, 20 | 300 s |
| [`cloudflare`](#cloudflare-workers) | experimental | ✓ | ✓ | – | – | – | embedded | 3.11–3.13; JavaScript | 900 s |
| [`onprem`](#onprem-on-premises) | experimental | ✓ | ✓ | ✓ | ✓ | ✓ | embedded | 3.9–3.14 | 3600 s |

**Tiers**

- **stable:** the generated Terraform is validated against the real provider plugin, and the full trigger set is supported.
- **beta:** validated with `terraform validate`; event payload formats follow vendor documentation.
- **experimental:** works with notable constraints (container images, Pyodide, or a process on your own machine), so read the section below first.

**Common to all providers**

- Every provider gets `provider.region` (or its default region), `provider.options` (below), and `functions.<fn>.options`, which is merged into that provider's function resource as an escape hatch.
- Resources are tagged or labelled with `pskit-service`, `pskit-stage` and `managed-by: py-serverless-kit` where the cloud supports tags.
- With no pinned `runtime`, pskit picks python3.12 or the newest version below it that the cloud supports (see [configuration.md](configuration.md#default-runtime)).

Every generated configuration (all 11 providers) passes `terraform validate`. The repository's `scripts/validate_all_providers.py` re-checks this in CI. On-premises uses Terraform's built-in provider, so that check does not download a plugin for it.

---

## aws (AWS Lambda)

- **Terraform:** `hashicorp/aws >= 5.40`
- **Credentials:** standard AWS chain (`aws configure`, SSO, `AWS_PROFILE`, env keys, OIDC in CI)
- **Dependencies:** pip-installed into the zip as manylinux wheels (`x86_64` or `arm64`); Node.js: `npm install --omit=dev` into the zip
- **Node.js:** `nodejs18`, `nodejs20`, `nodejs22` → `nodejs18.x` / `nodejs20.x` / `nodejs22.x`. Generated `pskit_entry.js`, Lambda handler `pskit_entry.handler` (same as Python)

| Trigger | Implementation |
|---|---|
| http | API Gateway **HTTP API** (one per service, `$default` stage), Lambda proxy v2; `auth: iam` → `AWS_IAM`, `auth: jwt` → JWT authorizer; CORS on the API |
| schedule | EventBridge Scheduler (supports `timezone`) |
| queue | SQS (+ optional DLQ / FIFO), event source mapping with `ReportBatchItemFailures` |
| storage | S3 bucket (public access blocked) + bucket notification |
| topic | SNS topic + subscription (filter policy) |
| workflows | Step Functions state machine (`options.type: STANDARD \| EXPRESS` per workflow) |

**Options**

```yaml
provider:
  name: aws
  region: eu-west-1
  options:
    profile: my-profile            # AWS CLI profile
    assume_role_arn: arn:aws:iam::123456789012:role/deployer
    allowed_account_ids: ["123456789012"]
    artifact_bucket: my-deploy-bucket   # optional: upload code here instead of a pskit-created bucket
    artifact_upload: s3            # s3 (default) | direct (inline zip; only for small bundles)
  iam:
    statements:
      - {actions: ["dynamodb:GetItem"], resources: ["arn:aws:dynamodb:*:*:table/orders"]}
functions:
  api:
    handler: app.api.handler
    options:                       # merged into aws_lambda_function
      layers: ["arn:aws:lambda:eu-west-1:123456789012:layer:deps:3"]
      vpc_config: {subnet_ids: [subnet-1], security_group_ids: [sg-1]}
```

**Resources:** `aws_lambda_function`, `aws_iam_role` (+ policies), `aws_cloudwatch_log_group`, `aws_apigatewayv2_*`, `aws_lambda_permission`, `aws_scheduler_schedule`, `aws_sqs_queue`, `aws_lambda_event_source_mapping`, `aws_s3_bucket*`, `aws_sns_topic*`, `aws_sfn_state_machine`, `aws_s3_object` (the code artifact).

**Code upload:** the artifact is uploaded once to S3 (a private `<service>-<stage>-code-*` bucket created by pskit, or `options.artifact_bucket`) and every function reads it from there. This avoids the 50 MB inline limit and the AWS provider error `decomposing request: bufio.Scanner: token too long` that inline uploads hit with larger bundles. The deploying identity needs `s3:CreateBucket`/`PutObject` (or just `PutObject` on `artifact_bucket`).

**Limits:** `auth: key` isn't available on HTTP APIs. Integration timeout is capped at 30 s by API Gateway.

---

## gcp (Google Cloud Functions, 2nd gen)

- **Terraform:** `hashicorp/google >= 5.20`
- **Credentials:** `gcloud auth application-default login` or `GOOGLE_APPLICATION_CREDENTIALS`
- **Dependencies:** built remotely from `requirements.txt` (`functions-framework` is added automatically); Node.js: from `package.json` by Cloud Build (`@google-cloud/functions-framework` is added)
- **Node.js:** `nodejs18`, `nodejs20`, `nodejs22`. Generated `pskit_entry.js` (the package's `main`) registers the same entry points, `pskit_http` and `pskit_event`

```yaml
provider:
  name: gcp
  region: europe-west1
  options:
    project: my-gcp-project               # required
    service_account: runtime@my-gcp-project.iam.gserviceaccount.com   # optional runtime identity
```

| Trigger | Implementation |
|---|---|
| http | function URL; `auth: none` adds an `allUsers` invoker binding, `auth: iam` doesn't |
| schedule | Cloud Scheduler (OIDC POST to the function, or Pub/Sub publish for event-only functions); `timezone` supported |
| queue / topic | Pub/Sub topic + Eventarc trigger (a queue is a topic on GCP) |
| storage | Cloud Storage bucket + Eventarc `finalized` / `deleted`; prefix/suffix applied by the runtime |
| workflows | Cloud Workflows, tasks call function URLs with OIDC |

Functions with several triggers are **split into multiple Cloud Functions** automatically (see [events.md](events.md#gcp-multi-trigger-functions-are-split-automatically)). A dedicated invoker service account is created for Scheduler, Eventarc and Workflows.

**Resources:** `google_storage_bucket` (+ object) for sources, `google_cloudfunctions2_function`, `google_cloud_run_service_iam_member`, `google_service_account`, `google_project_iam_member`, `google_cloud_scheduler_job`, `google_pubsub_topic`, `google_workflows_workflow`.

**Limits:** `auth: jwt`/`key` aren't supported. Event-triggered functions are limited to 540 s. `queue.dead_letter`/`fifo`/`batch_size` and `topic.filter` are not applied (warnings). `iam.statements` are ignored: grant roles to `options.service_account`. The bundle's root `main.py` is generated, so don't put your own `main.py` at the source root.

---

## azure (Azure Functions)

- **Terraform:** `hashicorp/azurerm >= 4.9` (needs a subscription id)
- **Credentials:** `az login` + `ARM_SUBSCRIPTION_ID`, or service principal env vars
- **Dependencies:** remote Oryx build from `requirements.txt` (`azure-functions` is added automatically); Node.js: from `package.json` (`@azure/functions` v4 is added)
- **Node.js:** `nodejs18`, `nodejs20`, `nodejs22` → `application_stack.node_version` `18` / `20` / `22`. Generated `pskit_entry.js` (the package's `main`) uses the v4 programming model: one `app.http()` / `app.timer()` / `app.storageQueue()` / `app.storageBlob()` / `app.serviceBusTopic()` per trigger, the same function names and routes as `function_app.py`, including the `_pskit/invoke/<fn>` routes for invoke-only and Logic Apps task functions. Several `Set-Cookie` headers are all kept (Python keeps only the last)

```yaml
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}   # or the env var itself
    resource_group: existing-rg                   # optional: use an existing resource group
    plan_sku: Y1                                  # default Y1 (Consumption)
    app_insights: true                            # default true
    storage_connection: OTHER_STORAGE             # app setting name, for `existing` queues/buckets in another account
    servicebus_namespace_id: /subscriptions/.../namespaces/my-sb   # for `existing` topics
    servicebus_connection: SB_CONNECTION                          # app setting with its connection string
```

One **Linux Consumption Function App** hosts every function of a service, using the Python v2 programming model: pskit generates `function_app.py` and `host.json`. `routePrefix` is empty, so your paths are served exactly as configured (no `/api`). `{path+}` becomes Azure's `{*path}`.

| Trigger | Implementation |
|---|---|
| http | `@app.route`; `auth: key` → function key |
| schedule | timer trigger (NCRONTAB, UTC) |
| queue | Storage Queue in the app's storage account (poison queue `<name>-poison`) |
| storage | Blob container + blob trigger (created/updated only) |
| topic | Service Bus namespace/topic + one subscription per function |
| workflows | embedded orchestrator function by default; `engine: native` → **Azure Logic App** (Consumption) |

**Resources:** `azurerm_resource_group`, `azurerm_storage_account`, `azurerm_service_plan`, `azurerm_linux_function_app`, `azurerm_application_insights` + `azurerm_log_analytics_workspace`, `azurerm_storage_queue`, `azurerm_storage_container`, `azurerm_servicebus_*`; for native workflows `azurerm_logic_app_workflow`, `azurerm_logic_app_trigger_http_request`, `azurerm_logic_app_action_custom` and the `azurerm_function_app_host_keys` data source.

**Native workflows (Logic Apps, opt-in).** `engine: auto` keeps the embedded engine on Azure; set `engine: native` on a workflow to deploy it as a Logic App with an HTTP request trigger. Start it with `POST` to the trigger's callback URL (`pskit info` shows it as the workflow `url`; it contains a SAS signature, so treat it like a secret). Task states call `POST /_pskit/invoke/<function>` on the Function App with the host's default function key, so every task function gets that route. See [workflows.md](workflows.md#compiler-notes-and-limits) for the limits.

**Limits:** `auth: iam`/`jwt` aren't supported. `environment` is app-wide (warning on conflicting values). Timers ignore `timezone`. Blob `deleted` events aren't available. `fifo`, `dead_letter` and `topic.filter` aren't applied. Invoke-only functions (and task functions of native workflows) get `POST /_pskit/invoke/<name>` (function key).

---

## alibaba (Function Compute 3.0)

- **Terraform:** `aliyun/alicloud >= 1.230.0`
- **Credentials:** `ALICLOUD_ACCESS_KEY` / `ALICLOUD_SECRET_KEY`, or `options.profile`
- **Default region:** `cn-hangzhou`
- **Dependencies:** vendored
- **Node.js:** `nodejs18`, `nodejs20` (generated `index.js`, handler `index.handler`)

```yaml
provider:
  name: alibaba
  region: cn-shanghai
  options:
    profile: default        # optional aliyun CLI profile
  iam:
    role: acs:ram::1234567890:role/fc-runtime   # use instead of iam.statements
```

| Trigger | Implementation |
|---|---|
| http | one anonymous HTTP trigger per function (`fcapp.run` URL) |
| schedule | timer trigger (`@every` or cron; `CRON_TZ=` when `timezone` is set) |
| storage | OSS bucket + OSS trigger (prefix/suffix) via a RAM trigger role |
| topic | MNS topic + trigger (`filter.tag`) |

**Resources:** `alicloud_fcv3_function`, `alicloud_fcv3_trigger`, `alicloud_oss_bucket`, `alicloud_message_service_topic`, `alicloud_ram_role` (+ policy attachment).

**Limits:** no queue events. HTTP `auth` must be `none`. `iam.statements` aren't translated to RAM (warning): set `iam.role`.

---

## tencent (Serverless Cloud Function, SCF)

- **Terraform:** `tencentcloudstack/tencentcloud >= 1.81.0`
- **Credentials:** `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`, or `options.profile`
- **Default region:** `ap-guangzhou`
- **Dependencies:** vendored
- **Node.js:** `nodejs18` → `Nodejs18.15` (generated `index.js`, handler `index.main_handler`)

```yaml
provider:
  name: tencent
  options:
    profile: default
    namespace: default      # SCF namespace shown in console links
functions:
  ingest:
    handler: app.ingest.handler
    events:
      - storage: {bucket: uploads-1250000000}   # COS buckets need the -<APPID> suffix
```

| Trigger | Implementation |
|---|---|
| http | API Gateway service, one API per route, released to `release` |
| schedule | timer trigger (7-field cron; input / enabled via trigger config) |
| storage | COS bucket + COS trigger (prefix/suffix) |

**Resources:** `tencentcloud_scf_function`, `tencentcloud_scf_trigger_config`, `tencentcloud_api_gateway_service` / `_api` / `_service_release`, `tencentcloud_cos_bucket`.

**Limits:** no queue or topic events. HTTP `auth` must be `none`. No `PATCH` (use `ANY`). `{path+}` becomes a prefix route. Memory must be 64, 128 or a multiple of 128 MB. `iam.statements` aren't translated (set `iam.role`). Each new artifact is copied to `artifact-<hash>.zip` so SCF re-uploads it.

---

## huawei (FunctionGraph)

- **Terraform:** `huaweicloud/huaweicloud >= 1.60.0`
- **Credentials:** `HW_ACCESS_KEY` / `HW_SECRET_KEY` (+ `HW_REGION_NAME`), or `options.profile`
- **Default region:** `cn-north-4`
- **Dependencies:** vendored
- **Node.js:** `nodejs18` → `Node.js18.15` (generated `index.js`, handler `index.handler`)

```yaml
provider:
  name: huawei
  options:
    apig_instance_id: 0123456789abcdef0123456789abcdef   # required for http events (dedicated APIG)
    app: default                                         # FunctionGraph app, default "default"
    enterprise_project_id: "0"                           # optional
  iam:
    role: my-functiongraph-agency                        # IAM agency name
```

| Trigger | Implementation |
|---|---|
| http | dedicated API Gateway group/APIs/environment; `auth: none \| iam \| key` (→ `NONE`/`IAM`/`APP`) |
| schedule | timer trigger (`Rate` or cron) |
| storage | OBS bucket + trigger (prefix/suffix) |
| topic | SMN topic + trigger |

**Resources:** `huaweicloud_fgs_function`, `huaweicloud_fgs_trigger`, `huaweicloud_apig_*`, `huaweicloud_obs_bucket`, `huaweicloud_smn_topic`.

**Limits:** no queue events. `{path+}` becomes a prefix route. `iam.statements` are ignored (use an agency in `iam.role`). Environment variables are passed as `user_data`.

---

## ibm (Code Engine functions)

- **Terraform:** `IBM-Cloud/ibm >= 1.70`
- **Credentials:** `IC_API_KEY`
- **Default region:** `us-south`
- **Dependencies:** vendored
- **Node.js:** `nodejs18`, `nodejs20` → `nodejs-18` / `nodejs-20`. The generated `index.js` exports `main`; Code Engine loads the package's main file, so don't point `package.json` `main` elsewhere

```yaml
provider:
  name: ibm
  options:
    resource_group: default          # provider-level resource group (optional)
    project_id: 1234abcd-...         # use an existing Code Engine project (else one is created)
    resource_group_id: abcd...       # for the created project
    visibility: local_public         # managed_domain_mappings; also settable per function
    code_reference: icr.io/ns/bundle:tag   # optional: code bundle image instead of an inline upload
```

Every function gets a public HTTPS endpoint, and pskit's runtime does the routing.

**Resources:** `ibm_code_engine_project`, `ibm_code_engine_function`.

**Limits:** HTTP only: no schedule/queue/storage/topic (the Terraform provider has no function subscriptions). Python: only python3.11. Max 120 s and 4096 MB (memory maps to fixed CPU/memory sizes). `auth` must be `none`. Code is uploaded inline as base64, so keep bundles small or use `code_reference`.

---

## digitalocean (Functions)

- **Terraform:** no cloud provider plugin. pskit renders a `doctl serverless` project and deploys it from a `terraform_data` resource (`local-exec`), redeploying when the artifact changes and running `undeploy` on destroy.
- **Credentials:** `doctl auth init`; `doctl` must be on `PATH`
- **Dependencies:** vendored
- **Node.js:** `nodejs18` → `nodejs:18`. Each function folder is a Node.js package whose main file is the generated `index.js` (exports `main`)

```yaml
provider:
  name: digitalocean
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000   # required: doctl serverless namespaces list
    api_host: https://faas-nyc1-2ef2e6cc.doserverless.co  # optional: enables URLs in outputs
```

| Trigger | Implementation |
|---|---|
| http | `web: raw` public functions |
| schedule | scheduled triggers in `project.yml` |

**Limits:** HTTP and schedule only. Runtimes python3.9 / python3.11 / nodejs18. Memory 128–1024 MB. `auth` must be `none`. Each function gets its own copy of the bundle under `.pskit/digitalocean-<stage>/do_project/`, so on Windows keep project paths short or enable long paths.

---

## oracle (OCI Functions)

- **Terraform:** `oracle/oci >= 6.0`
- **Credentials:** `~/.oci/config`, or provider-block options `config_file_profile`, `auth`, `tenancy_ocid`, `user_ocid`, `fingerprint`, `private_key_path`
- **Default region:** `us-ashburn-1`
- **Dependencies:** installed inside the container image build (`fdk` added for Python, `@fnproject/fdk` for Node.js)
- **Node.js:** `nodejs18`, `nodejs20`: `func.js` + `func.yaml` + a `Dockerfile` on `fnproject/node:<major>` (`-dev` for the `npm install` stage); entrypoint `node func.js`

OCI Functions only run **container images**. pskit writes `func.py` (`func.js` for Node.js), `func.yaml` and a `Dockerfile` into the bundle, then either:

```yaml
provider:
  name: oracle
  options:
    compartment_id: ocid1.compartment.oc1..aaaa       # required
    subnet_ids: [ocid1.subnet.oc1..aaaa]               # required
    image: iad.ocir.io/mytenancy/orders:1.0            # use a pre-built image, OR
    # image_repository: iad.ocir.io/mytenancy/orders   # pskit runs docker build + push (tag = artifact hash)
    gateway_subnet_id: ocid1.subnet.oc1..bbbb          # optional, default first subnet
    gateway_endpoint_type: PUBLIC                      # optional
```

| Trigger | Implementation |
|---|---|
| http | API Gateway + deployment (`{path+}` → `{path*}`) |
| storage | Object Storage bucket (object events enabled) + Events rule |

**Resources:** `oci_functions_application`, `oci_functions_function`, `oci_apigateway_gateway`, `oci_apigateway_deployment`, `oci_objectstorage_bucket`, `oci_events_rule`.

**Limits:** no schedule/queue/topic. `auth` must be `none`. Max 300 s. Events rules can't filter by prefix/suffix (filter in the handler). **You must add IAM policies** that let API Gateway and Events invoke functions, e.g. `ALLOW any-user to use functions-family in compartment <c> where ALL {request.principal.type='ApiGateway'}`.

---

## cloudflare (Workers)

- **Terraform:** `cloudflare/cloudflare >= 5.28, < 6.0`
- **Credentials:** `CLOUDFLARE_API_TOKEN`
- **Dependencies (Python):** **not bundled**. Python Workers run on Pyodide, so only the standard library and Pyodide's built-in packages are available.
- **JavaScript / TypeScript** (`runtime: nodejs18 | nodejs20 | nodejs22`; Workers run JavaScript natively, the version only selects the language): each function becomes one ES module bundled with esbuild, so npm dependencies **are** included. pskit writes `_pskit_cf/<fn>.mjs`, which imports your handler modules statically (a bundle can't load files by name), the manifest and the adapter, and uploads `_pskit_cf/<fn>.bundle.mjs` with `compatibility_flags: [nodejs_compat]`. Environment variables are `plain_text` bindings, copied into `process.env` per request. `require()` of `assert buffer crypto events fs path stream string_decoder url util` works through a generated shim; other Node.js built-ins are not available on Workers. Keep `compatibility_date` at `2025-09-01` or later (`node:fs`).

```yaml
provider:
  name: cloudflare
  options:
    account_id: 0123456789abcdef0123456789abcdef   # required
    workers_subdomain: my-team                     # <name>.my-team.workers.dev URLs in outputs
    workers_dev: true                              # default true
    zone_id: abcdef...                             # needed for custom routes
    compatibility_date: "2025-09-01"
functions:
  api:
    handler: app.api.handler
    options:
      route: api.example.com/*                     # optional zone route (needs zone_id)
```

One Worker script per function. pskit generates a single Python module per Worker that embeds your `.py` files plus the runtime and loads them through an import hook, so your package layout keeps working. Non-Python files aren't uploaded (warning).

| Trigger | Implementation |
|---|---|
| http | `workers.dev` subdomain and/or zone route |
| schedule | Cron Triggers (UTC) |

**Resources:** `cloudflare_workers_script`, `cloudflare_workers_script_subdomain`, `cloudflare_workers_cron_trigger`, `cloudflare_workers_route`.

**Limits:** HTTP and schedule only. `auth` must be `none` (validate tokens in your handler). Third-party packages beyond Pyodide's aren't available.

---

## onprem (On-premises)

- **Terraform:** built-in `terraform_data` (no plugin download). Create/destroy run `onprem_deploy.py` via `local-exec`
- **Credentials:** none for `method: local`. For `method: ssh` (or `scp`), a `.pem` (`options.deploy.pem` or `identity_file`) or the SSH agent. `pskit deploy` asks for the `.pem` on a terminal; Enter keeps the agent. For `method: docker` on a server, a `.pem` is required, plus OpenSSH on the laptop and a Docker CLI to build the image. `docker_host: tcp://`, `unix://`, or `npipe://` still talks to that daemon and does not use SSH
- **Dependencies:** native pip wheels for a local host; manylinux / Windows / macOS wheels matching `deploy.target_os` and `architecture` for a remote host. `tzdata` is vendored so cron timezones work on Windows

```yaml
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1          # bind address on the *target*. 0.0.0.0 is advertised as 127.0.0.1 unless advertise is set
    port: 8080               # 1-65535. Give each service its own port
    advertise: https://fn.internal.example   # optional URL written into outputs
    data_dir: .pskit/onprem-data             # default .pskit/onprem-data/<service>-<stage> (local); <path>/data on SSH
    poll_seconds: 0.5
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"  # header x-pskit-token on /__pskit/* except health
    env_file: .env.onprem      # KEY=VALUE secrets copied next to the host (host.env) and loaded at start;
                               # read by <name>_env driver options and handlers, never written to Terraform state
    execution_retention: 500   # finished workflow executions kept under <data_dir>/executions
    workflow_workers: 8        # workflow runs executing at once; further starts wait for a worker
    log_buffer: 5000           # log entries kept in memory for /__pskit/logs (min 100)
    log_level: INFO            # minimum level captured from `logging`
    capture_output: true       # also record print() / stdout / stderr lines
    services:
      schedule: builtin                        # the only schedule implementation
      queue: builtin                           # or {use: directory, path: /var/pskit/queues}
      storage: {use: directory, path: .onprem/buckets}
      topic: builtin
      workflow: embedded                       # builtin is an alias of embedded
    deploy:
      method: local          # local | ssh | scp | docker   (default local). scp is ssh
```

`pskit deploy` writes the bundle under `.pskit/onprem-<stage>/onprem_app/` and runs `onprem_deploy.py apply`. `pskit remove` stops the process (or container / systemd unit) and does not delete `data_dir`.

Omitted services default to `builtin` and are created at start. `existing: true` on one queue, bucket or topic skips that create and waits until the directory appears. Names are a single path segment (`..`, slashes and NUL are rejected).

| Trigger | Implementation |
|---|---|
| http | the host process. `auth` must be `none` (check tokens in the handler) |
| schedule | in-process rate (any positive number of minutes, hours or days, including values that are not cron) and 5-field cron. A missing IANA timezone warns and is evaluated in UTC |
| queue | one JSON file per message. `batch_size`, `batch_window`, `visibility_timeout` (default `max(30, 6 x timeout)`), `dead_letter`, `max_receive` and `fifo` are honoured. `BatchResult` retries only the failed ids |
| storage | files under `<bucket>/<key>`. `prefix`, `suffix`, `created` and `deleted`. The first start records the current files and does not emit them |
| topic | fan-out. `filter` is an exact match on message attributes, then on JSON body fields |
| workflows | embedded engine inside the host, so a workflow is not cut off by a function timeout |

Publish from outside the process:

| Request | Effect |
|---|---|
| `GET /__pskit/health` | status, no token |
| `POST /__pskit/queues/<name>` | enqueue one JSON value, a list, or `{"messages": [...]}`. `202 {"queued": [ids]}` |
| `GET /__pskit/queues/<name>` | `{"depth": n}` |
| `POST /__pskit/topics/<name>` | publish, then deliver. `{"message", "attributes"}` sets attributes when those are the only keys |
| `PUT` / `DELETE /__pskit/storage/<bucket>/<key>` | write or remove an object, then deliver |
| `POST /__pskit/invoke/<function>` | in-process invoke |
| `POST /__pskit/workflows/<name>` | start the embedded workflow: `202 {"execution_id", ...}`. `?wait=true` returns the result |
| `GET /__pskit/executions`, `GET /__pskit/executions/<id>`, `POST /__pskit/executions/<id>/cancel` | list, inspect and cancel runs ([workflow executions](workflow-executions.md)) |
| `GET /__pskit/logs` | captured logs ([below](#logs-and-stats)) |
| `GET /__pskit/logs/streams` | entry count and first/last time per function (`null` = host notes) |
| `DELETE /__pskit/logs[?function=]` | clear entries: all, one function's, or `function=__host__` for host notes. Also rewrites `host.jsonl` |
| `GET /__pskit/stats` | invocation counters per function and queue depths |

From a handler in that process (`PSKIT_ONPREM_ROOT` is set), call `submit_queue`, `submit_topic`, `put_object` or `delete_object` in `py_serverless_kit.runtime.onprem_host`.

A queue, bucket or topic can live in a service you already run: declare it under [`resources:`](resources.md) with `options.driver`. Queues take `directory` or `redis`, storage takes `directory` or `s3` (MinIO and other S3-compatible stores), and topics take `directory`. `pskit dashboard --serve` shows the host's health, stats, logs and workflow executions.

### Logs and stats

The host records everything into one log:

- `logging` records: `ctx.logger` and any `logging.getLogger(...)`, at `INFO` and above by default (set `PSKIT_LOG_LEVEL` in the environment that starts the host process to change it);
- `print()` / `sys.stdout` lines (source `stdout`, level `INFO`) and `sys.stderr` lines (source `stderr`, level `WARNING`);
- one `invocation` entry per handler call: function, event type, duration, and for HTTP the method, path and status. Failures (an exception, or HTTP status ≥ 500) are `ERROR`;
- host notes (source `host`): failed schedules, unreachable Redis/S3, runs aborted by a restart, the listen address.

Entries written during an invocation carry its `function` and `request_id`. The newest 5000 (`options.log_buffer`) are kept in memory and every entry is appended to `<data_dir>/logs/host.jsonl`. That file rotates at 10 MiB, keeping three old files, and the history is reloaded on restart. Messages longer than 16 KiB are truncated.

```bash
pskit logs                          # newest 100 entries
pskit logs -f --function worker     # follow one function
pskit logs --level error --source invocation -n 500
pskit logs -q timeout --json        # one JSON object per line
pskit logs --delete worker --yes    # clear one function's entries
```

`GET /__pskit/logs` (admin token when set):

| Parameter | Meaning |
|---|---|
| `since=N` | entries after `seq` N, oldest first: poll again with the returned `next` for a live tail. `0` or absent: the newest `limit` entries |
| `before=N` | the `limit` entries just before `seq` N (scroll back) |
| `limit` | default 200, max 2000 |
| `level` | minimum level: `DEBUG`, `INFO`, `WARNING` (`WARN`), `ERROR`, `CRITICAL` |
| `function`, `source` | exact match. Source is `function`, `host`, `stdout`, `stderr` or `invocation` |
| `q` | case-insensitive text search in the message |

```json
{"entries": [{"seq": 42, "ts": "2026-10-21T06:30:21.557+00:00", "level": "INFO", "source": "invocation",
              "function": "hello", "request_id": "f51c91a1...", "message": "GET /hello -> 200 (8.89 ms)",
              "fields": {"event_type": "http", "method": "GET", "path": "/hello", "status": 200, "duration_ms": 8.89}}],
 "next": 42, "oldest": 1, "more": false}
```

`next` advances past filtered-out entries, so polling with filters doesn't stall. `gap: true` (on `since` queries) means older entries were dropped from memory before you read them. `more` (on tail and `before` queries) means older matching entries exist.

`GET /__pskit/stats` returns `{"started_at", "uptime_s", "functions": {name: {"invocations", "errors", "avg_duration_ms", "last_duration_ms", "last_at", "last_error"}}, "queues": {name: depth}}`. Counters reset when the host restarts.

**Deploy targets** (`options.deploy`)

| `method` | What runs | Target needs | Laptop needs |
|---|---|---|---|
| `local` (default) | detached process on this machine | Python (the interpreter that runs `pskit`) | — |
| `ssh` or `scp` | one `release.tar.gz` extracted on the server, then a process or a systemd unit. Apply runs `systemctl restart` and waits for `/__pskit/health` | SSH. Python only if `python: system`. Passwordless `sudo` when `install: systemd` and `sudo: true` | OpenSSH (`ssh`, `scp`). Optional `.pem` |
| `docker` | image built on this machine, then `docker load` + `docker run` on the server. Apply waits until the container answers `/__pskit/health` | SSH. Docker is installed at apply when it is missing (`install_docker: true`, the default). Passwordless `sudo` when the daemon must be installed or the user cannot talk to it | Docker CLI, OpenSSH. Optional `.pem` |

**Several servers.** `options.cluster` (instead of `options.deploy`) runs the functions on a scaling cluster: Docker Swarm, Kubernetes (k3s) or Nomad on a master plus joined servers, with web replicas spread across the servers, capacity monitoring and alerts. Swarm and k3s load-balance the port; Nomad serves each server's own port and does not need a load balancer. For one URL, `pskit cluster balancer set NAME SERVER` runs nginx on one more server and keeps it in step with deploys and servers (`options.cluster.balancer_port` gives a second deployment its own port there). See [cluster.md](cluster.md).

**The stage remembers its machine.** A successful deploy writes `.pskit/onprem-<stage>/onprem_deployed.json` (the saved server, SSH login, port and admin token it used). Afterwards `pskit trigger`, `pskit logs`, `pskit resources send|check|browse`, executions, the dashboard and the studio's Test / Logs views talk to *that* host, even if `pskit package` or `plan` later re-rendered the spec for another machine. The next `pskit deploy` without `--server` (and without `server`, `host` or `method` under `deploy:` in `pskit.yml`) goes to the same saved server; `--server local` deploys on this machine, and `--server OTHER` points a single command at another saved server. `pskit deploy` prints `deployed on: <server> (<host>)`.

**Ports closed to this machine.** The host binds `127.0.0.1` on the server unless `options.host: 0.0.0.0`, and cloud firewalls often block 8080. When the host's port cannot be opened from here, pskit sends the control call (logs, triggers, uploads, HTTP tests) over the deploy's SSH login to `127.0.0.1:<port>` on the server, with the admin token on stdin rather than on a command line. To call the functions from other machines, still open the port (`options.host: 0.0.0.0` plus the firewall rule) or use `pskit client tunnel`.

When the server has **no Python**, use `python: bundle` (a portable CPython from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) is fetched at apply and copied with the app) or `method: docker` (the image is `FROM python:<minor>-slim`). From Windows, a Linux bundle is copied out of the downloaded archive and is not unpacked into the project (those trees contain test paths longer than `MAX_PATH`). Air-gapped: `python_home` (copy a tree you already have) or `python_url` + `python_sha256` (internal mirror of an `install_only` tarball).

```yaml
# A saved server (pskit resources onprem servers add edge1 ...): host, user, port and login come from it.
# `pskit deploy --server edge1` (or studio Deploy -> Machine) picks one for a single run.
deploy:
  server: edge1
  path: /opt/pskit/orders

# SSH + portable CPython + systemd (server does not need Python)
deploy:
  method: ssh
  host: 10.0.1.12                 # or deploy: ssh://pskit@10.0.1.12/opt/pskit/orders
  user: pskit
  port: 22
  pem: ${env:PSKIT_SSH_KEY}       # or identity_file. Empty: the SSH agent / default key (deploy asks in a terminal)
  # password_file: ~/.ssh/server.pass   # password login through sshpass (or auth: password + $SSHPASS)
  known_hosts: accept-new         # accept-new | ignore | path to a known_hosts file
  path: /opt/pskit/orders
  python: bundle                  # auto | system | bundle
  target_os: linux                # auto | linux | windows | darwin
  target_arch: x86_64             # auto | x86_64 | arm64  (drives pip wheels)
  install: systemd                # process | systemd (linux only)
  sudo: true                      # needed to write /etc/systemd/system

# Docker on a server. The image is built here, copied over SSH, and run there.
# No `pem`: the SSH agent / default key (`pskit deploy` offers to enter a path in a terminal).
# Docker is installed on the server first when `docker` is not already on PATH (apt/dnf/yum/apk).
deploy:
  method: docker
  host: 10.0.1.12
  user: pskit
  port: 22
  pem: ${env:PSKIT_SSH_KEY}          # or identity_file; or password_file (sshpass); or nothing (agent)
  image: pskit/orders:dev
  install_docker: true               # default for a remote host
  sudo: true                         # default; needed to install and start dockerd
  restart: unless-stopped

# Docker on this laptop only (no SSH, no .pem)
deploy:
  method: docker
  image: pskit/orders:dev
```

`options.host` is the bind address **on the target**. Use `0.0.0.0` so other machines can call a remote host. `advertise` is the URL stored in `pskit info`. SSH and remote Docker deploys default `advertise` to `http://<server>:<port>` when it is unset.

SSH and `scp` write `pskit-run.sh` plus `release.tar.gz` (the staged bundle, `onprem_ctl.py`, `pskit_host.json`, the unit when `install: systemd`, and `python/` when `python: bundle`). With `sudo: true`, apply runs `sudo -n mkdir` on `path` and `chown`s that directory to the SSH user (`azureuser` cannot create `/opt/pskit` itself), then copies the files. Apply does not delete `data_dir`. `install: systemd` runs `systemctl restart`. `install: process` runs `onprem_ctl.py start`. Either way the deploy fails if `http://127.0.0.1:<port>/__pskit/health` does not answer, and the failure includes `systemctl status` and `journalctl` when a unit was used.

Remote Docker (`method: docker` plus `host`, or `docker_host: ssh://user@host`) builds `pskit-<service>-<stage>` locally, saves it to a tar, and `scp`s that tar to `pskit-images/<container>/` in the SSH user's home. A script on the server installs Docker when it is missing (apt, dnf, yum, or apk), waits until `docker info` succeeds, runs `docker load` and `docker run`, and deletes the tar. The deploy fails if the container does not answer `/__pskit/health`, and the failure includes `docker logs`. The SSH user needs passwordless `sudo` (`sudo -n`) when Docker must be installed or when the user cannot talk to the daemon (`sudo` defaults to true). A key must be accepted by `ssh -o BatchMode=yes` (no passphrase prompt; load a protected key into the agent instead).

SSH login options, for `ssh`, `scp` and remote `docker`: `pem` / `identity_file` (a key file); nothing (the SSH agent,
`~/.ssh/id_*` and `~/.ssh/config`, or `auth: agent`); or a password through **sshpass** with `password_file: <file>`
or `auth: password` plus the `SSHPASS` environment variable. The password never appears on a command line, in
`pskit_host.json` or in Terraform state. sshpass is not available on Windows: run
`pskit resources onprem ssh-key user@host` once (it asks the password, installs `~/.ssh/pskit_ed25519`) and set `pem`
to that key. On Windows, if OpenSSH says the key is unprotected, restrict it with `icacls`. Set `install_docker: false` to refuse a server that does not already have Docker. A server whose package manager is not apt, dnf, yum, or apk is reported and left unchanged.

**Node.js / TypeScript services** (`provider.runtime: nodejs18 | nodejs20 | nodejs22 | nodejs24`): the host is still the Python process above (HTTP, schedules, queues, storage, topics, workflow executions and logs work the same). Each function runs in its own long-lived `node pskit_runtime/worker.js` process with that function's environment, started on its first invocation. Handler `console`/`ctx.logger` output appears in `pskit logs` and the dashboard as `function` entries (plain `console` output as `stdout`). Embedded workflows are still run by the host's executor; only the task functions run in Node.js. Where `node` comes from:

```yaml
deploy:
  method: ssh
  host: 10.0.1.12
  node: bundle            # auto | system | bundle. bundle downloads the official nodejs.org build for
                          # target_os/target_arch and ships only its `node` binary (node/bin/node)
  node_url: https://mirror.internal/node-v20.19.5-linux-x64.tar.gz   # optional mirror (.tar.gz, or .zip for Windows)
  node_sha256: <sha256 of that archive>                              # optional, checked after download
  node_home: /opt/node-v20                                           # or copy bin/node from a local install
  host_python: python3.12 # the host's interpreter (python: bundle downloads this one); default python3.12
```

`node: system` (the default) needs `node` on PATH: locally `pskit deploy` stops with a link to the installer when it is missing, and over SSH `pskit-run.sh` refuses to start without `./node/bin/node` or `node` on PATH. `method: docker` builds `FROM node:<major>-bookworm-slim` and adds Debian's `python3` (3.11) and `tzdata` for the host (one apt step instead of downloading Node.js into a Python image). Bundled Node.js archives are cached under `~/.cache/pskit/nodejs`.

**Resources:** `terraform_data.host` with create (`onprem_deploy.py apply`) and destroy (`onprem_deploy.py destroy`) `local-exec` provisioners.

**Limits:** no cloud authorizer and no IAM mapping. A `terraform.extra` resource from another cloud (`aws_*`, `google_*`, `azurerm_*`, and the other cloud prefixes) is omitted with a warning. A state backend of `s3`, `gcs` or `azurerm` warns; set `provider.state.backend` empty (see `providers.onprem` in examples 11 and 15) to keep state on this machine. Delivery is at-least-once. A missed schedule fires once on the next poll, not as a burst. The host does not kill a handler at `timeout`; `ctx.remaining_time_ms()` still counts down. If `method` is `local` and `provider.runtime` is not the interpreter running `pskit`, validation warns and the host still uses that interpreter. `python: bundle` needs network on first apply unless `python_home` or a cached archive under `~/.cache/pskit/python-standalone` is present. systemd units are written to `/etc/systemd/system` (set `sudo: true` unless the SSH user is root). That `sudo` is non-interactive (`sudo -n`), so the sudoers rule must not ask for a password.

Examples: [`examples/16-on-premises`](../examples/16-on-premises) (local process), [`examples/17-on-premises-remote`](../examples/17-on-premises-remote) (SSH / Docker / bundled Python).

---

## Writing your own provider

See [architecture.md](architecture.md#third-party-providers) and [`deploy_docs/CONTRIBUTING.md`](../deploy_docs/CONTRIBUTING.md).
