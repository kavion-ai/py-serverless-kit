# Azure Service Bus topic (`type: topic`)

Use a Service Bus topic you created in the portal: pskit adds one subscription per function on it and triggers the
function for every message, and handlers can publish to it.

Service Bus topics need the **Standard** or **Premium** tier (Basic has queues only).

## 1. Create the namespace and topic (portal)

1. Portal → **Service Bus** → **+ Create** → resource group, a globally unique namespace name, region,
   pricing tier **Standard** → **Review + create**.
2. Open the namespace → **Entities → Topics** → **+ Topic** → name (for example `order-events`) → **Create**.

## 2. Collect the values

| Value | Where in the portal | Example |
|---|---|---|
| Topic name | Namespace → **Entities → Topics** | `order-events` |
| Namespace resource ID | Namespace → **Settings → Properties** → *Id* (or Overview → *JSON View*) | `/subscriptions/<sub>/resourceGroups/acme-rg/providers/Microsoft.ServiceBus/namespaces/acme-bus` |
| Namespace host | Namespace → **Overview** → *Host name* | `acme-bus.servicebus.windows.net` |
| Connection string | Namespace → **Settings → Shared access policies** → a policy → *Primary Connection String* | `Endpoint=sb://acme-bus.servicebus.windows.net/;SharedAccessKeyName=...;SharedAccessKey=...` |

Create a dedicated policy rather than using `RootManageSharedAccessKey`: **Shared access policies → + Add** →
name `pskit-app`, tick **Send** and **Listen** → **Create**, then copy its *Primary Connection String*.

```bash
export ORDER_EVENTS_CONN='Endpoint=sb://acme-bus.servicebus.windows.net/;SharedAccessKeyName=pskit-app;SharedAccessKey=...'
```

## 3. Declare it in `pskit.yml`

```yaml
provider:
  name: azure
  region: westeurope
  options:
    subscription_id: ${env:ARM_SUBSCRIPTION_ID}
    servicebus_namespace_id: /subscriptions/<sub>/resourceGroups/acme-rg/providers/Microsoft.ServiceBus/namespaces/acme-bus
    servicebus_connection: ORDER_EVENTS_CONN      # app setting the topic trigger connects with
  environment:
    ORDER_EVENTS_CONN: ${env:ORDER_EVENTS_CONN}

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      namespace: acme-bus.servicebus.windows.net
      connection_string_env: ORDER_EVENTS_CONN

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events}
```

- Both `servicebus_namespace_id` and `servicebus_connection` are required for an external topic with a trigger;
  `pskit validate` reports an error otherwise.
- pskit **creates a subscription** named after the function in your topic (and deletes it on `pskit remove`). The
  identity running `pskit deploy` (`az login`) needs rights on the namespace to do that, for example *Azure Service Bus
  Data Owner* or *Contributor*.
- `topic.filter` is not applied on Azure (warning).

## 4. Use it in a handler

`requirements.txt`: `azure-servicebus`

```python
import json

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from py_serverless_kit import resource


def publish(event, ctx):
    topic = resource("order-events")
    with ServiceBusClient.from_connection_string(ctx.env[topic["connection_string_env"]]) as client:
        with client.get_topic_sender(topic.native_name) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps({"id": 1}), application_properties={"type": "paid"}))


def notify(event, ctx):
    for record in event.records:
        ctx.logger.info("event", extra={"body": record.body, "attributes": record.attributes})
```

## 5. Test

```bash
pskit validate
pskit deploy
export AZURE_SERVICEBUS_CONNECTION_STRING="$ORDER_EVENTS_CONN"
pskit resources send order-events -d '{"message": {"id": 1}, "attributes": {"type": "paid"}}'
pskit logs -f --function notify
```

Portal: Topic → **Service Bus Explorer** → **Send messages**; check the function's subscription under
Topic → **Subscriptions**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `existing topics need options.servicebus_namespace_id and options.servicebus_connection` | set both |
| Deploy fails reading the topic | wrong namespace ID or topic name, or the deploying identity can't read the namespace |
| Trigger doesn't fire, `Unauthorized` in logs | the policy lacks **Listen** |
| Messages in the subscription's dead-letter queue | the handler failed 10 times (`max_delivery_count`) |
