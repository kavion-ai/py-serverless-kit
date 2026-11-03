# Publishing `py-serverless-kit` to PyPI

This guide covers every step of releasing the library: one-time account setup, building, testing on TestPyPI, publishing to PyPI (manually or from CI), and what to do when something goes wrong.

| | |
|---|---|
| Distribution name (what users `pip install`) | `py-serverless-kit` |
| Import name | `py_serverless_kit` |
| CLI entry points | `pskit`, `py-serverless-kit` |
| Build backend | [hatchling](https://hatch.pypa.io/) (configured in `pyproject.toml`) |
| Version source | `src/py_serverless_kit/_version.py` (single source of truth) |

> **Check the name first.** Before the first release, open <https://pypi.org/project/py-serverless-kit/>. If the name is already taken by someone else, change `name` in `pyproject.toml` (for example to `kavion-serverless-kit`) and update the install commands in `README.md`. The import name `py_serverless_kit` can stay the same.

---

## 1. One-time setup

### 1.1 Create the accounts

1. Create an account on **PyPI**: <https://pypi.org/account/register/>
2. Create a *separate* account on **TestPyPI**: <https://test.pypi.org/account/register/> (it is a different database).
3. Turn on **two-factor authentication** on both (PyPI requires 2FA for uploads).
4. Optional but recommended: create a PyPI **organization** for the team and add maintainers, so releases don't depend on one person.

### 1.2 Choose how you authenticate

There are two options. **Trusted Publishing is recommended**: no secrets to store or rotate.

#### Option A: Trusted Publishing from GitHub Actions (recommended)

PyPI trusts a specific GitHub workflow through OIDC, so no API token is stored anywhere.

1. Push the repository to GitHub.
2. On PyPI go to **Your account → Publishing → Add a new pending publisher** and fill in:
   - PyPI project name: `py-serverless-kit`
   - Owner: `kavion-ai`
   - Repository name: `py-serverless-kit`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. Do the same on TestPyPI with environment name `testpypi`.
4. On GitHub go to **Settings → Environments**, create the environments `pypi` and `testpypi`, and (recommended) add *required reviewers* to `pypi` so every production release needs an approval.

The workflow `.github/workflows/release.yml` in this repository is already set up for this.

#### Option B: API tokens (manual uploads from a laptop)

1. On PyPI go to **Account settings → API tokens → Add API token**. For the very first upload the scope must be "Entire account". After the project exists, create a new token scoped to `py-serverless-kit` only and delete the broad one.
2. Do the same on TestPyPI.
3. Store the tokens in `~/.pypirc` (never commit this file):

   ```ini
   [distutils]
   index-servers =
       pypi
       testpypi

   [pypi]
   username = __token__
   password = pypi-AgEIcHlwaS5vcmc...

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-AgENdGVzdC5weXBpLm9yZw...
   ```

   On Linux/macOS run `chmod 600 ~/.pypirc`. On Windows the file is `%USERPROFILE%\.pypirc`.

   Instead of the file you can set environment variables per upload: `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<token>`.

### 1.3 Install the release tooling

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"     # pytest, ruff, mypy, build, twine
```

---

## 2. Release checklist (every release)

### 2.1 Decide the version number

We follow [Semantic Versioning](https://semver.org/):

| Change | Example | Bump |
|---|---|---|
| Bug fix, no config/API change | fix CORS header on GCP | `0.1.0 → 0.1.1` |
| New feature, backwards compatible (new provider, new event option) | add Vercel provider | `0.1.1 → 0.2.0` |
| Breaking change to `pskit.yml`, the handler API or CLI flags | rename `events.queue.name` | `0.x → 1.0.0` (or minor bump while < 1.0, clearly called out) |

Pre-releases use PEP 440 suffixes: `0.2.0a1`, `0.2.0b1`, `0.2.0rc1`. `pip install py-serverless-kit` ignores them unless the user passes `--pre`.

### 2.2 Prepare the release branch

```bash
git checkout main && git pull
git checkout -b release/0.2.0
```

1. Update the version in **one place**: `src/py_serverless_kit/_version.py`

   ```python
   __version__ = "0.2.0"
   ```

2. Update `CHANGELOG.md`: move items from *Unreleased* into a new `## [0.2.0] - YYYY-MM-DD` section.
3. If the runtime contract changed (event fields, manifest format), say so explicitly in the changelog. Deployed functions bundle the runtime, so users must redeploy to pick it up.

### 2.3 Run the full quality gate locally

```bash
ruff check src tests
mypy
pytest --cov=py_serverless_kit --cov-report=term-missing
```

Optional but strongly recommended before a release that touches providers: run real `terraform validate` against every provider. This downloads provider plugins, so it needs network access.

```bash
export PSKIT_TERRAFORM_BIN=$(which terraform)   # or tofu
pytest tests/test_cli.py -k terraform_validate
python scripts/validate_all_providers.py         # renders and validates every provider
```

### 2.4 Build the distributions

```bash
rm -rf dist build            # Windows: Remove-Item -Recurse -Force dist, build
python -m build              # creates dist/*.tar.gz (sdist) and dist/*.whl (wheel)
```

Check the artifacts:

```bash
twine check --strict dist/*
```

Look inside the wheel and confirm the dashboard template and runtime are there and tests are not:

```bash
python -m zipfile -l dist/py_serverless_kit-0.2.0-py3-none-any.whl | grep -E "template.html|runtime/dispatch.py"
```

### 2.5 Smoke-test the wheel in a clean environment

Install the wheel into a fresh venv. Don't use your editable install, or you might miss a file that never made it into the wheel.

```bash
python -m venv /tmp/pskit-smoke && source /tmp/pskit-smoke/bin/activate
pip install dist/py_serverless_kit-0.2.0-py3-none-any.whl
pskit --version
cd /tmp && pskit init smoke-app --template full && cd smoke-app
pskit validate
pskit invoke -f hello --path "/hello?name=release"
pskit workflow run order-pipeline -i '{"amount": 5}'
pskit package --skip-deps && pskit dashboard
deactivate
```

### 2.6 Publish to TestPyPI first

```bash
twine upload --repository testpypi dist/*
```

Then install from TestPyPI. The extra index is needed because the dependencies (pydantic, click, PyYAML) only exist on the real PyPI.

```bash
python -m venv /tmp/pskit-test && source /tmp/pskit-test/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ \
            py-serverless-kit==0.2.0
pskit --version
```

### 2.7 Publish to PyPI

**Manual:**

```bash
twine upload dist/*
```

**From CI (recommended):** merge the release branch, then tag and push:

```bash
git checkout main && git pull
git tag -a v0.2.0 -m "py-serverless-kit 0.2.0"
git push origin v0.2.0
```

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which:

1. checks that the tag matches `__version__` (it fails fast if you forgot to bump it);
2. runs the test suite;
3. builds the sdist and wheel and runs `twine check`;
4. publishes to **TestPyPI**, then to **PyPI** (the `pypi` environment waits for approval if you configured reviewers);
5. creates a GitHub Release with the built files attached.

### 2.8 After publishing

- Check <https://pypi.org/project/py-serverless-kit/> to make sure the README renders and the metadata is right.
- Run `pip install -U py-serverless-kit` in a clean venv.
- Announce the release and link the changelog.
- Bump `main` to the next dev version if you like (e.g. `0.3.0.dev0`).

---

## 3. Things that go wrong (and fixes)

| Symptom | Cause | Fix |
|---|---|---|
| `400 File already exists` | PyPI never lets you re-upload the same version, even after deleting it | Bump the version (e.g. `0.2.1`) and rebuild. Never reuse version numbers. |
| `403 Invalid or non-existent authentication` | Wrong token, or the username isn't `__token__` | Recreate the token; username must be literally `__token__`. |
| Trusted publishing: `invalid-publisher` | Workflow file name, environment or repo doesn't match the PyPI publisher config | Make the PyPI settings match exactly: `release.yml`, environment `pypi`, owner/repo. |
| README renders as plain text on PyPI | Missing `readme`/content type | `readme = "README.md"` is in `pyproject.toml`; check `twine check --strict` passes. |
| `pskit dashboard` fails after install with "template.html not found" | Non-Python file missing from the wheel | Hatch includes package data by default; make sure `.gitignore` doesn't exclude it and recheck with `python -m zipfile -l`. |
| Users get an old runtime in their functions | They upgraded the CLI but didn't redeploy | Expected: the runtime is vendored at package time, so run `pskit deploy` again. Mention it in the changelog. |
| You published a broken release | | **Yank** it on PyPI (*Manage → Releases → Options → Yank*). Pip skips yanked versions unless they are pinned. Then publish a fixed patch version. Don't delete releases. |

---

## 4. Security notes for maintainers

- Prefer Trusted Publishing, so no long-lived token exists to leak.
- If you must use tokens, scope them to this project and rotate them yearly or whenever a maintainer leaves.
- Enable 2FA on PyPI, TestPyPI and GitHub.
- Protect the `main` branch and `v*` tags (require PR review and passing CI).
- Never build releases from a dirty working tree. CI builds from the tag, which guarantees this.
