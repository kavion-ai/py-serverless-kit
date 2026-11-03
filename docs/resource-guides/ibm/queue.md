# IBM MQ queue (`type: queue`)

Send messages to (or read them from) a queue on an IBM MQ queue manager from a handler.

**Not supported on IBM Cloud:** `queue` triggers. pskit can't make a Code Engine function run for each message. Options:

- consume from the [on-premises host](../../resources.md#custom-drivers) with a `custom` driver class (IBM MQ or
  Event Streams),
- or read messages inside an HTTP function that something calls (a scheduler outside pskit, a cron job).

For Kafka-style messaging, [Event Streams](topic.md) is usually simpler to reach from Python.

## 1. Create the queue manager and queue (console)

1. Console → **Catalog** → **MQ** → plan → **Create**.
2. In the service → **Queue managers** → **Create** → name, location, size → **Create** (it takes a few minutes).
3. Open the queue manager → **Administration** → **Launch MQ Console** → **Create** a local queue (for example
   `ORDERS.JOBS`; MQ names are case-sensitive).
4. Back in the service → **User credentials** / **Application credentials** → **Add** an application user and
   **Generate API key**. Give it access to the queue (the default `DEV.*`/app channel setup varies by plan; check the
   queue manager's *Configuration* if you get `MQRC_NOT_AUTHORIZED`).

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Queue manager name | service → **Queue managers** | `QM1` |
| Queue name | MQ Console → **Queues** | `ORDERS.JOBS` |
| Host / port / channel | queue manager → **Connection information** (download the JSON) | `qm1-xxxx.qm.us-south.mq.appdomain.cloud`, `31175`, `CLOUD.APP.SVRCONN` |
| REST endpoint | queue manager → **Administration** → *MQ Console / REST URL* | `https://web-qm1-xxxx.qm.us-south.mq.appdomain.cloud` |
| Application user / API key | service → **Application credentials** | `orders-app` / `...` |

```bash
export MQ_APP_KEY='...'
```

## 3. Declare it in `pskit.yml`

```yaml
service: orders

provider:
  name: ibm
  region: us-south
  environment:
    MQ_APP_KEY: ${env:MQ_APP_KEY}

resources:
  jobs:
    type: queue
    external: true
    name: ORDERS.JOBS
    connection:
      queue_manager: QM1
      rest_url: https://web-qm1-xxxx.qm.us-south.mq.appdomain.cloud
      user: orders-app
      api_key_env: MQ_APP_KEY

functions:
  submit:
    handler: app.handlers.submit
    events: [{http: POST /jobs}]
```

## 4. Use it in a handler

The MQ messaging REST API needs no native client library, which keeps the bundle small (`pymqi` needs the IBM MQ C
client installed, which Code Engine functions don't have).

`requirements.txt`: `requests`

```python
import json

import requests
from py_serverless_kit import resource


def submit(event, ctx):
    q = resource("jobs")
    url = f'{q["rest_url"]}/ibmmq/rest/v2/messaging/qmgr/{q["queue_manager"]}/queue/{q.native_name}/message'
    resp = requests.post(
        url,
        data=json.dumps(event.http.json()),
        auth=(q["user"], ctx.env[q["api_key_env"]]),
        headers={"Content-Type": "text/plain;charset=utf-8", "ibm-mq-rest-csrf-token": "pskit"},
        timeout=10,
    )
    resp.raise_for_status()
    return {"queued": True}
```

A `DELETE` on the same URL reads (destructively gets) one message.

## 5. Test

```bash
pskit validate
pskit deploy
curl -X POST "$(pskit info --json | python -c 'import json,sys; print(json.load(sys.stdin)["functions"]["submit"]["url"])')/jobs" -d '{"id": 1}'
```

MQ Console → **Queues** → `ORDERS.JOBS` shows the queue depth and lets you browse messages.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `` IBM Cloud Code Engine does not support `queue` events in pskit `` | IBM Cloud has HTTP triggers only in pskit |
| `401` from the REST API | wrong application user / API key |
| `403` / `MQRC_NOT_AUTHORIZED` | the application user has no put/get authority on the queue |
| `404` | queue manager or queue name typo (both are case-sensitive) |
