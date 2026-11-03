# Huawei DMS queue (`type: queue`)

Huawei Cloud's message queues are **Distributed Message Service (DMS)** for RabbitMQ or for Kafka. pskit has **no
queue trigger on Huawei**: a `queue` event is a validation error. You can still bind the queue to functions and send
or receive messages with a client library. (To consume a DMS queue from an on-premises pskit host, use a
[`custom` driver](../../resources.md#custom-drivers).)

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
| Connection address | instance → **Basic Information** → *Connection* → *Instance Address (Private Network)* | `192.168.0.10:5672` |
| Username | instance → **Basic Information** → *Username* | `pskit` |
| Password | set when buying (reset with **More → Reset Password**) | |
| VPC / subnet | instance → **Basic Information** → *Network* | `vpc-…` / `subnet-…` |
| Queue / topic name | RabbitMQ Web UI → **Queues**, or Kafka instance → **Topics** | `orders-jobs` |

```bash
export RABBIT_PASSWORD='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: huawei
  region: cn-north-4
  options:
    apig_instance_id: 0123456789abcdef0123456789abcdef     # needed for the http event below
  iam:
    role: pskit-functions                 # agency with VPC permissions
  environment:
    RABBIT_PASSWORD: ${env:RABBIT_PASSWORD}

resources:
  jobs:
    type: queue
    external: true                         # required: no managed queues on Huawei
    name: orders-jobs
    connection:
      host: 192.168.0.10
      port: 5672
      user: pskit
      password_env: RABBIT_PASSWORD

functions:
  submit:
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
    options:                               # join the broker's VPC
      vpc_id: 11111111-2222-3333-4444-555555555555
      network_id: 66666666-7777-8888-9999-000000000000
```

## 4. Use it in a handler

`requirements.txt`: `pika`

```python
import json

import pika
from py_serverless_kit import resource


def submit(event, ctx):
    q = resource("jobs")
    params = pika.ConnectionParameters(
        host=q["host"], port=int(q["port"]),
        credentials=pika.PlainCredentials(q["user"], ctx.env[q["password_env"]]),
    )
    with pika.BlockingConnection(params) as conn:
        ch = conn.channel()
        ch.basic_publish(exchange="", routing_key=q.native_name, body=json.dumps(event.http.json()))
    return {"queued": True}
```

For Kafka use `kafka-python` with the instance's bootstrap address.

Consuming: there is no trigger, so poll from a `schedule` function (`ch.basic_get(...)` in a loop with a time limit)
or consume elsewhere.

## 5. Test

```bash
pskit validate
pskit deploy
curl -X POST "$(pskit info --json | python -c 'import json,sys; print(json.load(sys.stdin)["functions"]["submit"]["url"])')" -d '{"id": 1}'
```

Console: RabbitMQ Web UI → **Queues** → `orders-jobs` → message count goes up.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` Huawei Cloud FunctionGraph does not support `queue` events in pskit `` | no queue triggers on Huawei; remove the `queue` event |
| Connection timed out | function not in the broker's VPC: set `vpc_id` / `network_id`, agency with VPC permissions |
| `ACCESS_REFUSED` | wrong username / password, or the user has no rights on the vhost |
