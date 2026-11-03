# Azure triggers, resources and workflows

Search terms: azure http trigger, function key, timer trigger, ncrontab, storage queue, poison queue, blob trigger,
service bus topic, service bus subscription, logic apps, azure workflow, azure resources, storage_connection

This page explains how each pskit trigger, resource and workflow becomes Azure infrastructure. For credentials, the
`provider` block and deploy commands, see the [Azure provider page](README.md).

## Azure HTTP trigger: function routes

An Azure `http` event becomes an `@app.route` registration (Python v2 model) or `app.http()` (Node.js v4 model) in the
generated entry file of the one Function App.

| Setting | Azure result |
|---|---|
| `path: /users/{id}` | route `users/{id}`, served at `https://<app>.azurewebsites.net/users/{id}` (no `/api` prefix) |
| `path: /files/{path+}` | route `files/{*path}` |
| `method: ANY` | all methods |
| `auth: none` | anonymous |
| `auth: key` | `FUNCTION` auth level: callers send `?code=<key>` or the `x-functions-key` header |
| `auth: iam`, `auth: jwt` | validation error |
| `cors` | the Function App's `site_config.cors`: the union of all origins, and `support_credentials` if any event sets `allow_credentials` |

Functions without any event, and task functions of Logic Apps workflows, get a private route
`POST /_pskit/invoke/<function>` with function-key auth.

## Azure schedule trigger: timer

An Azure `schedule` event becomes a timer trigger with a 6-field NCRONTAB expression (seconds first).

| pskit key | Timer expression |
|---|---|
| `rate: 5 minutes` | `0 */5 * * * *` |
| `rate: 2 hours` | `0 0 */2 * * *` |
| `cron: "0 2 * * *"` | `0 0 2 * * *` |
| `timezone` | ignored with a warning: Linux Consumption timers run in UTC |
| `input` | passed to the handler as `event.data` |

`run_on_startup` is off. `enabled: false` is not mapped to a timer setting on Azure; disable the function on Azure
with `providers.azure.functions.<fn>.enabled: false` instead.

## Azure queue trigger: Storage Queue

An Azure `queue` event creates an `azurerm_storage_queue` in the app's storage account and a queue trigger that uses
the `AzureWebJobsStorage` connection.

