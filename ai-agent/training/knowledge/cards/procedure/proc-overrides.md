## In studio
1. Edit the YAML page and add providers or stages maps.

## In the terminal
1. Run:

```
pskit validate -p aws -s prod
```

## In code

providers.NAME and stages.NAME merge over the base file. extends inherits another file. Child values beat a parent providers block.

### Precedence (later wins) 1

. For each file in the `extends` chain, parents first: 1. that file's own values; 2. that file's `providers.<active provider>` block. So a child file's explicit values beat its parent's per-provider overrides. 2. `stages.<active stage>` (merged across all files; the child wins). 3.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
