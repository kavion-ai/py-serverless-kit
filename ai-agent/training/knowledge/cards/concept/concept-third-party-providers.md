# Concept: third-party providers

A provider subclasses `py_serverless_kit.providers.base.Provider`. The architecture example sets `name`, `display_name`, `tier = "experimental"`, `terraform_source`, `terraform_version`, `default_region`, `capabilities` such as HTTP and SCHEDULE, `runtimes`, and `max_timeout`. It implements `shim_files` and `render_resources`. `render_resources` adds resources to a `TerraformDoc` and emits `output "pskit"` shaped `{functions: {name: {id, url}}, workflows: {}, endpoint}`. Every built-in provider emits that output so `pskit info` and the dashboard stay provider-agnostic.

Register the class from your own package. The entry-point group is `py_serverless_kit.providers`:

```text
[project.entry-points."py_serverless_kit.providers"]
mycloud = "pskit_mycloud:MyCloudProvider"
```

`pskit providers` lists entry-point providers. `provider: {name: mycloud}` or `--provider mycloud` selects one. The loader accepts every built-in name plus every registered plug-in. The adapter should turn the native event into an `Event`, call `py_serverless_kit.runtime.dispatch.execute`, and turn the result back into the native response. The doc points the rest of the checklist at `deploy_docs/CONTRIBUTING.md`.

New built-in providers also start at tier `experimental` until they have been deployed, as CLAUDE.md states. A plug-in does not require a change inside pskit.

Sources: `docs/architecture.md#third-party-providers`, `CLAUDE.md`
