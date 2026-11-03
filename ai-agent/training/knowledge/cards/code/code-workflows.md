# Code: Workflow compilers

The deploy pipeline in the architecture doc is pskit.yml, then the config loader, the schema, the project, provider validate, the packaging builder, provider render to main.tf.json, the Terraform runner, deployment.json, and the dashboard. The runtime path is platform, shim, adapter, dispatch.execute, handler. runtime/ is stdlib-only and stays on Python 3.9. Terraform is built as Python dicts. Zip artifacts are byte-reproducible.

`src/py_serverless_kit/workflows/__init__.py`: Workflow (state machine) compilers. `src/py_serverless_kit/workflows/asl.py`: Compile a portable workflow definition to Amazon States Language. `src/py_serverless_kit/workflows/azure_logic.py`: Compile a portable workflow definition to an Azure Logic Apps (Consumption) definition. `src/py_serverless_kit/workflows/gcp.py`: Compile a portable workflow definition to Google Cloud Workflows (JSON syntax).

Studio pages and the pskit command line both call this package. pskit validate loads the schema before a provider renders main.tf.json. The runtime that is copied into a bundle stays on the standard library and on Python 3.9. Generated zip files sort their entries and use fixed timestamps so unchanged inputs hash the same way. Handlers stay the same across providers. Provider-specific behavior belongs in options and in the provider module.
