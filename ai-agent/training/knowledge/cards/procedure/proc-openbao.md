## In studio
1. Open this path:
Resources > + On-prem service

## In the terminal
1. Run:

```
pskit resources onprem create secrets --service openbao
```

## In code

OpenBao speaks the Vault API. The secretsmanager catalog id is pskit's AWS Secrets Manager compatible server. Handlers call get_secret.

# Secret managers on premises

Keep API keys, database passwords and certificates in a secret manager instead of files, and read them from handlers with **one call that works on every provider**: No extra library: the calls are part of the pskit runtime (Python standard library, Node.js built-ins). Values are cached for 60 seconds per function instance.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
