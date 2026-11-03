# OCI Object Storage bucket (`type: storage`)

Use a bucket you created in the console: run a function when objects are created, updated or deleted (through an OCI
Events rule), read or write objects from a handler, or both.

## 1. Create the bucket (console)

1. Console → **Storage → Object Storage & Archive Storage → Buckets** → pick the compartment → **Create Bucket**.
2. Name (for example `invoices`), *Standard* tier, and tick **Emit Object Events** → **Create**.

An existing bucket: open it → *Emit Object Events* → **Edit** → enable. Without it, the Events rule pskit creates
never fires (`pskit validate` warns about this for external buckets).

## 2. Collect the values

| Value | Where in the console | Example |
|---|---|---|
| Bucket name | **Buckets** list | `invoices` |
| Namespace | bucket details → *Namespace* | `axabc12345` |
| Compartment | bucket details → *Compartment* | `ocid1.compartment.oc1..aaaa` |
| Region | region menu | `us-ashburn-1` |

## 3. Policies

The first lets the Events service invoke functions; the second lets the functions read and write objects with
resource principals (dynamic group: see README.md).

## 4. Declare it in `pskit.yml`

- pskit creates only an `oci_events_rule` for the bucket, no bucket.
- OCI Events rules can't filter by `prefix` / `suffix`: pskit warns and you filter in the handler.

## 5. Use it in a handler

`requirements.txt`: `oci`

## 6. Test

Console: bucket → **Objects** → **Upload**. **Observability & Management → Events Service → Rules** shows the rule
pskit created.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Upload doesn't run the function | *Emit Object Events* is off, or the `cloudEvents` policy is missing |
| `NotAuthorizedOrNotFound` in the handler | dynamic group rule or `manage objects` policy missing |
| Function runs for every object | expected: filter by `record.key` in the handler |

```
Allow service cloudEvents to use functions-family in compartment <name>
Allow dynamic-group pskit-functions to manage objects in compartment <name> where target.bucket.name = 'invoices'
```
