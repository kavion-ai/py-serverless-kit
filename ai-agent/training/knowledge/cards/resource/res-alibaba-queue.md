# Alibaba Cloud SMQ / MNS queue (`type: queue`)

Use a Simple Message Queue (SMQ, formerly Message Service / MNS) queue from your functions.

> **No queue trigger on Alibaba Cloud.** pskit's Alibaba provider has no `queue` event: `pskit validate` rejects
> `- queue: ...` there. Declare the queue as an external resource and send / receive with the MNS SDK, for example
> from a `schedule` function that drains it. Need push delivery? Publish to an MNS **topic** instead and use a
> topic trigger.

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

## 4. Use it in a handler

`requirements.txt`: `aliyun-mns-sdk`

Messages that aren't deleted become visible again after the queue's visibility timeout.

## 5. Test

Console: SMQ → **Queues** → `orders-jobs` → **Send Messages** / **Receive Messages**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| ``does not support `queue` events in pskit`` (validate) | expected: Alibaba has no queue trigger; use the SDK or a topic |
| `managed queue resources that no event uses are not supported` | set `external: true` |
| `AccessDenied` / `InvalidAccessKeyId` | check the RAM user's policy and the key pair |
| Messages processed twice | delete each message after handling it, and keep processing shorter than the visibility timeout |

```bash
export MNS_ACCESS_KEY_ID=LTAI...
export MNS_ACCESS_KEY_SECRET=...
```
