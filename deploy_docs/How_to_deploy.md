# How to deploy py-serverless-kit to PyPI

This guide publishes **py-serverless-kit** as a public Python package so anyone can install it with:

```bash
pip install py-serverless-kit
pip install py-serverless-kit[aws]     # adds boto3, used by invoke() on AWS
```

| | |
|---|---|
| PyPI name | `py-serverless-kit` |
| Import name | `py_serverless_kit` |
| CLI | `pskit` (alias `py-serverless-kit`) |
| Author | Asif Khan @ Kavion.ai |

For the full maintainer guide (troubleshooting table, security notes), see [PUBLISHING_TO_PYPI.md](PUBLISHING_TO_PYPI.md).

> **Windows PowerShell 5.1:** `&&` and `rm -rf` don't work there. Run commands one per line, or use the PowerShell blocks below. (PowerShell 7+ supports `&&`.)
>
> **Version numbers:** examples use `X.Y.Z`. Replace it with the version in `src/py_serverless_kit/_version.py`, which is `0.1.0` for the first release.

---

## 1. One-time setup

### PyPI account

1. Create an account at [https://pypi.org/account/register/](https://pypi.org/account/register/).
2. Enable 2FA (required for uploads).
3. Check the name is free: [https://pypi.org/project/py-serverless-kit/](https://pypi.org/project/py-serverless-kit/). If it is taken, change `name` in `pyproject.toml`.
4. Set up a **Trusted Publisher** (recommended, see section 6) or create an API token.

### API token (manual upload)

1. Open [https://pypi.org/manage/account/token/](https://pypi.org/manage/account/token/).
2. Token name: `py-serverless-kit-publish`.
3. Scope: entire account for the first upload, then project `py-serverless-kit` only (create a new token and delete the broad one).
4. Copy the token. It is shown only once and starts with `pypi-`.

Store it as an environment variable, never in git:

```powershell
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = "pypi-…"
```

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-…
```

### TestPyPI (optional but recommended)

TestPyPI is a **completely separate site with separate accounts and tokens**. A pypi.org token does not work there, and that mismatch is the usual cause of `403 Forbidden`.

1. Register at [https://test.pypi.org/account/register/](https://test.pypi.org/account/register/), **verify your email**, and enable 2FA.
2. Create a token at [https://test.pypi.org/manage/account/token/](https://test.pypi.org/manage/account/token/), scoped to the entire account.
3. Set it right before uploading to TestPyPI:

```powershell
$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = "pypi-…"   # the TestPyPI token, not the pypi.org one
```

Or keep both tokens in `%USERPROFILE%\.pypirc` (`~/.pypirc` on Linux/macOS) and never commit it:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-<your pypi.org token>

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-<your test.pypi.org token>
```

If `TWINE_USERNAME`/`TWINE_PASSWORD` are set, they **override** `.pypirc`. Clear them before relying on the file:

```powershell
Remove-Item Env:TWINE_USERNAME, Env:TWINE_PASSWORD -ErrorAction SilentlyContinue
```

---

## 2. Version bump

Edit **one** place: `src/py_serverless_kit/_version.py`

```python
__version__ = "0.1.1"   # the first release ships as 0.1.0; bump it for every later upload
__author__ = "Asif Khan @ Kavion.ai"
```

`pyproject.toml` reads the version from this file (`dynamic = ["version"]`), so there's nothing to keep in sync. Add an entry to `CHANGELOG.md`.

Use semantic versioning:

| Change | Version |
| --- | --- |
| Bug fix | patch (`0.1.1`) |
| New compatible feature (new provider, new event option) | minor (`0.2.0`) |
| Breaking change to `pskit.yml`, handler API or CLI | major (`1.0.0`) |

> Deployed functions bundle the runtime. If a release changes the runtime, tell users in the changelog to run `pskit deploy` again.

---

## 3. Local checks

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux / macOS
pip install -e ".[dev]"

pytest
ruff check src tests
mypy
python -m build
python -m twine check dist/*
```

`twine check` must report `PASSED` for both the wheel and the sdist.

Confirm the artifacts (the version in the file names matches `_version.py`):

```
dist/py_serverless_kit-X.Y.Z.tar.gz
dist/py_serverless_kit-X.Y.Z-py3-none-any.whl
```

**Always delete `dist/` before building**, so old versions are never uploaded by `dist/*`:

```powershell
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
python -m build
```

```bash
rm -rf dist
python -m build
```

Optional, and only if Terraform ≥ 1.5 is installed: check the generated Terraform for every provider. Without Terraform the script exits with a hint; CI runs this check on every push anyway. On-premises uses Terraform's built-in provider, so it does not download a plugin.

```bash
python scripts/validate_all_providers.py
```

---

## 4. Publish to TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

Got `403 Forbidden`? See [Troubleshooting](#11-troubleshooting).

Then install from TestPyPI in a **new venv outside the repository**. Inside the repo, Python would import your local `src/` copy instead of the uploaded package.

PowerShell:

```powershell
cd $env:TEMP
python -m venv pskit-smoke
.\pskit-smoke\Scripts\Activate.ps1
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple py-serverless-kit==X.Y.Z
python -c "import py_serverless_kit as p; print(p.__version__, p.__author__, p.__file__)"
pskit --version
pskit init smoke -t full
cd smoke
pskit validate
pskit invoke -f hello --path "/hello?name=PyPI"
deactivate
```

bash:

```bash
cd /tmp && python -m venv pskit-smoke && source pskit-smoke/bin/activate
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple py-serverless-kit==X.Y.Z
pskit --version
pskit init smoke -t full && cd smoke && pskit validate && pskit invoke -f hello
deactivate
```

`--extra-index-url` is required because TestPyPI does not host the dependencies (Pydantic, Click, PyYAML). `p.__file__` should point into the venv's `site-packages`, not into your repository.

---

## 5. Publish to PyPI (public)

```bash
python -m twine upload dist/*
```

After a few minutes:

```bash
pip index versions py-serverless-kit
pip install py-serverless-kit
```

Project page: [https://pypi.org/project/py-serverless-kit/](https://pypi.org/project/py-serverless-kit/)

---

## 6. GitHub Actions trusted publishing (recommended)

Trusted publishing avoids long-lived tokens: PyPI gives GitHub Actions a short-lived OIDC token instead.

### On PyPI (and TestPyPI)

1. Open **Your account → Publishing** (or the project → **Publishing**).
2. Add a trusted publisher:
   - Owner: `kavion-ai`
   - Repository: `py-serverless-kit`
   - Workflow name: `release.yml`
   - Environment: `pypi` (on TestPyPI: `testpypi`)
3. On GitHub, under **Settings → Environments**, create `pypi` and `testpypi`. Add required reviewers to `pypi` for a manual approval step.

### Workflow

The repository includes `.github/workflows/release.yml`. It runs when you push a version tag:

```bash
git add src/py_serverless_kit/_version.py CHANGELOG.md
git commit -m "release: X.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

The workflow:

1. fails if the tag doesn't match `__version__`;
2. runs the tests and builds the sdist and wheel, then runs `twine check`;
3. uploads to TestPyPI, then to PyPI;
4. creates a GitHub Release with the files attached.

`.github/workflows/ci.yml` runs on every push and pull request without publishing: tests on Python 3.9–3.13, ruff, mypy, `terraform validate` for every provider, and a build check.

---

## 7. What gets uploaded

The build backend is **hatchling**. These files ship in the **wheel**:

- every module under `src/py_serverless_kit/` (runtime, CLI, providers, ...)
- `dashboard/template.html`, needed by `pskit dashboard`

These ship in the **sdist** (source distribution):

- `src/`, `tests/`, `examples/`, `docs/`, `README.md`, `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `pyproject.toml`

`.venv/`, `.pskit/`, `__pycache__/`, `.env` and the other entries in `.gitignore` are excluded.

To list the wheel's contents:

```bash
python -m zipfile -l dist/py_serverless_kit-X.Y.Z-py3-none-any.whl
```

---

## 8. Optional extras

```bash
pip install py-serverless-kit[aws]   # boto3, for invoke() on AWS
pip install py-serverless-kit[dev]   # pytest, ruff, mypy, build, twine (contributors)
```

If you add a new extra, bump the **minor** version and document it in `README.md` and `CHANGELOG.md`.

---

## 9. Yank a bad release

You can't re-upload or truly delete a version on PyPI. Instead, **yank** it, so `pip install py-serverless-kit` skips it while the file stays available for anyone who pinned it:

1. Open the project on PyPI → **Manage** → the release → **Options** → **Yank**.
2. Publish a fixed patch release right away (e.g. `0.1.2`).

---

## 10. Checklist

- [ ] Tests pass (`pytest`), and `ruff check` and `mypy` are clean
- [ ] Version bumped in `src/py_serverless_kit/_version.py` (skip for the very first `0.1.0` release)
- [ ] `CHANGELOG.md` updated
- [ ] `dist/` deleted, then `python -m build` produces sdist + wheel
- [ ] `twine check dist/*` passes
- [ ] TestPyPI install works (optional)
- [ ] Uploaded to PyPI (manually or by the tag workflow)
- [ ] `pip install py-serverless-kit` works in a clean venv and `pskit --version` shows the new version
- [ ] Git tag `vX.Y.Z` pushed

---

## 11. Troubleshooting

| Error | Cause | Fix |
| --- | --- | --- |
| `403 Forbidden` from `test.pypi.org` | You're using a **pypi.org** token on TestPyPI, `TWINE_USERNAME` isn't exactly `__token__`, or your TestPyPI email isn't verified | Create a token **on test.pypi.org**, set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=<that token>`, verify your email, then retry with `--verbose` to see the server's exact message |
| `403 Forbidden` from `pypi.org` | Same mix-up the other way round, or a project-scoped token for a different project | Use a pypi.org token scoped to the entire account (first upload) or to `py-serverless-kit` |
| `400 File already exists` | That version was already uploaded (even if deleted later) | Bump `__version__`, delete `dist/`, rebuild |
| `400 The name ... is too similar to an existing project` | PyPI blocks look-alike names | Change `name` in `pyproject.toml` (e.g. `kavion-serverless-kit`); the import name can stay the same |
| `No matching distribution found for py-serverless-kit==X.Y.Z` | The upload failed, you asked for a different version, or the index hasn't refreshed yet | Check the version on the project page, wait a minute, retry |
| `The token '&&' is not a valid statement separator` | Windows PowerShell 5.1 | Run the commands one per line, or use the PowerShell blocks above |
| `Neither terraform nor tofu was found` (validate script) | Terraform isn't installed (it's only needed for this optional check) | Skip it, or install Terraform / set `PSKIT_TERRAFORM_BIN` |
| `KeyboardInterrupt` during `python -m build` | Ctrl+C was pressed while it was downloading hatchling | Run `python -m build` again |
