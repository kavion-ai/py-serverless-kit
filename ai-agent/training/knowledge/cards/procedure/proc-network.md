## In studio
1. Open Network map in the left navigation.

## In the terminal
1. Run:

```
pskit firewall
```

## In code

The network page shows how saved servers, clusters, load balancers, and services connect. pskit firewall prints the ports each server must open.

# Network and firewall rules (on premises)

Which machine must accept **inbound connections, and which must be allowed **outbound**, at each step: saving servers, deploying, running, clusters, joining servers, load balancers, function groups on several servers, and resources / triggers. Ports in *italics* are defaults you can change.

Run pskit validate after you edit pskit.yml and before you deploy. The studio keeps the in-memory draft until you save. pskit plan writes the Terraform JSON for the stage so you can read it before apply.

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
