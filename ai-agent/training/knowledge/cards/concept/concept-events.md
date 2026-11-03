# Concept: events

Each function has a list of `events`. Each entry is a single-key mapping. The key is the trigger type. `EVENT_TYPES` in `config/schema.py` is http, schedule, queue, storage, topic, and smtp. A function with no events is invoke-only: the events doc says it can be called by workflows, by `invoke()`, or by the provider's own CLI.

The events doc's support table marks http on every provider, with a note that Huawei HTTP needs `provider.options.apig_instance_id`. Schedule is absent on Oracle and IBM. Queue is marked for AWS SQS, GCP Pub/Sub, Azure Storage Queue, and on-prem files. Storage is marked for AWS S3, GCP GCS, Azure Blob created only, Alibaba OSS, Oracle Object Storage, Tencent COS, Huawei OBS, and an on-prem directory. Topic is marked for AWS SNS, GCP Pub/Sub, Azure Service Bus, Alibaba MNS, Huawei SMN, and on-prem files. smtp is marked only for the on-prem SMTP service. `pskit validate` reports an error for a trigger or option the selected provider cannot honour.

An smtp event is written `- smtp: {resource: inbound-mail}` on the SMTP server resource. The handler gets from, to, cc, subject, text, html, headers, and attachments, plus the same mail as an Amazon SES event at `Records[0].ses`.

Sources: `docs/events.md#events-triggers`, `src/py_serverless_kit/config/schema.py`

```text
functions:
  worker:
    handler: app.jobs.process
    events:
      - http: POST /jobs
      - schedule: 15 minutes
      - queue: jobs
      - storage: uploads-bucket
      - topic: job-events
```
