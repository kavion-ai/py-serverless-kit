# IBM Event Streams topic (`type: topic`)

Publish to (or read from) an Event Streams (Apache Kafka) topic from a handler.

**Not supported on IBM Cloud:** `topic` triggers. pskit can't subscribe a Code Engine function to a topic. Consume it
from the on-premises host with a `custom` Kafka driver class
(`examples/19-custom-drivers` has a Kafka template), or poll from an HTTP
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

## 4. Use it in a handler

`requirements.txt`: `kafka-python` (pure Python, so it vendors cleanly)

## 5. Test

Console: instance → **Topics** → `order-events` → **Messages** to see what arrived.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` IBM Cloud Code Engine does not support `topic` events in pskit `` | IBM Cloud has HTTP triggers only in pskit |
| `SaslAuthenticationFailed` | user must be `token`; password is the credential's API key |
| `TopicAuthorizationFailed` | the credential's role is *Reader*; create a *Writer* credential |
| `UnknownTopicOrPartition` | topic name typo, or the *Lite* plan's single-topic limit |

```bash
export EVENTSTREAMS_PASSWORD='...'
```
