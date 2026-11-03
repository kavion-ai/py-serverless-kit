# Cloudflare Queues (`type: queue`)

Send messages to a Cloudflare queue from a Worker, and consume them. pskit has **no queue trigger on Cloudflare**, so a
Worker can't be a push consumer. Consume with a scheduled function that pulls over HTTP, or from an on-premises host.

## 1. Create the queue (dashboard)

1. Dashboard → **Workers & Pages → Queues** (also listed under *Storage & databases*) → **Create queue**.
2. Name: lowercase letters, digits and dashes (for example `shop-jobs`) → **Create**.
3. To consume it over HTTP: queue → **Settings** (or *Consumers*) → **Add consumer** → type **HTTP pull** → set the
   visibility timeout and retries → **Add**. A queue has only one consumer.

## 2. Collect the values

| Value | Where | Example |
|---|---|---|
| Queue name | **Queues** → the list | `shop-jobs` |
| Queue ID | queue → **Settings** → *Queue ID* (or the queue's URL) | `fedcba9876543210fedcba9876543210` |
| Account ID | see README | |
| API token (pull consumer only) | **My Profile → API Tokens → Create Token** → *Custom token* → permission **Account → Queues → Edit** | |

## 4. Use it in a handler

Messages that aren't acknowledged before the visibility timeout are delivered again; after the consumer's retry limit
they go to its dead-letter queue (if you set one in the consumer settings).

**Alternative consumer:** an on-premises host with `driver: cloudflare_queue` pulls the same
queue and runs a normal `queue` event handler, with batching, retries and dead letters handled by pskit.

## 5. Test

Dashboard: queue → **Messages** → **Send message** / **List messages** (only with an HTTP pull consumer).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `does not support `queue` events` | remove the `queue:` event; consume with a `schedule` function or an on-prem host |
| `/pull` returns an error about consumers | add an **HTTP pull** consumer to the queue |
| `401` / `10000 Authentication error` on `/pull` | the token needs **Queues Edit** on that account |
| Bodies arrive base64-encoded | the producer sent the default content type; pass `{"contentType": "text"}` |

```bash
export CF_QUEUES_TOKEN=...
```
