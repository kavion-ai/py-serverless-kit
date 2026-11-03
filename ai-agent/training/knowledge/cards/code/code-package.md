# Code: Package entry points

The deploy pipeline in the architecture doc is pskit.yml, then the config loader, the schema, the project, provider validate, the packaging builder, provider render to main.tf.json, the Terraform runner, deployment.json, and the dashboard. The runtime path is platform, shim, adapter, dispatch.execute, handler. runtime/ is stdlib-only and stays on Python 3.9. Terraform is built as Python dicts. Zip artifacts are byte-reproducible.

`src/py_serverless_kit/__init__.py`: py_serverless_kit - write a Python function once, deploy it to any cloud. src/py_serverless_kit/__main__.py has no module docstring. src/py_serverless_kit/_version.py has no module docstring. `src/py_serverless_kit/client.py`: Use an on-premises pskit host from any Python program (standard library only).

Studio pages and the pskit command line both call this package. pskit validate loads the schema before a provider renders main.tf.json. The runtime that is copied into a bundle stays on the standard library and on Python 3.9. Generated zip files sort their entries and use fixed timestamps so unchanged inputs hash the same way. Handlers stay the same across providers. Provider-specific behavior belongs in options and in the provider module.
