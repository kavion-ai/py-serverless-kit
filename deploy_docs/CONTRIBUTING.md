# Contributing to py-serverless-kit

Thanks for helping! This guide explains how the project is organised, how to set up a dev environment, the rules every change has to follow, and step-by-step recipes for the most common contributions: a new event option, a new cloud provider, docs and examples.

## Ground rules

1. **Handler code must never need to change between clouds.** Every feature is designed around this promise. If something can't be portable, it goes under a provider's `options:` and is documented as provider-specific.
2. **The runtime is standard-library only and Python 3.9 compatible.** Everything in `src/py_serverless_kit/runtime/` is copied into every deployment bundle and runs on clouds we don't control. No third-party imports, no `match` statements, and no `X | Y` type syntax evaluated at runtime. `tests/test_packaging.py::test_vendored_runtime_is_stdlib_only` enforces this.
3. **Generated Terraform must be real.** Never guess a resource type or argument. Validate with `terraform validate` against the actual provider plugin (see *Verifying Terraform* below).
4. **Be honest about limits.** If a provider can't do something, raise a clear validation `Issue` and document it. Don't silently skip it.
5. **Tests come with every change.** Bug fixes need a regression test.

## Project layout

```
src/py_serverless_kit/
  runtime/            # shipped inside every function bundle (stdlib only)
    event.py          #   Event / HttpRequest / Record / Headers
    response.py       #   Response + coercion of handler return values
    context.py        #   Context (request id, logger, remaining time)
    dispatch.py       #   calls the user handler: routing, CORS, error mapping
    workflow.py       #   embedded state-machine engine
    invoke.py         #   portable function-to-function invoke()
    adapters/<cloud>.py  # native event/response <-> portable model
  config/             # pskit.yml schema (pydantic) + loader (extends, overrides, variables)
  providers/          # one Terraform renderer per cloud + base class + registry
  workflows/          # compilers: ASL (AWS Step Functions), Google Cloud Workflows
  packaging/          # deterministic zip builder
  terraform/          # terraform/tofu subprocess wrapper
  core/               # Project (config + provider), Deployer, deployment record
  local/              # LocalRunner (invoke/workflows) + `pskit dev` server
  dashboard/          # static HTML dashboard generator
  cli/                # click CLI + `pskit init` templates
tests/                # mirrors the package layout
examples/             # runnable scenario projects (tested by tests/test_examples.py)
docs/                 # user documentation
deploy_docs/          # maintainer docs (publishing, contributing)
```

### How a deploy flows through the code

```
pskit deploy
  -> config.loader.load_config       read YAML, extends, providers:/stages: overrides, ${...} variables
  -> core.project.Project            pick provider, add embedded-workflow orchestrator functions
  -> Provider.validate               capability / limit checks -> Issues
  -> packaging.build_artifact        sources + vendored runtime + manifest + provider shim -> artifact.zip
  -> Provider.render                 TerraformDoc -> .pskit/<provider>-<stage>/main.tf.json
  -> terraform init/apply            TerraformRunner
  -> core.describe.build_record      terraform outputs -> deployment.json
  -> dashboard.write_dashboard       .pskit/dashboard/index.html
```

At runtime in the cloud:

```
platform -> shim (e.g. pskit_entry.handler) -> runtime.adapters.<cloud> -> runtime.dispatch.execute -> your handler
```

## Development setup

```bash
git clone https://github.com/kavion-ai/py-serverless-kit.git
cd py-serverless-kit
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                             # whole suite, no cloud access needed
ruff check src tests
mypy
```

Optional tools:

- **Terraform ≥ 1.5** or **OpenTofu**, for `terraform validate` and real deploys.
- Cloud CLIs/credentials, only if you want to run a real deploy of the examples.

## Workflow

1. Open an issue first for anything non-trivial (new provider, config changes) so we can agree on the design.
2. Fork and branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
3. Keep PRs focused. One provider or one feature per PR.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) messages: `feat(gcp): support Cloud Tasks queues`, `fix(runtime): keep multi-value headers`.
5. Add an entry under **Unreleased** in `CHANGELOG.md`.
6. Make sure CI is green: tests on Python 3.9 to 3.13, ruff, mypy, and `terraform validate` for every provider.
7. A maintainer reviews the PR. Expect questions about portability and failure modes.

## Recipes

### Add a new option to an existing event type

Example: `queue.max_concurrency`.

1. Add the field to the model in `config/schema.py` (with a sensible default and validation).
2. Implement it in every provider that can support it (`providers/<cloud>.py`). Where a provider can't, either ignore it with a `doc.warnings.append(...)` or return an `Issue("error", ...)` from `extra_validation` if ignoring it would be dangerous.
3. Add tests in `tests/config/test_schema.py` and the relevant `tests/providers/test_<cloud>.py`.
4. Document it in `docs/configuration.md` and, if it differs per provider, in `docs/providers.md`.

### Add a new cloud provider

