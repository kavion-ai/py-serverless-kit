# Azure Functions provider (`azure`)

Search terms: azure, microsoft azure, azure functions, function app, az login, ARM_SUBSCRIPTION_ID, subscription id,
service principal, consumption plan, application insights, log analytics, azurerm, deploy to azure, eastus

The `azure` provider deploys all functions of a service into **one Linux Function App** on Azure Functions. pskit writes
Terraform JSON for the `hashicorp/azurerm` plug-in (`>= 4.9`) and runs Terraform.

| Fact | Value |
|---|---|
| Tier | **stable** |
| Default region | `eastus` |
| Python runtimes | `python3.9`, `python3.10`, `python3.11`, `python3.12` (default `python3.12`) |
| Node.js runtimes | `nodejs18`, `nodejs20`, `nodejs22` (`application_stack.node_version` 18 / 20 / 22) |
| Max timeout | 600 s (`functionTimeout` in `host.json`, one value for the whole app) |
| Triggers | `http`, `schedule`, `queue`, `storage`, `topic` |
| Workflows | embedded by default; `engine: native` deploys an Azure Logic App |
| Dependencies | built remotely by Oryx from `requirements.txt` (`azure-functions` is added); Node.js from `package.json` (`@azure/functions` v4 is added) |

This page covers credentials, the `provider` block, deploy / info / remove and logs. Triggers, resources and
workflows are in [triggers-and-resources.md](triggers-and-resources.md).

## Set up Azure credentials for pskit

The Azure provider signs in the way the `azurerm` Terraform plug-in does, and `azurerm` 4 always needs a subscription
id.

1. Install Terraform and the Azure CLI. `pskit doctor -p azure` prints the install commands for your OS
   (`winget install -e --id Microsoft.AzureCLI`, `brew install azure-cli`, or the Debian script).
2. Sign in, either way:

   | Way | Commands |
   |---|---|
   | Azure CLI (interactive) | `az login`, then `az account set --subscription <id>` |
   | Service principal | `ARM_CLIENT_ID`, `ARM_TENANT_ID` and `ARM_CLIENT_SECRET` (or `ARM_CLIENT_CERTIFICATE_PATH`, or `ARM_USE_OIDC` in CI) |

3. Give the subscription id, either way:

```bash
export ARM_SUBSCRIPTION_ID=<subscription id>       # PowerShell: $env:ARM_SUBSCRIPTION_ID = "<id>"
```

   or in `pskit.yml`: `provider.options.subscription_id: ${env:ARM_SUBSCRIPTION_ID}` (this is what
   `pskit init -p azure` writes).
4. Run the check:

```bash
pskit doctor -p azure
```

It reports `Azure CLI login found` or `service principal from ARM_* variables`, and `provider.options.subscription_id`
as set or missing.

5. Optional, on your machine only: `pip install azure-monitor-query azure-identity` for `pskit logs`, and
   `pip install azure-storage-queue azure-storage-blob azure-servicebus` for `pskit trigger` / `pskit resources send`.

## Set up Azure credentials in studio

The studio **Setup & credentials** page checks the Azure CLI, the login and the subscription id.

1. Run `pskit studio --open` in the project folder.
2. In the sidebar, click **Setup & credentials**. In **Provider**, pick **Azure Functions**.
3. On the credentials check, click **Sign in (az login)**. A browser window opens; the command output appears in the
   **Running: az login** section.
4. In the **Environment variables** section, type your subscription id next to `ARM_SUBSCRIPTION_ID` and click **Set
   for this session**. For a service principal, set `ARM_TENANT_ID`, `ARM_CLIENT_ID` and `ARM_CLIENT_SECRET` the same
   way. Secret values are not sent back to the browser. They last until studio stops; to keep them, set them in your
   shell before `pskit studio`.
5. The same section has `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_SERVICEBUS_CONNECTION_STRING`. They are only for
   **Browse account** and test messages; by default pskit reads them from the deployment.
6. Click **Check again** until the badge says **ready to deploy to Azure Functions**.

## Write the Azure provider block in pskit.yml

The Azure `provider` block selects Azure and sets app-wide defaults.

```yaml
provider:
  name: azure
  region: westeurope                 # default eastus
  stage: dev
  runtime: python3.12                # python3.9-3.12 or nodejs18/20/22
  timeout: 30                        # max 600; the largest function timeout becomes host.json functionTimeout
  log_retention_days: 30             # Log Analytics retention (at least 30)
  environment:
    LOG_LEVEL: INFO
  tags:
    team: payments
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}   # required (or the ARM_SUBSCRIPTION_ID variable)
    resource_group: existing-rg                   # optional: use an existing resource group
    plan_sku: Y1                                  # default Y1 (Consumption)
    app_insights: true                            # default true
    storage_connection: OTHER_STORAGE             # app setting name, for `existing` queues/containers elsewhere
    servicebus_namespace_id: /subscriptions/.../namespaces/my-sb   # for `existing` topics
    servicebus_connection: SB_CONNECTION          # app setting holding that namespace's connection string
```

