## Deploy pipeline

Key properties:

- **Terraform JSON, not HCL.** The generator builds Python dicts, so there's no quoting or templating to get wrong. User strings are escaped (`${` → `$${`) unless written as `${tf:...}`.
- **Reproducible artifacts.** The zip is byte-identical for identical inputs. Unchanged code means an unchanged hash and no redeploy.
- **One directory per provider and stage.** Each has its own Terraform workspace and state, so `aws-dev` and `gcp-prod` never interfere.
- **Every provider emits a `pskit` output** with the shape `{functions: {name: {id, arn?, url?, base_url?, console?}}, workflows: {...}, endpoint}`. `pskit info` and the dashboard use only this output, which keeps them provider-agnostic.

pskit validate checks the project before Terraform runs. The studio page for this work is listed in the left navigation.

```
pskit validate
```

```
pskit validate
```

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
