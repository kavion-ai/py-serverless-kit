# Concept: providers, stages, and extends

`providers:` holds per-cloud overrides. The block for the active provider (`provider.name` or `--provider`) is deep-merged into the config. Inside a block, ProviderConfig keys may be written directly as shorthand for `provider: {...}`: region, stage, runtime, memory, timeout, architecture, environment, tags, iam, log_retention_days, options, state, and terraform. Any top-level key can be overridden too, including `functions`.

Setting `enabled: false` on a function or workflow under one provider keeps it for the other clouds and skips it there. Replacing a function's `events` list replaces the list. It does not append. Disabled functions and workflows are warnings from `pskit validate`. A workflow that calls a disabled function is an error. The doc says studio writes these overrides from the Deploy page, a provider switch, and the function wizard.

`stages.<name>` deep-merges that stage. The example sets `provider.memory` and one function's `concurrency` for prod. `extends` is one file or a list. Relative paths resolve from the extending file. A circular extends is an error.

Precedence, later wins: for each file in the extends chain, parents first, that file's own values, then that file's `providers.<active>` block, so a child's explicit values beat a parent's per-provider overrides. Then `stages.<active>` across all files, child wins. Then `stages.<active>.providers.<active>`. Then CLI flags `--provider`, `--stage`, and `--region`. Dicts are deep-merged. Lists are replaced.

Sources: `docs/configuration.md#providers-per-cloud-overrides`, `docs/configuration.md#stages-per-stage-overrides`, `docs/configuration.md#extends-inherit-files`, `docs/configuration.md#precedence-later-wins`

```text
provider:
  name: aws
  region: us-east-1
providers:
  gcp:
    region: europe-west1            # shorthand for provider.region
    options: {project: my-proj}     # shorthand for provider.options
  azure:
    region: westeurope
    functions:                      # any top-level key can be overridden too
      create-order: {memory: 1024}
```
