# Tencent Cloud TDMQ for CMQ queue (`type: queue`)

Use a message queue from your functions. Tencent's original CMQ service has moved to **TDMQ for CMQ**; the console
and APIs below are TDMQ's.

> **No queue trigger on Tencent Cloud.** pskit's Tencent provider has no `queue` event: `pskit validate` rejects
> `- queue: ...` there. Declare the queue as an external resource and send to it with the Tencent Cloud SDK. To react to
> messages, consume them with the TDMQ CMQ client from a `schedule` function, or put work into a COS bucket and use a
> [storage trigger](storage.md).

## 1. Create the queue (console)

1. Console → **TDMQ** → **CMQ** → **Queue Service** (the exact menu label can differ by console language and version) →
   pick the region → **Create**.
2. Name (for example `orders-jobs`), keep the default retention and visibility timeout → **Submit**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Queue name | TDMQ for CMQ → queue list | `orders-jobs` |
| Region | the region selector | `ap-guangzhou` |
| Access address | the queue's details / **Access** information (private and public network endpoints) | shown in the console |
| SecretId / SecretKey | CAM sub-user with a TDMQ policy (for example `QcloudTDMQFullAccess`) | `AKID...` |

```bash
export TDMQ_SECRET_ID=AKID...
export TDMQ_SECRET_KEY=...
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: tencent
  region: ap-guangzhou
  environment:
    TDMQ_SECRET_ID: ${env:TDMQ_SECRET_ID}
    TDMQ_SECRET_KEY: ${env:TDMQ_SECRET_KEY}

resources:
  jobs:
    type: queue
    external: true                # required: pskit does not create queues on Tencent
    name: orders-jobs
    connection:
      region: ap-guangzhou
      secret_id_env: TDMQ_SECRET_ID
      secret_key_env: TDMQ_SECRET_KEY

functions:
  api:
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```

## 4. Use it in a handler

`requirements.txt`: `tencentcloud-sdk-python-tdmq` (or the full `tencentcloud-sdk-python`)

```python
import json

from tencentcloud.common import credential
from tencentcloud.tdmq.v20200217 import models, tdmq_client
from py_serverless_kit import resource


def submit(event, ctx):
    jobs = resource("jobs")
    cred = credential.Credential(ctx.env[jobs["secret_id_env"]], ctx.env[jobs["secret_key_env"]])
    client = tdmq_client.TdmqClient(cred, jobs["region"])
    req = models.SendCmqMsgRequest()
    req.QueueName = jobs.native_name
    req.MsgContent = json.dumps(event.http.json())
    req.DelaySeconds = 0
    client.SendCmqMsg(req)
    return {"queued": True}
```

`SendCmqMsg` is a management API (rate-limited). For high throughput, and for receiving and deleting messages, use the
TDMQ CMQ data-plane client described in the TDMQ for CMQ documentation, with the access address from step 2.

## 5. Test

```bash
pskit validate
pskit deploy
pskit resources send --list       # the PSKIT_RESOURCE_* variables for jobs
```

Console: the queue → **Send Message** / **Receive Message** (labels depend on the console version) to check that
messages arrive.

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `queue` events in pskit`` (validate) | expected: Tencent has no queue trigger in pskit; use the SDK |
| `managed queue resources that no event uses are not supported` | set `external: true` |
| `AuthFailure` | wrong SecretId / SecretKey, or the sub-user lacks TDMQ permissions |
| `ResourceNotFound` | queue name or region differs from the console |
