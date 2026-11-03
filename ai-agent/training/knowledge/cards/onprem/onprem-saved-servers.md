```bash
pskit resources onprem servers add edge1 --ssh deploy@192.0.2.10 --pem ~/.ssh/edge1.pem
pskit resources onprem servers add db-box --ssh deploy@192.0.2.10              # SSH agent / default key
pskit resources onprem servers add lab --ssh deploy@192.0.2.10 --ssh-password-env LAB_PW --sudo
pskit resources onprem servers list
pskit resources onprem servers test edge1        # OS, CPU, memory, disk, Docker access, sudo, Python / Node / nginx
pskit resources onprem servers check             # ✓ / ✗: which servers answer on their SSH port (no login)
pskit resources onprem servers top edge1 --watch 5   # live CPU, memory and disk use
pskit resources onprem servers usage edge1       # where it is used: deploy, function groups, clusters, LBs, services
pskit resources onprem create cache --service redis --server edge1 --save
pskit resources onprem servers remove lab        # services there keep running
```

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
