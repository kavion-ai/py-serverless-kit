# Concept: deployment.json

After Terraform, `core/describe.py` writes `.pskit/<provider>-<stage>/deployment.json`. The constant is `RECORD_FILE`. `build_record` reads the config and the Terraform output named `pskit`. `pskit info --json` prints the same record. The dashboard reads every `.pskit/*/deployment.json`.

The record has `schema` 1 and `key` `<provider>-<stage>`. `status` passed into `build_record` defaults to `deployed`. `pskit remove` sets that file's status to `removed`. When nothing is deployed, `pskit dashboard` renders the configured functions as a `local` record. Other fields are `service`, `stage`, `provider`, `provider_display`, `provider_tier`, `region`, `endpoint` from the pskit output, `deployed_at` as a UTC timestamp, `pskit_version`, `config_file`, `artifact`, `functions`, `workflows`, `resources`, and `outputs`. `outputs` is every Terraform output except the `pskit` key.

Each function row includes the logical name, the cloud `resource_name`, handler, kind, runtime, memory, timeout, architecture, event summaries, `environment_keys`, and id, arn, url, and console when the output has them. A workflow row stores the engine, `start_at`, each state's type, the task function names, and id, url, and console. Resource rows store the key, type, whether it is external, the native name, bound functions, and `connection_keys` only. `resource_records` does not copy connection values, because they may hold secrets.

Sources: `src/py_serverless_kit/core/describe.py`, `src/py_serverless_kit/core/deployer.py`, `docs/dashboard.md#where-the-data-comes-from`, `docs/architecture.md#deploy-pipeline`
