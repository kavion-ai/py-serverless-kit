## In studio
1. Open this path:
Deploy > Validate

2. Open this path:
Deploy > Plan

3. Open this path:
Deploy > Deploy

## In the terminal
1. Run:

```
pskit validate
```

2. Run:

```
pskit plan -s dev
```

3. Run:

```
pskit deploy -s dev
```

## In code

Deploy writes Terraform JSON under .pskit/provider-stage and runs terraform apply or tofu. Pass --confirm when you want to read the plan before apply.

## Deploy pipeline

Key properties: - **Terraform JSON, not HCL.** The generator builds Python dicts, so there's no quoting or templating to get wrong. User strings are escaped (`${` → `$${`) unless written as `${tf:...}`. - **Reproducible artifacts.** The zip is byte-identical for identical inputs. Unchanged code means an unchanged hash and no redeploy.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
