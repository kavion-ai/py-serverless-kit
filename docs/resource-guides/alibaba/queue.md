# Alibaba Cloud SMQ / MNS queue (`type: queue`)

Use a Simple Message Queue (SMQ, formerly Message Service / MNS) queue from your functions.

> **No queue trigger on Alibaba Cloud.** pskit's Alibaba provider has no `queue` event: `pskit validate` rejects
> `- queue: ...` there. Declare the queue as an external resource and send / receive with the MNS SDK, for example
> from a `schedule` function that drains it. Need push delivery? Publish to an MNS **topic** instead and use a
> [topic trigger](topic.md).

## 1. Create the queue (console)

1. Console → **Simple Message Queue (formerly MNS)** → pick the region → **Queues** → **Create Queue**.
2. Name (for example `orders-jobs`), keep the defaults for message retention, visibility timeout and long polling →
   **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Queue name | SMQ → **Queues** | `orders-jobs` |
| Endpoint | SMQ → **Queues** → **Get Endpoint** (top right), or the queue's details page: *Internet* / *Internal* endpoint | `https://1234567890.mns.cn-hangzhou.aliyuncs.com` |
| AccessKey | RAM user with `AliyunMNSFullAccess` (or a custom policy on this queue) | `LTAI...` |

```bash
export MNS_ACCESS_KEY_ID=LTAI...
export MNS_ACCESS_KEY_SECRET=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: alibaba
  region: cn-hangzhou
  environment:
    MNS_ACCESS_KEY_ID: ${env:MNS_ACCESS_KEY_ID}
    MNS_ACCESS_KEY_SECRET: ${env:MNS_ACCESS_KEY_SECRET}

resources:
  jobs:
    type: queue
    external: true                # required: pskit does not create queues on Alibaba
    name: orders-jobs
    connection:
      endpoint: https://1234567890.mns.cn-hangzhou.aliyuncs.com
      access_key_env: MNS_ACCESS_KEY_ID
      secret_key_env: MNS_ACCESS_KEY_SECRET

functions:
  api:                            # sends messages
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
  drain:                          # receives them every minute
    handler: app.handlers.drain
    events: [{schedule: 1 minute}]
```

## 4. Use it in a handler

`requirements.txt`: `aliyun-mns-sdk`

```python
import json

from mns.account import Account
from mns.mns_exception import MNSExceptionBase
from mns.queue import Message
from py_serverless_kit import resource


def _queue(ctx):
    jobs = resource("jobs")
    account = Account(jobs["endpoint"], ctx.env[jobs["access_key_env"]], ctx.env[jobs["secret_key_env"]])
    return account.get_queue(jobs.native_name)


def submit(event, ctx):
    _queue(ctx).send_message(Message(json.dumps(event.http.json())))
    return {"queued": True}


def drain(event, ctx):
    queue = _queue(ctx)
    try:
        for msg in queue.batch_receive_message(16, 1):          # up to 16 messages, wait 1 s
            ctx.logger.info("job", extra={"body": msg.message_body})
            queue.delete_message(msg.receipt_handle)             # only after it succeeded
    except MNSExceptionBase as exc:
        if exc.type != "MessageNotExist":                       # empty queue
            raise
```

Messages that aren't deleted become visible again after the queue's visibility timeout.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list       # the PSKIT_RESOURCE_* variables for jobs
```

Console: SMQ → **Queues** → `orders-jobs` → **Send Messages** / **Receive Messages**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `queue` events in pskit`` (validate) | expected: Alibaba has no queue trigger; use the SDK or a topic |
| `managed queue resources that no event uses are not supported` | set `external: true` |
| `AccessDenied` / `InvalidAccessKeyId` | check the RAM user's policy and the key pair |
| Messages processed twice | delete each message after handling it, and keep processing shorter than the visibility timeout |
