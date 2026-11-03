# Studio: Deploy

How to open: Left navigation label Deploy.

What it is for: Run validate, package, plan, deploy, info and remove, with a live log. docs/studio.md says Remove, and any stage named `prod*`, need a typed confirmation. The same page can invoke a function with a JSON payload and run a workflow locally.

What you see: Action buttons from the list in Deploy.tsx: Validate ("Check the configuration against the provider."), Package ("Build the bundle and Terraform without deploying."), Plan ("terraform plan: what would change."), Deploy ("Build and apply."), Info ("What is deployed."), Remove ("Destroy every resource of this stage."). A switch label is either "Remove also deletes buckets, queues and topics" or "Remove keeps buckets, queues and topics (and their data)". Output tabs are Steps and Raw log. Section "Where functions run", hint provider.options.placement. Section Firewall, hint "the ports each server must allow". Section "Invoke a function locally", hint `pskit invoke`. Section "Run a workflow locally", hint `pskit workflow run --history`.

What you can do: Validate, Package, Plan, Deploy, Info and Remove start studio jobs for those commands. When the switch says remove keeps buckets, queues and topics, Remove is called with `keep_resources: true`, which is `pskit remove --keep-resources`. docs/studio.md states that flag keeps the data resources and destroys functions and triggers. Invoke on this page runs the handler locally. Run a workflow locally runs the embedded engine with history.

```
pskit plan
pskit deploy
pskit remove --keep-resources
```

Tips and limits: Deploy and Remove change the selected stage. The UI asks before remove, and docs/studio.md says a stage whose name starts with prod also needs a typed confirmation. Package does not apply. Plan shows what would change. If some functions or triggers will not run on this provider, a section lists them and can disable them under `providers.<cloud>`.

Sources: `dashboard-ui/src/studio/views/Deploy.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#project-environment-trigger-resources-and-remove`
