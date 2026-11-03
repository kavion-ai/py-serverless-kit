## In studio
1. Open this path:
Test > Run locally

## In the terminal
1. Run:

```
pskit invoke -f hello -t http --method GET --path /hello
```

2. Run:

```
pskit dev
```

## In code

pskit invoke runs one function with a synthetic event. pskit dev serves HTTP routes on this machine. Neither contacts the cloud.

# Local development All of this works without cloud credentials or Terraform

. Locally, handlers run through the **same dispatcher** as in the cloud (routing, CORS, error mapping, `BatchResult`). Only the cloud-specific adapter is skipped.
## `pskit dev`: local server

On startup it prints every route: | Endpoint | What it does | |---|---| | your `http` routes | `{id}` and `{path+}` templates; static routes win over parameterised ones; unknown paths

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.
