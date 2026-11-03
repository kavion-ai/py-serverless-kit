# Tencent Cloud TDMQ for CMQ topic (`type: topic`)

Publish to a topic from your functions. Tencent's original CMQ topics have moved to **TDMQ for CMQ**.

> **No topic trigger on Tencent Cloud.** pskit's Tencent provider has no `topic` event: `pskit validate` rejects
> `- topic: ...` there. Declare the topic as an external resource and publish with the Tencent Cloud SDK. Subscribers
> (queues, HTTP endpoints) are configured on the topic in the console.

## 1. Create the topic (console)

1. Console → **TDMQ** → **CMQ** → **Topic Subscription** (the exact label can differ by console version) → pick the
   region → **Create**.
2. Name (for example `order-events`) → **Submit**.
3. Optional: open the topic → **Subscription** → **Create** to deliver its messages to a queue or an HTTP endpoint
   (for example the URL of a pskit `http` function from `pskit info`).

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | TDMQ for CMQ → topic list | `order-events` |
| Region | the region selector | `ap-guangzhou` |
| SecretId / SecretKey | CAM sub-user with a TDMQ policy | `AKID...` |

## 4. Use it in a handler

`requirements.txt`: `tencentcloud-sdk-python-tdmq`

## 5. Test

Console: the topic → **Publish Message** (label depends on the console version).

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `topic` events in pskit`` (validate) | expected: publish with the SDK and subscribe via the console |
| `AuthFailure` | wrong keys, or the sub-user lacks TDMQ permissions |
| HTTP subscription doesn't reach `receive` | check the URL from `pskit info` and the subscription's push settings |

```bash
export TDMQ_SECRET_ID=AKID...
export TDMQ_SECRET_KEY=...
```
