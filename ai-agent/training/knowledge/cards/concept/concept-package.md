# Concept: packaging

`package.source` defaults to `.`, the directory relative to the config whose files are bundled. `include` defaults to `["**/*"]`, using gitignore-style globs where `**` means any depth. `exclude` defaults to an empty list and is added to the built-in excludes. `requirements` defaults to `requirements.txt`. Lines that name `py-serverless-kit` are dropped because the runtime is vendored. `pip_args` defaults to an empty list of extra pip install flags. `vendor` follows the provider default. True forces `pip install` into the bundle. False ships `requirements.txt` instead.

Always excluded: `.git/**`, `.hg/**`, `.pskit/**`, `.terraform/**`, `.venv/**`, `venv/**`, `env/**`, `**/__pycache__/**`, `**/*.pyc`, `**/*.pyo`, `.pytest_cache/**`, `.mypy_cache/**`, `.ruff_cache/**`, `.idea/**`, `.vscode/**`, `node_modules/**`, `tests/**`, `dist/**`, `build/**`, `*.egg-info/**`, `**/.DS_Store`, `.env`, `.env.*`, `**/*.tfstate`, `**/*.tfstate.*`, `pskit*.yml`, `pskit*.yaml`, and `serverless_kit*.yml`.

Providers that build remotely (GCP, Azure, Oracle, Cloudflare) get a `requirements.txt` in the bundle. AWS, Alibaba, IBM, DigitalOcean, Tencent, and Huawei get dependencies pip-installed into the zip as Linux `manylinux2014` wheels for the target runtime and architecture.

Sources: `docs/configuration.md#package`
