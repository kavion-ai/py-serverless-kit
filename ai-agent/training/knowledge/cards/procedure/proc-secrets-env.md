## In studio
1. Keep the secret out of the YAML file. Reference it as ${env:NAME}.

## In the terminal
1. Run:

```
pskit validate
```

## In code

Unresolved env:NAME fails validation unless you supply a default. On premises, provider.options.env_file ships a KEY=VALUE file as host.env.

## Variables | Syntax |

Resolves to | |---|---| | `${env:NAME}` | environment variable; error if unset | | `${env:NAME, default}` | environment variable or `default` | | `${opt:stage}` / `${opt:provider}` / `${opt:region}` | effective CLI values (`${opt:x, default}` allowed) | | `${self:dotted.path}` | any value of the merged config, e.g.

## Secrets Connection values become environment variables

. They're stored in Terraform state and, on premises, in `.pskit/onprem-<stage>/onprem_app/pskit_host.json`. Treat both as sensitive, or keep secrets out of them: - Put the **name** of a secret variable in `connection` (`password_env: ORDERS_DB_PASSWORD`) and read the secret at run time (`ctx.env[db["password_env"]]`) from the platform's secret store or function environment.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
