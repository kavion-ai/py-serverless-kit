# Requirements and how to install them

Search terms: requirements, prerequisites, install, Python, pip, Node.js, npm, Terraform, OpenTofu, Docker, OpenSSH, Git, sshpass, cloud CLI, Windows, macOS, Linux, Ubuntu, Debian, RHEL, Fedora, Amazon Linux, WSL, arm64

You only need what your work uses. Python and Terraform cover most projects. This page lists what each task needs, then
how to install each tool on Windows, macOS and Linux.

## What you need, and when

| Tool | Version | Needed for | Not needed for |
|---|---|---|---|
| [Python and pip](#python-and-pip) | 3.9 or newer | Always: pskit itself runs on Python, also for Node.js projects | |
| [Terraform or OpenTofu](#terraform-or-opentofu) | Terraform 1.5 or newer, or OpenTofu | Plan, deploy and remove, on premises too | Studio editing, local runs and tests, validate, package |
| [Node.js and npm](#nodejs-and-npm) | 18 or newer. We suggest 22 | Node.js and TypeScript projects | Python projects |
| [Docker](#docker) | Current | One-click services on this machine, `method: docker`, cluster deploys (the image is built on your machine), Full VS Code, Hana with Docker, Oracle images | Cloud deploys in most other cases, and on-prem deploys as a local process or over SSH |
| [OpenSSH client](#openssh-client) | Current | Deploying to, or managing, your own servers | Cloud projects and this machine |
| [sshpass](#sshpass) | Current | Optional for password logins (pskit falls back to its askpass helper) | Always optional |
| [Git](#git) | Current | Sharing a team project | Working alone |
| [Cloud CLI](#cloud-clis) | Current | Signing in and looking at resources. **DigitalOcean needs `doctl` to deploy** | Other clouds can use credentials in environment variables |

Machine types:

* **This machine** (where pskit runs): Windows, macOS or Linux, on x86_64 or arm64.
* **On-prem servers:** see [Your own servers](#your-own-servers).
* **Hana** needs about 2 GB of free RAM and no GPU. The Docker image is about 4 GB, and other install options are in the
  [Hana guide](studio-guide/hana.md#install-hanas-model-from-studio).

## Check what you have

After installing pskit, it can check this machine for you and print the install steps for your system. In studio, open
**Setup & credentials**. In a terminal:

```bash
pskit doctor -p aws        # use your provider: azure, gcp, onprem, ...
```

Open a new terminal after installing anything, so the new tool is on your `PATH`.

## Package managers

These commands use each system's usual package manager.

| System | Package manager |
|---|---|
| Windows 10 and 11 | `winget`, included with the system |
| macOS, Intel or Apple silicon | [Homebrew](https://brew.sh) |
| Debian, Ubuntu | `apt` |
| RHEL, CentOS, Rocky, AlmaLinux, Fedora, Amazon Linux | `yum` or `dnf` |

**Windows Subsystem for Linux (WSL):** follow the Linux steps inside WSL. Install Docker Desktop on Windows and turn on its
WSL integration, or install Docker inside WSL.

Other Linux distributions work if they provide the versions above. Arch (`pacman`), openSUSE (`zypper`) and Alpine (`apk`)
package Python, Node.js, Docker, Git and OpenSSH, but check the versions they give you. For Terraform there, use the
[download](https://developer.hashicorp.com/terraform/install) or [OpenTofu](#terraform-or-opentofu).

## Python and pip

You need Python 3.9 or newer. Python 3.12 is a good choice, because it is the default runtime of new projects.

**Windows**

```powershell
winget install -e --id Python.Python.3.12
```

**macOS**

```bash
brew install python@3.12
```

**Debian, Ubuntu**

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

**RHEL, CentOS, Rocky, AlmaLinux, Fedora, Amazon Linux**

```bash
sudo dnf install -y python3 python3-pip
```

Older systems can ship a Python that is too old. Check with `python3 --version`. On RHEL 8 and similar, install a newer one
with `sudo dnf install -y python3.11`.

### Install pskit

Use a virtual environment. Current Debian and Ubuntu refuse a system-wide `pip install`.

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install py-serverless-kit
```

**macOS and Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install py-serverless-kit
```

Then start it with `pskit studio --open`.

### If pip is missing

A virtual environment made with `uv` has no `pip`, and a deploy that installs dependencies then fails. Add it:

```bash
python -m ensurepip
```

## Terraform or OpenTofu

pskit finds `terraform` or `tofu` on your `PATH`. You need one of them.

### Terraform

**Windows**

```powershell
winget install -e --id Hashicorp.Terraform
```

**macOS**

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

**Debian, Ubuntu**

```bash
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
```

**RHEL, CentOS, Rocky, AlmaLinux**

```bash
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
sudo yum -y install terraform
```

**Fedora**

```bash
wget -O- https://rpm.releases.hashicorp.com/fedora/hashicorp.repo | sudo tee /etc/yum.repos.d/hashicorp.repo
sudo dnf -y install terraform
```

**Amazon Linux**

```bash
sudo yum install -y yum-utils shadow-utils
sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo
sudo yum install -y terraform
```

**Any other system:** download the [zip for your system](https://developer.hashicorp.com/terraform/install), unzip it, and
move `terraform` to a folder on your `PATH`.

### OpenTofu

**Windows**

```powershell
winget install -e --id OpenTofu.Tofu
```

**macOS**

```bash
brew install opentofu
```

**Linux:** see the [install guide](https://opentofu.org/docs/intro/install/) for your distribution's packages. The standalone
installer works on most systems:

```bash
curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o install-opentofu.sh
chmod +x install-opentofu.sh
./install-opentofu.sh --install-method standalone
```

## Node.js and npm

You need Node.js 18 or newer for Node.js and TypeScript projects. npm comes with it. We suggest Node.js 22, the newest
runtime on AWS, Google Cloud, Azure and Cloudflare. Other providers support older versions: see the
[provider table](nodejs.md#choosing-the-runtime).

**Windows**

```powershell
winget install -e --id OpenJS.NodeJS.22
```

**macOS**

```bash
brew install node@22
brew link --overwrite node@22
```

**Debian, Ubuntu**

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x -o nodesource_setup.sh
sudo -E bash nodesource_setup.sh
sudo apt install -y nodejs
```

**RHEL, CentOS, Fedora, Amazon Linux**

```bash
curl -fsSL https://rpm.nodesource.com/setup_22.x -o nodesource_setup.sh
sudo bash nodesource_setup.sh
sudo yum install -y nodejs
```

Other options are on the [Node.js download page](https://nodejs.org/en/download).

## Docker

**Windows**

```powershell
winget install -e --id Docker.DockerDesktop
```

Then start Docker Desktop and wait until it says it is running.

**macOS**

```bash
brew install --cask docker
```

Then start Docker Desktop.

**Linux**

Docker's [install guides](https://docs.docker.com/engine/install/) cover Ubuntu, Debian, Fedora, RHEL and CentOS, and are the
right choice for production servers. For a development machine, Docker's convenience script is quicker:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER      # then log out and back in
```

Docker Desktop needs a paid subscription for use in larger companies: see
[Docker's terms](https://docs.docker.com/subscription/desktop-license/).

## OpenSSH client

**Windows:** open **Settings > System > Optional features > Add a feature > OpenSSH Client**, or in an elevated PowerShell:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

**macOS:** `ssh` and `scp` are preinstalled.

**Debian, Ubuntu**

```bash
sudo apt install -y openssh-client
```

**RHEL, CentOS, Rocky, AlmaLinux, Fedora, Amazon Linux**

```bash
sudo dnf install -y openssh-clients
```

## sshpass

Optional. [Password logins](onprem/servers.md#log-in-to-a-server-with-a-password) use sshpass when it is installed,
and otherwise pskit's own askpass helper, which needs only OpenSSH 8.4+ (so Windows needs nothing extra). Keys are safer.

```bash
sudo apt install -y sshpass        # Debian, Ubuntu
sudo dnf install -y sshpass        # RHEL family, Fedora, Amazon Linux
```

macOS: `brew install hudochenkov/sshpass/sshpass`. Windows: not needed.

## Git

**Windows**

```powershell
winget install -e --id Git.Git
```

**macOS**

```bash
brew install git
```

**Linux**

```bash
sudo apt install -y git            # Debian, Ubuntu
sudo dnf install -y git            # RHEL family, Fedora, Amazon Linux
```

## Cloud CLIs

You need these to sign in or inspect resources from your machine. Install the one for your cloud.

| Cloud | Command | Install guide |
|---|---|---|
| AWS | `aws` | [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Azure | `az` | [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) |
| Google Cloud | `gcloud` | [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) |
| Alibaba Cloud | `aliyun` | [Alibaba Cloud CLI](https://www.alibabacloud.com/help/en/cli/) |
| Tencent Cloud | `tccli` | [TCCLI](https://github.com/TencentCloud/tencentcloud-cli) |
| Huawei Cloud | `hcloud` | [KooCLI](https://support.huaweicloud.com/intl/en-us/qs-hcli/hcli_02_003.html) |
| Oracle Cloud | `oci` | [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) |
| IBM Cloud | `ibmcloud` | [IBM Cloud CLI](https://cloud.ibm.com/docs/cli?topic=cli-getting-started) |
| DigitalOcean | `doctl` | [doctl](https://docs.digitalocean.com/reference/doctl/how-to/install/) |
| Cloudflare | `wrangler` | [Wrangler](https://developers.cloudflare.com/workers/wrangler/install-and-update/) |

Studio's **Setup & credentials** page shows the steps for your system, and how to sign in. Credentials are covered in
[Configure cloud credentials](getting-started.md#6-configure-cloud-credentials).

## Your own servers

Servers you deploy to need less than your own machine, because pskit installs most of what they need over SSH.

* **Operating system:** Linux, on x86_64 or arm64.
* **Access:** SSH from your machine. The user needs root or passwordless `sudo`.
* **Docker:** installed when missing, on servers used for `method: docker`, services, clusters and load balancers.
* **Python and Node.js:** a server without them can use a bundled copy. See
  [Deploy methods](providers/onprem/deploy-methods.md).
* **Firewall:** see [On-prem firewall](onprem/firewall.md) for the ports each server must allow.

Your own machine still needs Docker to build the image for a cluster deploy, and the OpenSSH client.
