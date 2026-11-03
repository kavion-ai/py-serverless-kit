```yaml
provider:
  name: onprem
  region: local
  options:
    host: 127.0.0.1          # bind address on the *target*. 0.0.0.0 is advertised as 127.0.0.1 unless advertise is set
    port: 8080               # 1-65535. Give each service its own port
    advertise: https://fn.internal.example   # optional URL written into outputs
    data_dir: .pskit/onprem-data             # default .pskit/onprem-data/<service>-<stage> (local); <path>/data on SSH
    poll_seconds: 0.5
    admin_token: "${env:PSKIT_ADMIN_TOKEN, }"  # header x-pskit-token on /__pskit/* except health
    env_file: .env.onprem      # KEY=VALUE secrets copied next to the host (host.env) and loaded at start;
                               # read by <name>_env driver options and handlers, never written to Terraform state
    execution_retention: 500   # finished workflow executions kept under <data_dir>/executions
    workflow_workers: 8        # workflow runs executing at once; further starts wait for a worker
    log_buffer: 5000           # log entries kept in memory for /__pskit/logs (min 100)
    log_level: INFO            # minimum level captured from `logging`
    capture_output: true       # also record print() / stdout / stderr lines
    services:
```

pskit validate checks the project before Terraform runs. The generated file is main.tf.json under .pskit/provider-stage. Handlers stay on Python 3.9 and the copied runtime uses only the standard library.
