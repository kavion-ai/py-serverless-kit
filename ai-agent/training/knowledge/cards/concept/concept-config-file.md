# Concept: the pskit.yml file

pskit looks for `pskit.yml`, `pskit.yaml`, `serverless_kit.yml`, or `serverless_kit.yaml` in the current directory. Pass `-c FILE` to use another file. Unknown keys are rejected, so a typo fails fast.

The documented top-level keys are `service` (required), `provider` (required), `package`, `functions`, `workflows`, `resources`, `hooks`, `custom`, `providers`, `stages`, and `extends`. `service` is a string of 2–32 characters: lowercase letters, digits, and `-`, starting with a letter. `provider` may be a mapping or the shorthand string `provider: aws`, which means `provider: {name: aws}`.

`functions` maps a name to a function. Names start with a letter and use letters, digits, `-`, and `_`, with a maximum of 63 characters. `workflows` and `resources` are maps and default to empty. `hooks` maps a hook name to a list of shell commands. `custom` is any mapping and exists so `${self:custom...}` can read it. `providers` and `stages` hold overrides. `extends` names another file to inherit.

`package` has its own section. Deployed function names are built later as `<service>-<stage>-<function>`, lowercased, with invalid characters replaced and long names shortened with a stable hash.

Sources: `docs/configuration.md#configuration-reference-pskityml`, `docs/configuration.md#top-level`

```text
service: orders                 # required
provider:                       # required
  name: aws
  region: us-east-1
package: {...}
functions: {...}
workflows: {...}
hooks: {...}
custom: {...}                   # free-form values for ${self:custom.x}
providers: {...}                # per-cloud overrides (see below)
stages: {...}                   # per-stage overrides (see below)
extends: base.yml               # inherit another file (see below)
```
