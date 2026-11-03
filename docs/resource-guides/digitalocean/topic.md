# DigitalOcean Managed Kafka topic (`type: topic`)

Publish to (or read from) a topic in a Managed Kafka cluster from a handler.

**Not supported on DigitalOcean:** `topic` triggers. Consume from a `schedule` function, or from the
[on-premises host](../../resources.md#custom-drivers) with a `custom` Kafka driver class
([`examples/19-custom-drivers`](../../../examples/19-custom-drivers) has a Kafka template).

## 1. Create the cluster and topic (control panel)

1. Control panel → **Databases** → **Create Database Cluster** → engine **Kafka** → region, plan, name → **Create
   Database Cluster**.
2. In the cluster → **Topics** → **Create topic** → name (for example `order-events`), partitions → **Create**.
3. **Users & ACLs** (optional): add a user with *produce* / *consume* permission on the topic instead of using
   `doadmin`.

## 2. Collect the values

| Value | Where in the control panel | Example |
|---|---|---|
| Topic name | cluster → **Topics** | `order-events` |
| Host / port | cluster → **Overview** → **Connection details** → *Public network* | `acme-kafka-do-user-0.db.ondigitalocean.com`, `25073` |
| User / password | same panel (or **Users & ACLs**) | `doadmin` / `...` |
| Security protocol / SASL mechanism | same panel (shown with the connection parameters) | `SASL_SSL`, `SCRAM-SHA-256` |
| CA certificate | same panel → **Download CA certificate** | `ca-certificate.crt` |

Use the protocol and mechanism the panel shows for your cluster; the example values above are typical.

```bash
export KAFKA_PASSWORD='...'
```

Put the CA certificate in your project (for example `app/certs/kafka-ca.crt`) so it is packaged with the handler.

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: digitalocean
  region: nyc1
  options:
    namespace: fn-00000000-0000-0000-0000-000000000000
  environment:
    KAFKA_PASSWORD: ${env:KAFKA_PASSWORD}

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      bootstrap_servers: acme-kafka-do-user-0.db.ondigitalocean.com:25073
      user: doadmin
      password_env: KAFKA_PASSWORD
      security_protocol: SASL_SSL
      sasl_mechanism: SCRAM-SHA-256
      ca_file: certs/kafka-ca.crt    # relative to the app package

functions:
  publish:
    handler: app.handlers.publish
    events: [{http: POST /events}]
```

## 4. Use it in a handler

`requirements.txt`: `kafka-python` (pure Python, so it vendors cleanly)

```python
import json
import os

from kafka import KafkaProducer
from py_serverless_kit import resource

_producer = None


def publish(event, ctx):
    global _producer
    t = resource("order-events")
    if _producer is None:   # reuse the connection across warm invocations
        _producer = KafkaProducer(
            bootstrap_servers=t["bootstrap_servers"].split(","),
            security_protocol=t["security_protocol"],
            sasl_mechanism=t["sasl_mechanism"],
            sasl_plain_username=t["user"],
            sasl_plain_password=ctx.env[t["password_env"]],
            ssl_cafile=os.path.join(os.path.dirname(__file__), t["ca_file"]),
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

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `topic` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit |
| `SaslAuthenticationFailed` | check the mechanism the control panel shows, and the user / password |
| `certificate verify failed` | the CA certificate isn't packaged or `ca_file` points elsewhere |
| timed out from the function | trusted sources block it, see [README](README.md#values-you-need-for-most-digitalocean-services) |
