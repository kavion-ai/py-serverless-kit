# IBM MQ queue (`type: queue`)

Send messages to (or read them from) a queue on an IBM MQ queue manager from a handler. **Not supported on IBM Cloud:** `queue` triggers. pskit can't make a Code Engine function run for each message. Options: - consume from the on-premises host with a `custom` driver class (IBM MQ or Event Streams), - or read messages inside an HTTP function that something calls (a scheduler outside pskit, a cron job). For Kafka-style messaging, Event Streams is usually simpler to reach from Python.
## 1. Create the queue manager and queue (console) 1. Console → **Catalog** →

**MQ** → plan → **Create**. 2. In the service → **Queue managers** → **Create** → name, location, size → **Create** (it takes a few minutes). 3. Open the queue manager → **Administration** → **Launch MQ Console** → **Create** a local queue (for example `ORDERS.JOBS`; MQ names are case-sensitive). 4. Back in the service → **User credentials** / **Application credentials** → **Add** an application user and **Generate API key**. Give it access to the queue (the default `DEV.*`/app channel setup varies by plan; check the queue manager's *Configuration* if you get `MQRC_NOT_AUTHORIZED`).
## 2. Collect the values | Value | Where in the console | Example | |---|---|---|

| Queue manager name | service → **Queue managers** | `QM1` | | Queue name | MQ Console → **Queues** | `ORDERS.JOBS` | | Host / port / channel | queue manager → **Connection information** (download the JSON) | `qm1-xxxx.qm.us-south.mq.appdomain.cloud`, `31175`, `CLOUD.APP.SVRCONN` | | REST endpoint | queue manager → **Administration** → *MQ Console / REST URL* | `https://web-qm1-xxxx.qm.us-south.mq.appdomain.cloud` | | Application user / API key | service → **Application credentials** | `orders-app` / `...` |
## 4. Use it in a handler

The MQ messaging REST API needs no native client library, which keeps the bundle small (`pymqi` needs the IBM MQ C client installed, which Code Engine functions don't have). `requirements.txt`: `requests` A `DELETE` on the same URL reads (destructively gets) one message.
## 5. Test MQ Console → **Queues** → `ORDERS.JOBS` shows the queue depth and lets you

browse messages.

```bash
export MQ_APP_KEY='...'
```
