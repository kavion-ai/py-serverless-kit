## In studio
1. Open Resources and add a server, then save and test.

## In the terminal
1. Run:

```
pskit resources onprem servers add app-1 --ssh deploy@192.0.2.10
```

## In code

Name the server, set the host, the SSH user, and the login method. The studio button is Save and test.

## 2. Saving a server (`pskit resources onprem servers add`, studio "Add server")

| | From | To | Port |
|---|---|---|---|
| 🟥 | Admin machine | the new server | **TCP *22*** |

Nothing else; "Test" only uses SSH.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