`memory`, `architecture`, `concurrency` and `functions.<fn>.options` are not used by the Azure provider: one Function
App on a shared plan has no per-function memory or instance settings. `iam.statements` are ignored with a warning.

## Azure provider options reference

The Azure `provider.options` keys choose the subscription, the plan and the connections for existing resources.

| Option | Default | What it does |
|---|---|---|
| `subscription_id` | `ARM_SUBSCRIPTION_ID` | subscription Terraform deploys into |
| `resource_group` | a new group `<service>-<stage>-rg` | name of an existing resource group (read with a data source, never deleted) |
| `plan_sku` | `Y1` | `azurerm_service_plan.sku_name`: `Y1` Consumption, `EP1`-`EP3` Elastic Premium, `B1`-`B3`, `S1`-`S2`, `P1v3`, `P2v3` dedicated |
| `app_insights` | `true` | creates a Log Analytics workspace and Application Insights; `false` turns both off (and `pskit logs` with them) |
| `storage_connection` | `AzureWebJobsStorage` | name of an app setting holding the connection string of another storage account, used by `existing: true` queues and containers |
| `servicebus_namespace_id` | none | resource id of an existing Service Bus namespace; required with `existing: true` topics |
| `servicebus_connection` | `PSKIT_SERVICEBUS` | name of an app setting with that namespace's connection string; required with `existing: true` topics |

Put the connection string itself in `provider.environment` (for example `OTHER_STORAGE: ${env:OTHER_STORAGE}`); the
option only names the setting.

In studio, **Overview & provider → Azure Functions options** shows **Subscription ID**, **Resource group**, **Plan
SKU**, **Application Insights**, **Storage connection setting**, **Service Bus namespace ID** and **Service Bus
connection setting**.

## What pskit creates on Azure

The Azure provider creates these Terraform resources for a service:

| Resource | Name | Notes |
|---|---|---|
| `azurerm_resource_group` | `<service>-<stage>-rg` | skipped with `options.resource_group` |
| `azurerm_storage_account` | letters of `<service><stage>` + a hash | Standard LRS, TLS 1.2; holds the app's files, queues and containers |
| `azurerm_service_plan` | `<service>-<stage>-plan` | Linux, `plan_sku` |
| `azurerm_linux_function_app` | `<service>-<stage>-<hash>` | Functions v4, HTTPS only, zip deploy of `artifact.zip`, remote build |
| `azurerm_log_analytics_workspace` + `azurerm_application_insights` | `<prefix>-logs`, `<prefix>-ai` | when `app_insights` is true |
| `azurerm_storage_queue`, `azurerm_storage_container` | your names | queue and storage events, standalone resources |
| `azurerm_servicebus_namespace` (Standard), `_topic`, `_subscription` | | topic events |
| `azurerm_logic_app_workflow` and friends | | `engine: native` workflows |

pskit generates `function_app.py` (Python v2 model) or `pskit_entry.js` (Node.js v4 model) and `host.json` in the
bundle. `host.json` sets `routePrefix` to `""`, so your paths are served as written, without Azure's `/api` prefix.

## Azure app settings are shared by all functions

On Azure every function of a service runs in the same Function App, so the environment variables are app settings
shared by all of them.

- `provider.environment`, every `functions.<fn>.environment` and every `PSKIT_RESOURCE_*` binding are merged into one
  set. When two functions set the same key to different values, validation warns and the last one wins.
- `PSKIT_FUNCTION` and `PSKIT_HANDLER` are not app settings; the generated `function_app.py` passes the function name.
- pskit owns the app settings. A setting you add in the portal (**Function App → Settings → Environment variables**)
  is removed on the next `pskit deploy`. Add it to `pskit.yml` instead.
- pskit also sets `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, `ENABLE_ORYX_BUILD=true` and
  `AzureWebJobsFeatureFlags=EnableWorkerIndexing`.

## Deploy to Azure from the terminal

Deploying to Azure runs `terraform init` and `terraform apply` in `.pskit/azure-<stage>/`.

```bash
pskit init my-api --provider azure        # writes options.subscription_id: ${env:ARM_SUBSCRIPTION_ID}
cd my-api
export ARM_SUBSCRIPTION_ID=<subscription id>
pskit validate                            # checks against Azure, no cloud calls
pskit plan -s dev                         # optional: terraform plan
pskit deploy -s dev                       # or --confirm to review the plan first
pskit info -s dev                         # URLs, ids, portal links
```

The first deploy takes several minutes: the Function App runs a remote Oryx build of your `requirements.txt` after
the zip upload. `--upgrade` runs `terraform init -upgrade`. `-r northeurope` overrides the region for one command.

## Deploy to Azure from studio

Deploying to Azure from studio uses the credentials of the machine running studio.

1. Sidebar **Overview & provider** → **Provider** section → click the **Azure Functions** card. If the dialog lists
   items that won't run on Azure, pick **Switch & disable on Azure Functions** or **Switch only (fix later)**.
2. Under **Defaults for every function**, pick the **Region**. Fill **Subscription ID** in **Azure Functions options**
   (the default `${env:ARM_SUBSCRIPTION_ID}` reads the variable).
3. Click **Save** in the top bar.
4. In the top bar, check **validate & deploy as** shows **Azure Functions** and set the **stage**.
5. Sidebar **Deploy** → click **Validate**, **Plan**, then **Deploy**. Watch the live log. A `prod*` stage asks you to
   type `azure/<stage>`.
6. Click **Info** for the URLs.

## Find the Azure URLs and portal links

After an Azure deploy, `pskit info` prints one entry per function with `id` `<app-name>/<function>` and a portal link
`https://portal.azure.com/#resource<app-id>/functions`.

