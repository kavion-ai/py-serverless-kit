# DigitalOcean Managed Kafka topic (`type: topic`)

Publish to (or read from) a topic in a Managed Kafka cluster from a handler.

**Not supported on DigitalOcean:** `topic` triggers. Consume from a `schedule` function, or from the
on-premises host with a `custom` Kafka driver class
(`examples/19-custom-drivers` has a Kafka template).

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

Put the CA certificate in your project (for example `app/certs/kafka-ca.crt`) so it is packaged with the handler.

## 4. Use it in a handler

`requirements.txt`: `kafka-python` (pure Python, so it vendors cleanly)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` DigitalOcean Functions does not support `topic` events in pskit `` | DigitalOcean has HTTP and schedule triggers only in pskit |
| `SaslAuthenticationFailed` | check the mechanism the control panel shows, and the user / password |
| `certificate verify failed` | the CA certificate isn't packaged or `ca_file` points elsewhere |
| timed out from the function | trusted sources block it, see README |

```bash
export KAFKA_PASSWORD='...'
```
