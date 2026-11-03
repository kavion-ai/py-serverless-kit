# Studio: Browse account

How to open: The resource form and the queue, storage, and topic trigger forms open this picker. The component comment in Misc.tsx calls it "Browse account". The modal title is "Existing <noun> in <provider>", and the region is appended in parentheses when the caller passed one. The noun is "buckets" for storage and "<kind>s" otherwise.

What it is for: Pick a queue, bucket, topic, or workflow that already exists, instead of typing its name. docs/studio.md#browse-account says it runs with the credentials of the machine running studio. A missing SDK or credential shows a message, and you can still type the name.

What you see: While the request runs, the spinner is "Listing <noun>…". The component calls `api.discover(provider, kind, region)`, which the file comment says is GET /api/discover. The kind is queue, storage, topic, or workflow. If the result says listing is not supported, the empty title is "Listing isn't available here" and the body is the result reason, or "Type the name instead." A filter field placeholder is "Filter <noun>…". It matches name, id, arn, region, and detail. An empty list says "No <noun> found" and "Create one, or type a name in the form." A filter that removes every row says "No match" and "Try another filter." Each row shows the name, then the arn or id, then region and detail.

What you can do: Choosing a row calls `onPick` with that item and closes the modal. Retry on an error banner runs the request again. docs/studio.md lists what each provider can list: AWS lists SQS queues, S3 buckets, SNS topics, and Step Functions state machines, and needs `py-serverless-kit[aws]` plus AWS credentials. GCP lists Pub/Sub topics and subscriptions and Cloud Storage buckets. Azure lists storage queues and blob containers. On premises lists existing queue and bucket directories under the host's data directory. The doc says other providers are not available and you type the name.

Tips and limits: The picker does not create the cloud object. Picking one fills the form so the resource or trigger can point at it. Discover uses the studio machine's credentials, not a credential stored in the browser.

Sources: `dashboard-ui/src/studio/components/Misc.tsx`, `docs/studio.md#browse-account`
