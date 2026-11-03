## Installation and tooling

Run `pskit doctor` (or `pskit doctor -p <provider>`) first: it reports missing tools, credentials and provider
options with the install steps for your OS.

**`Neither terraform nor tofu was found on PATH`**
: Install Terraform ≥ 1.5 or OpenTofu, or point `PSKIT_TERRAFORM_BIN` (or `provider.terraform.binary`) at the binary.

**`pip install failed while vendoring dependencies`**
: For vendoring providers (aws, alibaba, ibm, digitalocean, tencent, huawei), pskit downloads **Linux** wheels (`manylinux2014_<arch>`, `--only-binary=:all:`) for the target Python version. A package with no such wheel fails. Fixes:
  - pin a version that publishes manylinux wheels;
  - add flags with `package.pip_args`;
  - for pure-Python packages, check that they ship a wheel at all.

  `pskit package --skip-deps` lets you test packaging without dependencies.

**Paths too long on Windows** (`FileNotFoundError` / `[WinError 206]` while building, or while unpacking a bundled CPython for an on-premises deploy)
: Some providers copy the bundle into nested folders (DigitalOcean especially). Enable long paths, either with `git config --system core.longpaths true` for git, or system-wide with: Or keep the project in a short path such as `C:\src\app`.
