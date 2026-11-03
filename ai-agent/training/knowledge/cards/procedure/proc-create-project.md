## In studio
1. Open the new project screen when the folder has no pskit.yml.
2. Open this path:
Functions > + Create function

## In the terminal
1. Run:

```
pskit init my-service --provider aws
```

2. Run:

```
pskit validate
```

## In code

service is required and is 2 to 32 characters, starting with a letter. provider.name is required. A function needs a handler.

## Top level | Key |

Type | Default | Rules | |---|---|---|---| | `service` | string | — | 2–32 chars, lowercase letters, digits, `-`, starts with a letter | | `provider` | mapping or string | — | `provider: aws` is shorthand for `provider: {name: aws}` | | `package` | mapping | see package | | | `functions` | map name → function | `{}` | names: start

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
