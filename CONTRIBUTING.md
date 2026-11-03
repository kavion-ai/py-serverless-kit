# Contributing

The full contributor guide lives in [deploy_docs/CONTRIBUTING.md](deploy_docs/CONTRIBUTING.md). It covers the project layout, dev setup, how to add providers and options, and how to verify Terraform.

Quick start:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest && ruff check src tests && mypy
```
