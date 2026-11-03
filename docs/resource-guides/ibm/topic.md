# IBM Event Streams topic (`type: topic`)

Publish to (or read from) an Event Streams (Apache Kafka) topic from a handler.

**Not supported on IBM Cloud:** `topic` triggers. pskit can't subscribe a Code Engine function to a topic. Consume it
from the [on-premises host](../../resources.md#custom-drivers) with a `custom` Kafka driver class
([`examples/19-custom-drivers`](../../../examples/19-custom-drivers) has a Kafka template), or poll from an HTTP
function that something calls.

## 1. Create the instance and topic (console)

1. Console → **Catalog** → **Event Streams** → plan (*Lite* allows one topic with one partition; *Standard* for real
   use) → region → **Create**.
2. In the instance → **Topics** → **Create topic** → name (for example `order-events`), partitions, retention →
   **Create topic**.
3. **Service credentials** → **New credential** → role *Writer* (*Reader* to consume only) → **Add**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | instance → **Topics** | `order-events` |
| Bootstrap servers | **Service credentials** → **View credentials** → `kafka_brokers_sasl` (comma-join the list) | `broker-0-xxxx.kafka.svc01.us-south.eventstreams.cloud.ibm.com:9093,...` |
| User | same credential → `user` | `token` |
| Password | same credential → `password` (the API key) | `...` |

Connections use `SASL_SSL` with mechanism `PLAIN`.

```bash
export EVENTSTREAMS_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: ibm
  region: us-south
  environment:
    EVENTSTREAMS_PASSWORD: ${env:EVENTSTREAMS_PASSWORD}

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      bootstrap_servers: broker-0-xxxx.kafka.svc01.us-south.eventstreams.cloud.ibm.com:9093
      user: token
      password_env: EVENTSTREAMS_PASSWORD

functions:
  publish:
    handler: app.handlers.publish
    events: [{http: POST /events}]
```

## 4. Use it in a handler

`requirements.txt`: `kafka-python` (pure Python, so it vendors cleanly)

```python
import json

from kafka import KafkaProducer
from py_serverless_kit import resource

_producer = None


def publish(event, ctx):
    global _producer
    t = resource("order-events")
    if _producer is None:   # reuse the connection across warm invocations
        _producer = KafkaProducer(
            bootstrap_servers=t["bootstrap_servers"].split(","),
            security_protocol="SASL_SSL",
            sasl_mechanism="PLAIN",
            sasl_plain_username=t["user"],
            sasl_plain_password=ctx.env[t["password_env"]],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    _producer.send(t.native_name, event.http.json()).get(timeout=10)
    return {"published": True}
```

## 5. Test

```bash
pskit validate
pskit deploy
pskit info      # the function URL; POST a JSON body to /events
```

Console: instance → **Topics** → `order-events` → **Messages** to see what arrived.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` IBM Cloud Code Engine does not support `topic` events in pskit `` | IBM Cloud has HTTP triggers only in pskit |
| `SaslAuthenticationFailed` | user must be `token`; password is the credential's API key |
| `TopicAuthorizationFailed` | the credential's role is *Reader*; create a *Writer* credential |
| `UnknownTopicOrPartition` | topic name typo, or the *Lite* plan's single-topic limit |
