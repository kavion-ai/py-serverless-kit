# Studio: Logs

How to open: Left navigation label Logs. A function's Logging section, on the function editor, sets log level and can show that function's live logs. docs/studio.md says each function's Logging section does that.

What it is for: The page header subtitle says these are logs of the functions deployed to the provider and stage in the top bar. They are read with this machine's credentials. If they cannot be read, the subtitle links to Setup & credentials. The file comment says live tail, streams, and delete.

What you see: For an on-prem deploy that is spread across a cluster or more than one group, the page shows a Source line and does not offer a single-server picker. The comment in the file says logs then come from every replica or group. Section Stored logs, hint "list, select and delete". The component passes `api.deleteLogs` for the current provider, stage, optional function and optional server.

What you can do: Read the live tail for the top-bar target. Open Stored logs, select streams, and delete the selection or all of them. docs/studio.md says list and delete are available for AWS and on-prem, and that the page shows logs for on-prem, AWS, GCP and Azure with a Log Analytics workspace. The matching CLI is:

```
pskit logs
```

Tips and limits: Changing the top-bar provider or stage changes which deployment is read. Credentials are the ones on the machine running studio, which is why a failure points at Setup & credentials. Deleting streams is a delete call, separate from `pskit remove`. Function log level is edited on the function, not on this page.

Sources: `dashboard-ui/src/studio/views/Logs.tsx`, `docs/studio.md#setup-logs-and-provider-differences`