- **HTTP endpoint:** `https://<app-name>.azurewebsites.net`. A path `/hello` is served at
  `https://<app-name>.azurewebsites.net/hello` (no `/api`). `{path+}` becomes Azure's `{*path}`.
- **Function keys:** `auth: key` routes need `?code=<key>` or the `x-functions-key` header. Find keys in the portal
  under **Function App → Functions → App keys**.
- **Invoke-only functions** (no events) get `POST /_pskit/invoke/<function>` with function-key auth.
- **Embedded workflows:** `POST https://<app-name>.azurewebsites.net/workflows/<workflow>`.
- **Logic Apps workflows:** the HTTP trigger's callback URL (it contains a SAS signature: treat it as a secret).

## Read Azure logs with pskit logs and studio

Azure Functions logs go to Application Insights, backed by a Log Analytics workspace. pskit adds a Terraform output
`log_analytics_workspace_id`; `pskit logs` queries the `AppTraces` table of that workspace with
`DefaultAzureCredential` (your `az login` or `ARM_*` variables).

```bash
pip install azure-monitor-query azure-identity
pskit logs -s dev                          # last 15 minutes
pskit logs -f --function hello --level warning
pskit logs -q "order 42" --json
```

Azure logs are read only: pskit can't delete them; they expire with the workspace retention
(`log_retention_days`, at least 30). With `app_insights: false` there is no workspace, and `pskit logs` points to the
portal instead. In studio, open **Logs** in the sidebar.

## Remove an Azure deployment

Removing an Azure stage runs `terraform destroy` in `.pskit/azure-<stage>/`.

```bash
pskit remove -s dev --yes
pskit remove -s dev --keep-resources       # keep queues, containers and topics with their data
```

With `--keep-resources` the storage queues, blob containers and Service Bus topics are kept, and so are the storage
account, Service Bus namespace and resource group that hold them (deleting those would delete the data). In studio:
**Deploy** → choose the remove switch → **Remove** → type `azure/<stage>`.

## Azure limits and gotchas

The Azure provider rejects or changes these settings:

- HTTP `auth: iam` and `auth: jwt` are validation errors. Use `none` or `key`, or put API Management / Easy Auth in front.
- Timers run in UTC on Linux Consumption: `timezone` is ignored with a warning.
- Queue and container names must be 3-63 lowercase letters, digits and dashes.
- Blob triggers fire on created or updated blobs only: `events: [deleted]` is an error.
- Storage Queues are not FIFO (`fifo` warns) and poison messages go to `<queue>-poison` (`dead_letter` warns).
- `topic.filter` is not applied on Service Bus subscriptions (warning).
- One `functionTimeout` for the whole app: the largest function timeout, capped at 600 s.
- Do not put your own `function_app.py` or `host.json` at the project root: pskit generates them.

## Complete minimal Azure example project

The minimal Azure project below has an HTTP function, a timer and a Storage Queue worker.

```yaml
service: hello-azure

provider:
  name: azure
  region: westeurope
  stage: dev
  timeout: 15
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}

functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello

  nightly:
    handler: app.handlers.nightly
    events:
      - schedule: {cron: "0 2 * * *", input: {report: daily}}     # UTC

  worker:
    handler: app.handlers.worker
    events:
      - queue: {name: hello-azure-jobs, batch_size: 10}
```

Use the same `app/handlers.py` as the
[AWS example](../aws/README.md#handler-code-and-commands-for-the-minimal-aws-example): the handler
code does not change between clouds.

```bash
export ARM_SUBSCRIPTION_ID=<subscription id>
pskit invoke -f hello --path "/hello?name=Ada"
pskit deploy -s dev
pskit trigger -f worker -e 0 -d '{"order_id": 1}'
pskit logs -f --function worker
pskit remove -s dev --yes
```

This config creates seven Terraform resources: resource group, storage account, plan, Function App, Log Analytics
workspace, Application Insights and the `hello-azure-jobs` queue.

## See also

- [triggers-and-resources.md](triggers-and-resources.md): triggers, resources, Logic Apps
- [Azure resource guides](../../resource-guides/azure/README.md): portal walkthroughs for queues, blobs, Service Bus,
  databases and caches
- [providers.md](../../providers.md#azure-azure-functions), [configuration.md](../../configuration.md)
- [Deploy, remove and info](../../deployment/deploy-remove-info.md), [Logs](../../deployment/logs.md)
- [All providers](../README.md), [AWS](../aws/README.md), [GCP](../gcp/README.md)
