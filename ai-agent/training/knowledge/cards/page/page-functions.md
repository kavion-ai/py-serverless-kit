# Studio: Functions

How to open: Left navigation label Functions. A count badge on that item is the number of functions (`countFor` in App.tsx). Test and Code on a row open the Test and Code pages for that function.

What it is for: A table of functions plus the create-function flow. docs/studio.md describes a four-step Create function wizard: basics, triggers, environment and permissions, review (a YAML diff). Trigger types the selected provider cannot run are disabled, with a tooltip naming the providers that can. Creating a function writes a handler stub into the project.

What you see: The page header is the functions list. The button + Create function opens the wizard. A row action Own folder shows Moving… while a split runs. Wizard section Basics. Section Add a trigger. Section Logging, hint "log level and live logs". Section Environment variables, hint "merged over the provider-wide ones". Section Concurrency & tags, with Add tag. Section Provider-specific options, hint functions.<name>.options. Section Permissions (IAM), hint advanced. Section Changes to pskit.yml. If the route names a function that is not in the draft, the header is "Function not found".

What you can do: Own folder is the studio control for giving a function its own directory. Delete asks "Delete function <name>?" The confirm body says the function and its triggers are removed from pskit.yml and the handler code is not deleted. The toast after confirm says the delete is not saved yet, because the change is in the draft until the top bar saves. The matching CLI for Own folder is:

```
pskit function split
```

The wizard review shows the YAML diff before the function is written into the draft. docs/studio.md says HTTP has a path-parameter preview, CORS and auth, and schedule has rate presets and a cron editor with a plain-English preview. Queue, storage and topic can be new, a resource from the Resources page, Browse account, or a typed name. Delete on a workflow is a different page. On this page, deleting a function removes it from the draft. Save in the top bar writes pskit.yml.

Tips and limits: Provider-specific options and IAM statements are per function. Environment variables here are merged over the provider-wide ones from Overview & provider. Disabled trigger types stay visible with the reason, rather than being omitted, which is what docs/studio.md describes under provider differences.

Sources: `dashboard-ui/src/studio/views/Functions.tsx`, `docs/studio.md#what-you-can-do`
