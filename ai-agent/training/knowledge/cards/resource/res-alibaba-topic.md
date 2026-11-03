# Alibaba Cloud SMQ / MNS topic (`type: topic`)

Use a Simple Message Queue (SMQ, formerly MNS) topic you created in the console: pskit adds an MNS topic trigger to the
function, and handlers can publish to the topic.

## 1. Create the topic (console)

1. Console → **Simple Message Queue (formerly MNS)** → pick the **same region** as `provider.region` → **Topics** →
   **Create Topic**.
2. Name (for example `order-events`) → **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | SMQ → **Topics** | `order-events` |
| Endpoint | SMQ → **Topics** → **Get Endpoint**, or the topic's details page | `https://1234567890.mns.cn-hangzhou.aliyuncs.com` |
| AccessKey (to publish) | RAM user with `AliyunMNSFullAccess` (or a custom policy on this topic) | `LTAI...` |

## 3. Declare it in `pskit.yml`

- `topic: {resource: order-events}` adds an `mns_topic` trigger on the existing topic (JSON notify format,
  `BACKOFF_RETRY`). No `alicloud_message_service_topic` is created.
- `filter` supports a single string `tag` only.
- The trigger is created for `provider.region`; the topic must be there.

## 4. Use it in a handler

`requirements.txt`: `aliyun-mns-sdk`

`record.body` is the message, `record.attributes` holds the other notification fields (`TopicName`, `MessageId`,
`PublishTime`, ...).

## 5. Test

Console: SMQ → **Topics** → `order-events` → **Publish Message** (set the tag if you used `filter.tag`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails creating the trigger, topic not found | the topic is in another region, or the name differs |
| Messages published but `notify` never runs | the message tag doesn't match `filter.tag` |
| Publishing fails with `AccessDenied` | the RAM user lacks MNS permissions |

```bash
export MNS_ACCESS_KEY_ID=LTAI...
export MNS_ACCESS_KEY_SECRET=...
```
