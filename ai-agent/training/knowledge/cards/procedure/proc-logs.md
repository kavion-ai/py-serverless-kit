## In studio
1. Open this path:
Logs > Stored logs

## In the terminal
1. Run:

```
pskit logs -f --function worker
```

2. Run:

```
pskit logs --streams
```

## In code

pskit logs reads the deployment logs. -f follows. --function limits the stream. --streams lists streams.

## HTTP **CORS errors in the browser** : Add `cors: true` (or a `cors:` mapping)

to the route. With `allow_credentials: true` the runtime echoes the request's `Origin` instead of `*`, so list explicit `origins` to restrict who may call. Preflights are answered by the runtime (and by API Gateway on AWS). **405 Method Not Allowed** : The path matched a route but not the method.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
