## In studio
1. Open this path:
Load balancers > + Create load balancer

## In the terminal
1. Run:

```
pskit lb create edge --server app-1 --port 80
```

2. Run:

```
pskit lb attach edge --cluster prod
```

## In code

The server must be saved, outside every cluster, and not used by another load balancer. attach adds a cluster path on that balancer.

## Create one and put projects on it A project names it in `pskit.yml`; every `pskit

deploy` updates its route and `pskit remove` drops it: The path prefix is removed before the request reaches your functions (`/shop/orders` arrives as `/orders`) and sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
