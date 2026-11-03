# Huawei DMS queue (`type: queue`)

Huawei Cloud's message queues are **Distributed Message Service (DMS)** for RabbitMQ or for Kafka. pskit has **no
queue trigger on Huawei**: a `queue` event is a validation error. You can still bind the queue to functions and send
or receive messages with a client library. (To consume a DMS queue from an on-premises pskit host, use a
`custom` driver.)

## 1. Create the instance (console)

**RabbitMQ:**

1. Console → **Distributed Message Service for RabbitMQ** → **Buy Instance**.
2. Region (same as the functions), AZ, version, flavor; **VPC** and **subnet** (note them: the function must join the
   same VPC); username and password for the broker; optionally **SSL** and **Public Access** → **Submit**.
3. Open the instance → **Web UI** (or the RabbitMQ management console) → create the queue, for example `orders-jobs`.

**Kafka:** **Distributed Message Service for Kafka** → **Buy Instance** (same VPC / subnet choices) → instance →
**Topics** → **Create Topic**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Connection address | instance → **Basic Information** → *Connection* → *Instance Address (Private Network)* | `192.0.2.10:5672` |
| Username | instance → **Basic Information** → *Username* | `pskit` |
| Password | set when buying (reset with **More → Reset Password**) | |
| VPC / subnet | instance → **Basic Information** → *Network* | `vpc-…` / `subnet-…` |
| Queue / topic name | RabbitMQ Web UI → **Queues**, or Kafka instance → **Topics** | `orders-jobs` |

## 4. Use it in a handler

`requirements.txt`: `pika`

For Kafka use `kafka-python` with the instance's bootstrap address.

Consuming: there is no trigger, so poll from a `schedule` function (`ch.basic_get(...)` in a loop with a time limit)
or consume elsewhere.

## 5. Test

Console: RabbitMQ Web UI → **Queues** → `orders-jobs` → message count goes up.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` Huawei Cloud FunctionGraph does not support `queue` events in pskit `` | no queue triggers on Huawei; remove the `queue` event |
| Connection timed out | function not in the broker's VPC: set `vpc_id` / `network_id`, agency with VPC permissions |
| `ACCESS_REFUSED` | wrong username / password, or the user has no rights on the vhost |

An address or login copied from the source was rewritten in this card. Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.

```bash
export RABBIT_PASSWORD='...'
```
