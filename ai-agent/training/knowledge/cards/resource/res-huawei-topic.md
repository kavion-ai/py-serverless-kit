# Huawei SMN topic (`type: topic`)

Use a Simple Message Notification (SMN) topic you created in the console: pskit adds a FunctionGraph SMN trigger so
every published message runs the function, and handlers can publish to it.

## 1. Create the topic (console)

1. Console → **Simple Message Notification** → **Topic Management → Topics** → **Create Topic**.
2. Topic name (letters, digits, `-`, `_`; for example `order-events`), optional display name → **OK**.

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Topic name | SMN → **Topics** → *Topic Name* | `order-events` |
| Topic URN | SMN → **Topics** → *Topic URN* column | `urn:smn:cn-north-4:0a1b2c...:order-events` |
| Region | console header | `cn-north-4` |
| Project ID | **My Credentials → API Credentials** | `0a1b2c...` |

## 3. Declare it in `pskit.yml`

- For an external topic pskit looks it up by name (`huaweicloud_smn_topics` data source) and adds the trigger. The
  topic must be in `provider.region`.
- `topic.filter` is not supported on Huawei.

## 4. Use it in a handler

`requirements.txt`: `huaweicloudsdksmn`

## 5. Test

Console: SMN → **Topics** → topic → **Publish Message**. FunctionGraph → `notify` → **Triggers** lists the SMN trigger.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails: topic not found | name or region differs; SMN topic names are case-sensitive |
| Publishing returns 403 | the agency lacks SMN permissions |

```text
service: orders

provider:
  name: huawei
  region: cn-north-4
  iam:
    role: pskit-functions             # agency with SMN permissions, needed to publish

resources:
  order-events:
    type: topic
    external: true
    name: order-events
    connection:
      urn: urn:smn:cn-north-4:0a1b2c3d4e5f:order-events
      project_id: 0a1b2c3d4e5f

functions:
  notify:
    handler: app.handlers.notify
    events:
      - topic: {resource: order-events}
```
