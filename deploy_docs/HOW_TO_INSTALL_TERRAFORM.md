
Option 1: winget (easiest)

winget install --id Hashicorp.Terraform -e

Then close and reopen PowerShell so the updated PATH loads, and check it:

terraform -version

Option 2: Chocolatey (if you use it)

Run PowerShell as Administrator:

choco install terraform -y

Option 3: Manual (no admin rights needed)

1. Download the Windows AMD64 zip from https://developer.hashicorp.com/terraform/install.
2. Unzip it, e.g. to C:\tools\terraform\ so you have C:\tools\terraform\terraform.exe.
3. Add that folder to your user PATH:
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\tools\terraform", "User")
4. Close and reopen PowerShell, then run terraform -version.

Shortcut: if you'd rather not touch PATH, point pskit at the exe directly:

$env:PSKIT_TERRAFORM_BIN = "C:\tools\terraform\terraform.exe"

Then run the check

cd C:\Users\asif.khan\Documents\github\common_python_services\serverless_kit
.venv\Scripts\Activate.ps1
python scripts/validate_all_providers.py

The first run downloads the Terraform plugin for each cloud, which is a few hundred MB and takes a few minutes. On-premises uses Terraform's built-in provider and does not download one. You don't need cloud credentials for this check. The end of the output should say 11/11 providers valid.

To make later runs faster by reusing the downloaded plugins:

New-Item -ItemType Directory -Force $env:USERPROFILE\.terraform.d\plugin-cache | Out-Null
$env:TF_PLUGIN_CACHE_DIR = "$env:USERPROFILE\.terraform.d\plugin-cache"

Alternative: OpenTofu, the open-source Terraform fork, also works. Install it with winget install --id OpenTofu.Tofu -e; pskit finds tofu automatically.