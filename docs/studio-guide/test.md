# Test page in studio

Search terms: test function, test event, run locally, send to cloud, pskit invoke, pskit trigger, sample payload, saved events, direct invoke, test events json, how to test, send real event

The **Test functions** page sends an event to a function: **locally** (runs the handler on this machine, like
`pskit invoke`) or to the deployed provider and stage in the top bar (a real queue message, upload, HTTP call, ...,
like `pskit trigger`). Sidebar: **Test** (▶). **Test** on a function row opens it on that function. More on testing:
[Invoke and test functions](../functions/invoke-and-test.md).

## Run a function locally from studio

The studio Test page runs a handler on this machine with a synthetic event; no cloud and no deploy are needed.

1. Open **Test**. The left list shows every function and its trigger types ("invoke only" without triggers).
2. Click a function.
3. **1. Choose the event**: click one of its triggers (HTTP, schedule, queue, storage, topic, smtp) or **Direct
   invoke** (no trigger).
4. **2. Edit the event**:
   - HTTP: **Request** with the method badge and the path including the query string, e.g. `/items/42?verbose=1`.
     Path parameters (`{id}`) need real values. GET and HEAD have no payload.
   - Others: **Payload (JSON)**. It starts from a sample for that trigger type (a storage sample matches the
     trigger's prefix and suffix; a schedule uses its own `input`).
5. **3. Run it**: click **▶ Run locally**. If `pskit.yml` has unsaved changes, studio asks **Save first?** (**Save
   and run** or **Run without saving**).
6. The result and logs appear in the console below.

From the terminal:

```bash
pskit invoke -f hello -d '{"name": "Ada"}'
pskit invoke -f get-item -t http --method GET --path '/items/42?verbose=1'
pskit invoke -f worker -t queue -d '[{"order_id": 1}]'
```

## Send a real event to the deployed function

The **☁ Send to <Provider> / <stage>** button on the Test page fires the real trigger of the deployed function
(`pskit trigger`): a queue message, an uploaded object, a topic message, an HTTP request or an invocation.

1. Deploy first ([Deploy page](deploy.md)). Until the stage is deployed from this folder, a box says only local tests
   are available.
2. Choose the event and edit it as above.
3. On premises, **Server** picks which machine to send to (default: where the stage was last deployed).
4. Click **☁ Send to <Provider> / <stage>** and confirm **Send to <Provider> / <stage>?** with **Send**. It is real:
   a storage object is uploaded to the bucket; a queue or topic message reaches every subscriber; an SMTP test mail
   runs every function attached to the server.
5. Turn on **Show the function's logs** to watch it run.

If the provider cannot send that event, the button is disabled and the reason shows under it.

```bash
pskit trigger -f worker --list                   # how to test each trigger
pskit trigger -f worker -e 0 -d '{"id": 1}'      # trigger number 0
pskit trigger -f get-item -e 0 --path /items/42
pskit trigger -f worker --direct -d '{"id": 1}'  # invoke instead of the trigger
```

## Save named test events in studio

The **Saved events** row of step 2 keeps named payloads per function and trigger, like test events in the Lambda
console. They are stored in `.pskit/studio/test-events.json`.

- **sample** restores the sample payload and path.
- Type a name (e.g. `big order`) and click **Save event**.
- Click a saved event's name to load it; ✕ deletes it.

## Read How to test this for a trigger

The **How to test this** section (closed by default) shows the same test three ways:

- **In the studio**: **Run locally**, then **Send to <provider>** after deploy with *Show the function's logs*.
- **Terminal**: the local command (`pskit invoke`), the deployed command (`pskit trigger`), the cloud's own CLI (for
  example `aws sqs send-message` or `gcloud pubsub topics publish`) and how to watch the logs, each with **Copy**.
- **<Provider> console**: click-by-click steps in the cloud console (available once deployed).

**Refresh** (top right) reloads the functions and the deployment state.

## See also

- [Invoke and test functions](../functions/invoke-and-test.md)
- [Logs page](logs.md)
- [Resources page: test a resource](resources.md#test-a-resource-in-studio)
- [Trigger guides](../triggers/README.md)
- [`pskit trigger` in the CLI reference](../cli.md#pskit-trigger)