- Name: 3-63 lowercase letters, digits and dashes, otherwise a validation error.
- `fifo` is ignored with a warning (Storage Queues are not FIFO).
- `dead_letter` is ignored with a warning: Azure moves a message that keeps failing to `<queue>-poison`.
- `existing: true` creates nothing and reads the queue through the app setting named in `options.storage_connection`
  (default `AzureWebJobsStorage`, the app's own account).

Send a test message with `pskit trigger -f <fn> -e 0 -d '{...}'` (needs `azure-storage-queue`). The equivalent CLI
command is `az storage message put` with a base64 body; `pskit trigger --list` prints it.

## Azure storage trigger: Blob container

An Azure `storage` event creates a private `azurerm_storage_container` in the app's storage account and a blob trigger
on the path `<container>/<prefix>{name}<suffix>`.

- Container name: 3-63 lowercase letters, digits and dashes.
- Only created or updated blobs fire: `events: [deleted]` is a validation error.
- `existing: true` reads a container in another account through `options.storage_connection`.

## Azure topic trigger: Service Bus

An Azure `topic` event creates a Service Bus namespace (Standard, one per service), a topic, and one subscription per
subscribed function (named after the function, `max_delivery_count: 10`). The namespace connection string goes into the
app setting `PSKIT_SERVICEBUS`.

- `filter` is not applied on Service Bus subscriptions (warning): filter in the handler.
- `existing: true` needs `options.servicebus_namespace_id` and `options.servicebus_connection`; otherwise it is a
  validation error. pskit then reads the topic with a data source and still creates the subscription.

## Azure resources: managed, standalone and external

A `resources:` entry of type `queue`, `storage` or `topic` is a Storage Queue, Blob container or Service Bus topic on
Azure.

| Case | What pskit does on Azure |
|---|---|
| managed, used by an event | the event creates it |
| managed, no event uses it | created anyway (standalone) in the app's storage account / Service Bus namespace |
| `external: true` | nothing is created; the event's trigger uses `storage_connection` / `servicebus_connection` |
| `database`, `cache`, `custom` | must be `external: true`; only `connection` values reach handlers |

Bound functions get `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL` and one variable per `connection` entry. No id or
URL is added on Azure. Because app settings are shared, every function in the app sees every binding, whatever the
resource's `functions:` list says.

`iam` is not used on Azure: pskit assigns no roles. Give your code access with connection strings in
`environment` / `connection`, or assign a managed identity with `provider.terraform.extra`.

Portal walkthroughs: [Azure resource guides](../../resource-guides/azure/README.md).

## Azure workflows: embedded engine or Logic Apps

Azure workflows use the **embedded engine** by default: `engine: auto` keeps it, so existing projects don't change.
pskit adds an HTTP function `<workflow>-orchestrator` with the route `POST /workflows/<workflow>` that runs the state
machine and calls the task handlers in the same app. The whole run must fit in one call (600 s at most);
`pskit validate` warns about this.

`engine: native` compiles the workflow to an **Azure Logic App** (Consumption): `azurerm_logic_app_workflow`, an HTTP
request trigger named `manual`, and one `azurerm_logic_app_action_custom` per action. Task states call
`POST /_pskit/invoke/<function>` on the Function App with the host's default function key.

```yaml
workflows:
  order-pipeline:
    engine: native            # opt in to Logic Apps
    timeout: 3600             # run limit (default 1 hour)
    options:
      sync: true              # default true: the trigger answers with the output; false for long runs
    start_at: Validate
    states:
      Validate: {type: task, function: validate-order, next: Charge}
      Charge: {type: task, function: charge-order, end: true}
```

Start it with a POST to the callback URL from `pskit info`, or `pskit workflow start order-pipeline -i '{...}'`. Logic
Apps limits: task HTTP calls time out after 120 s (validation warns when a task function's timeout is longer), only the
first retry rule is used, `map` runs one item at a time. Full list:
[workflows.md](../../workflows.md#compiler-notes-and-limits).

On Azure, `pskit workflow executions` and `status` are not available: embedded runs keep no history and return their
`execution_id` in the response.

## Call another function with invoke() on Azure

`invoke()` on Azure needs the target's URL. Set `PSKIT_ENDPOINT_<NAME>` in the caller's environment to an HTTP URL of
the target function (from `pskit info`); `invoke()` then POSTs the payload there. Without it, `invoke()` raises an error
that names the variable. See `examples/09-function-invoke`.

## Send test events to Azure triggers

`pskit trigger` and the studio **Test** page send Azure queue messages, blob uploads and Service Bus messages with the
Azure SDKs on your machine, and HTTP requests to the function URLs.

| Trigger | Sent by pskit | Notes |
|---|---|---|
| http | yes | `auth: key` routes need the key |
| queue | yes | `azure-storage-queue` |
| storage | yes | `azure-storage-blob` |
| topic | yes | `azure-servicebus` |
| schedule | no | run it in the portal: Function App → Functions → the timer → Code + Test → Test/Run |

Connection strings come from the deployment, or from `AZURE_STORAGE_CONNECTION_STRING` and
`AZURE_SERVICEBUS_CONNECTION_STRING` when set.

## See also

- [Azure provider page](README.md)
- [Azure resource guides](../../resource-guides/azure/README.md)
- [events.md](../../events.md#azure-one-function-app-per-service), [workflows.md](../../workflows.md),
  [resources.md](../../resources.md)
- [Triggers overview](../../triggers/README.md), [Workflows guide](../../deployment/workflows.md)
