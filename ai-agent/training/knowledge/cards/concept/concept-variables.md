# Concept: config variables

pskit resolves four variable forms in the config. `${env:NAME}` is an environment variable and is an error if unset. `${env:NAME, default}` uses `default` when it is unset. `${opt:stage}`, `${opt:provider}`, and `${opt:region}` are the effective CLI values. `${opt:x, default}` is allowed. `${self:dotted.path}` reads the merged config, for example `${self:service}` or `${self:custom.table}`. `${file(path.json)}` reads a file relative to the config. `.json` and `.yml` are parsed. Other files are stripped text.

When a value is exactly one variable, its type is kept, so `memory: ${self:custom.mem}` stays an int. Variables can nest across passes. Unresolved variables are reported together.

Two forms are not resolved by pskit and are passed through. `${tf:<terraform expression>}` becomes a live Terraform reference, for example `${tf:aws_dynamodb_table.orders.arn}` in an IAM statement or an environment value. Every other `${` in user values is escaped, so Terraform does not interpret it. Any other `${...}`, such as an IAM policy variable like `${aws:username}`, stays literal.

The doc says not to put secrets in YAML. Use `${env:...}` for CI-provided values, or reference a secret manager with `${tf:...}`.

Sources: `docs/configuration.md#variables`
