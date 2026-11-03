# Concept: hooks

`hooks` maps a hook name to a list of shell commands. The schema allows only `before_package`, `after_package`, `before_deploy`, `after_deploy`, `before_remove`, and `after_remove`. Any other name fails validation with `unknown hooks`. An empty map is the default.

`Deployer.run_hook` prints `hook <name>: <cmd>`, then runs each command with `shell=True` in the project root. The environment is the current environment plus `PSKIT_SERVICE`, `PSKIT_STAGE`, `PSKIT_PROVIDER`, and `PSKIT_WORK_DIR`. A non-zero exit raises `DeployError` with the hook name, the return code, and the command.

`package` runs `before_package` after validation and before the artifact is built, and `after_package` after `main.tf.json` is written. `deploy` calls `package`, then `before_deploy`, then Terraform, then `after_deploy` after the deployment record is saved. `plan` calls `package`, so the package hooks run, and it does not call the deploy hooks. `remove` runs `before_remove` before init and destroy, and `after_remove` after the record is marked removed.

The documented example runs `python scripts/gen_schema.py` on `before_package` and `python scripts/smoke_test.py` on `after_deploy`. Those paths are examples, not built-in scripts. Hooks are not function events.

Sources: `docs/configuration.md#hooks`, `src/py_serverless_kit/core/deployer.py`, `src/py_serverless_kit/config/schema.py`

```text
hooks:
  before_package: ["python scripts/gen_schema.py"]
  after_deploy:   ["python scripts/smoke_test.py"]
```
