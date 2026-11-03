## Databases: one server, or a primary with read replicas

- **Single server**: one container on this machine or a server. To scale it up, give that server more CPU and
  memory (vertical scaling). Nothing else changes.
- **Primary + read replicas** (horizontal scaling): the **primary** takes every write, each **read replica** on
  another server keeps a copy and answers reads, and an optional **load balancer** gives the functions one address
  that sends writes to the primary and reads to the replicas. Add replicas later as reads grow.

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
