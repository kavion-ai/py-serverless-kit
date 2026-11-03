# Tencent Cloud TDMQ for CMQ queue (`type: queue`)

Use a message queue from your functions. Tencent's original CMQ service has moved to **TDMQ for CMQ**; the console
and APIs below are TDMQ's.

> **No queue trigger on Tencent Cloud.** pskit's Tencent provider has no `queue` event: `pskit validate` rejects
> `- queue: ...` there. Declare the queue as an external resource and send to it with the Tencent Cloud SDK. To react to
> messages, consume them with the TDMQ CMQ client from a `schedule` function, or put work into a COS bucket and use a
> storage trigger.

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

## 4. Use it in a handler

`requirements.txt`: `tencentcloud-sdk-python-tdmq` (or the full `tencentcloud-sdk-python`)

`SendCmqMsg` is a management API (rate-limited). For high throughput, and for receiving and deleting messages, use the
TDMQ CMQ data-plane client described in the TDMQ for CMQ documentation, with the access address from step 2.

## 5. Test

Console: the queue → **Send Message** / **Receive Message** (labels depend on the console version) to check that
messages arrive.

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `queue` events in pskit`` (validate) | expected: Tencent has no queue trigger in pskit; use the SDK |
| `managed queue resources that no event uses are not supported` | set `external: true` |
| `AuthFailure` | wrong SecretId / SecretKey, or the sub-user lacks TDMQ permissions |
| `ResourceNotFound` | queue name or region differs from the console |

```bash
export TDMQ_SECRET_ID=AKID...
export TDMQ_SECRET_KEY=...
```
