## Create one and put projects on it A project names it in `pskit.yml`; every `pskit

deploy` updates its route and `pskit remove` drops it: The path prefix is removed before the request reaches your functions (`/shop/orders` arrives as `/orders`) and
sent in `X-Forwarded-Prefix: /shop`. `/shop` redirects to `/shop/`.

A **cluster** can be attached instead; every deployment on it gets `/<service>/` (or `/<service>-<stage>/` when
two stages of a service share the cluster), kept up to date on deploy, remove, join and leave: A project's own `balancer` setting wins over the cluster's route for that deployment. A project whose
placement groups run on several attached clusters gets one route, `/<service>/`, to the servers of
all of them; each server passes another group's routes on to it.

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