1. **Research.** Find the Terraform provider and the exact resources for: a function from a zip (or image), an HTTP endpoint, and triggers. Write down the native event payload shapes and the entrypoint signature.
2. **Adapter:** create `runtime/adapters/<cloud>.py` with:
   - `to_event(native, native_ctx) -> Event`: handle HTTP, every trigger type, and `__pskit` envelopes (`adapters.base.unwrap_envelope`);
   - a function that turns the result into the native response (for HTTP use `Response.render_for_gateway()`);
   - an entrypoint that calls `runtime.dispatch.execute`.
3. **Provider:** create `providers/<cloud>.py` subclassing `providers.base.Provider`:
   - class attributes: `name`, `display_name`, `tier` (`experimental` until it has been deployed for real), `terraform_source`, `default_region`, `capabilities`, `runtimes`, `max_timeout`, `vendor_dependencies`, naming rules;
   - `shim_files()`: the files at the bundle root that the platform calls;
   - `render_resources(doc, ctx)`: emit resources, and **always** the `pskit` output (`functions`, `workflows`, `endpoint`);
   - `extra_validation()` for provider-specific limits.
4. **Register** it in `providers/registry.py` (`BUILTIN`) and add its name to `PROVIDERS` in `config/schema.py`. Third-party packages can instead register through the `py_serverless_kit.providers` entry-point group without changing this repo:

   ```toml
   [project.entry-points."py_serverless_kit.providers"]
   mycloud = "pskit_mycloud:MyCloudProvider"
   ```

5. **Tests:** `tests/providers/test_<cloud>.py` (render, outputs, validation errors) and `tests/runtime/test_adapter_<cloud>.py` (realistic native payloads, recorded from the real platform when possible).
6. **Verify Terraform** (below), then update `docs/providers.md`, the README matrix, and `cli/templates.py` (`DEFAULT_REGIONS`, `PROVIDER_OPTIONS`).

### Add an example

Create `examples/NN-name/` with `pskit.yml`, handler code and a `README.md`. `tests/test_examples.py` picks it up automatically and validates and packages it.

### Dashboard UI

The same Vite project also builds the studio (`pskit studio`): `vite.studio.config.ts` with entry `studio.html` writes `src/py_serverless_kit/studio/studio.html`. `npm run build` builds both, and `npm run dev:studio` runs it against `pskit studio --port 8770` (or `VITE_MOCK=1 npm run dev:studio` with an in-browser mock API). The Python side is `src/py_serverless_kit/studio/` and its form catalog comes from `/api/meta`, so new providers, events, drivers and options appear in the UI without UI changes.

The dashboard page is built from [`dashboard-ui/`](../dashboard-ui) (Vite + React 18 + TypeScript). The build output is committed as `src/py_serverless_kit/dashboard/template.html`, a single file with JS and CSS inline. `dashboard/generator.py` fills its `{{TITLE}}` and `{{DATA}}` placeholders.

- Never hand-edit `template.html`. Change `dashboard-ui/src/` and rebuild:

  ```bash
  cd dashboard-ui
  npm ci
  npm run build          # writes ../src/py_serverless_kit/dashboard/template.html (deterministic)
  npm run dev            # Vite dev server; proxies /api to pskit dashboard --serve on 127.0.0.1:8765
  ```

- Commit `template.html` together with the source change. The `dashboard-ui` CI job rebuilds it and fails if `git diff` shows a difference.
- Keep both placeholders verbatim and keep the page self-contained (no CDN, works from `file://`). Render user data as text only.
- Node is only needed to change the UI. Installing or using pskit never needs it: the built page ships in the wheel, and `dashboard-ui/` isn't packaged.
- The live API is `dashboard/server.py`. Its tests (`tests/test_dashboard_server.py`) mock `core.onprem_control` and `core.executions`.

## Verifying Terraform

Unit tests check the *shape* of the generated JSON. Only Terraform itself can say whether the resources and arguments exist. For any provider change:

```bash
cd examples/08-multi-cloud
pskit package --skip-deps --provider <cloud>
cd .pskit/<cloud>-dev
terraform init -backend=false
terraform validate          # must print: Success! The configuration is valid.
```

To look up a resource's exact schema:

```bash
terraform providers schema -json | python -c "import json,sys; s=json.load(sys.stdin); \
print(json.dumps(next(iter(s['provider_schemas'].values()))['resource_schemas']['aws_lambda_function'], indent=1))"
```

## Coding style

- `ruff` for linting and import order, line length 120.
- Type hints everywhere. `mypy` must pass.
- Comments explain *why*, not *what*. Match the density of the surrounding code.
- User-facing errors say what's wrong **and** how to fix it.

## Reporting bugs and security issues

- Bugs: open a GitHub issue with `pskit --version`, the provider, the relevant part of `pskit.yml` (remove secrets) and the full error.
- Security vulnerabilities: **don't** open a public issue. Follow `SECURITY.md`.

## Releasing

Maintainers: see [PUBLISHING_TO_PYPI.md](PUBLISHING_TO_PYPI.md).
