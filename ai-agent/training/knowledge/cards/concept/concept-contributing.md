# Contributing to py-serverless-kit Thanks for helping!

This guide explains how the project is organised, how to set up a dev environment, the rules every change has to follow, and step-by-step recipes for the most common contributions: a new event option, a new cloud provider, docs and examples.
## Ground rules 1. **Handler code must never need to change between clouds.

Every feature is designed around this promise. If something can't be portable, it goes under a provider's `options:` and is documented as provider-specific. 2. **The runtime is standard-library only and Python 3.9 compatible.** Everything in `src/py_serverless_kit/runtime/` is copied into every deployment bundle and runs on clouds we don't control. No third-party imports, no `match` statements, and no `X | Y` type syntax evaluated at runtime. `tests/test_packaging.py::test_vendored_runtime_is_stdlib_only` enforces this. 3. **Generated Terraform must be real.** Never guess a resource type or argument. Validate with `terraform validate` against the actual provider plugin (see *Verifying Terraform* below). 4. **Be honest about limits.** If a provider can't do something, raise a clear validation `Issue` and document it. Don't silently skip it. 5. **Tests come with every change.** Bug fixes need a regression test.
## Development setup

Optional tools: - **Terraform ≥ 1.5** or **OpenTofu**, for `terraform validate` and real deploys. - Cloud CLIs/credentials, only if you want to run a real deploy of the examples.
## Workflow 1. Open an issue first for anything non-trivial (new provider, config changes)

so we can agree on the design. 2. Fork and branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`. 3. Keep PRs focused. One provider or one feature per PR. 4. Use Conventional Commits messages: `feat(gcp): support Cloud Tasks queues`, `fix(runtime): keep multi-value headers`. 5. Add an entry under **Unreleased** in `CHANGELOG.md`. 6. Make sure CI is green: tests on Python 3.9 to 3.13, ruff, mypy, and `terraform validate` for every provider. 7. A maintainer reviews the PR. Expect questions about portability and failure modes.
### Add a new option to an existing event type Example: `queue.max_concurrency`

. 1. Add the field to the model in `config/schema.py` (with a sensible default and validation). 2. Implement it in every provider that can support it (`providers/<cloud>.py`). Where a provider can't, either ignore it with a `doc.warnings.append(...)` or return an `Issue("error", ...)` from `extra_validation` if ignoring it would be dangerous. 3. Add tests in `tests/config/test_schema.py` and the relevant `tests/providers/test_<cloud>.py`. 4. Document it in `docs/configuration.md` and, if it differs per provider, in `docs/providers.md`.
