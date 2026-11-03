## 9. The studio and browser terminals

The studio listens on `127.0.0.1` of the admin machine, and browser terminals (ttyd) on `127.0.0.1:7681+`: no
firewall change; they reach servers over SSH.

---

These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.

```
pskit validate
pskit resources onprem catalog
```

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
