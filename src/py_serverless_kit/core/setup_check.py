"""Check what a provider needs on this machine, and explain how to fix what's missing.

Used by ``pskit doctor`` and ``pskit studio`` (``GET /api/setup``). Every check is
local and fast: tools are found on ``PATH``, credentials are looked up in
environment variables and the standard config files, and the few subprocesses
(``terraform version``, ``docker version``) run with a short timeout, no stdin
and no shell. Nothing here prints or returns a secret value.

A check is::

    {"id", "title", "status": "ok"|"missing"|"warning"|"info", "detail",
     "fix": {"summary", "links": [{"label", "url"}], "steps": {"windows", "macos", "linux"},
             "commands": [...], "action": None | "<id the studio can run>"}}
"""

from __future__ import annotations

import configparser
import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OK = "ok"
MISSING = "missing"
WARNING = "warning"
INFO = "info"
TIMEOUT = 8.0

Steps = Dict[str, List[str]]

# --------------------------------------------------------------------- tools


def _steps(windows: List[str], macos: List[str], linux: List[str]) -> Steps:
    return {"windows": windows, "macos": macos, "linux": linux}


# exe candidates, title, link, steps
TOOLS: Dict[str, Dict[str, Any]] = {
    "terraform": {
        "title": "Terraform (or OpenTofu)",
        "exes": ["terraform", "tofu"],
        "links": [
            {"label": "Install Terraform", "url": "https://developer.hashicorp.com/terraform/install"},
            {"label": "Install OpenTofu", "url": "https://opentofu.org/docs/intro/install/"},
        ],
        "steps": _steps(
            ["winget install Hashicorp.Terraform", "or: choco install terraform", "Open a new terminal afterwards."],
            ["brew tap hashicorp/tap", "brew install hashicorp/tap/terraform"],
            [
                "Follow the apt/yum repository steps on the install page, or download the zip,",
                "unzip it and move `terraform` to a folder on PATH (e.g. /usr/local/bin).",
            ],
        ),
    },
    "aws": {
        "title": "AWS CLI",
        "exes": ["aws"],
        "links": [
            {
                "label": "Install the AWS CLI",
                "url": "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html",
            }
        ],
        "steps": _steps(
            ["winget install Amazon.AWSCLI", "or run the installer: https://awscli.amazonaws.com/AWSCLIV2.msi"],
            ["brew install awscli", "or run the installer: https://awscli.amazonaws.com/AWSCLIV2.pkg"],
            [
                'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip',
                "unzip awscliv2.zip && sudo ./aws/install",
            ],
        ),
    },
    "az": {
        "title": "Azure CLI",
        "exes": ["az"],
        "links": [{"label": "Install the Azure CLI", "url": "https://learn.microsoft.com/cli/azure/install-azure-cli"}],
        "steps": _steps(
            ["winget install -e --id Microsoft.AzureCLI"],
            ["brew install azure-cli"],
            ["curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash   # Debian/Ubuntu"],
        ),
    },
    "gcloud": {
        "title": "Google Cloud CLI (gcloud)",
        "exes": ["gcloud"],
        "links": [{"label": "Install the gcloud CLI", "url": "https://cloud.google.com/sdk/docs/install"}],
        "steps": _steps(
            ["winget install Google.CloudSDK", "or download the installer from the install page"],
            ["brew install --cask google-cloud-sdk"],
            ["curl https://sdk.cloud.google.com | bash", "exec -l $SHELL"],
        ),
    },
    "aliyun": {
        "title": "Alibaba Cloud CLI (aliyun)",
        "exes": ["aliyun"],
        "links": [
            {"label": "Alibaba Cloud CLI", "url": "https://www.alibabacloud.com/help/en/cli/"},
            {"label": "Releases", "url": "https://github.com/aliyun/aliyun-cli/releases"},
        ],
        "steps": _steps(
            ["Download the Windows zip from the releases page and put aliyun.exe on PATH."],
            ["brew install aliyun-cli"],
            ["Download the Linux tgz from the releases page, extract it and move `aliyun` to /usr/local/bin."],
        ),
    },
    "tccli": {
        "title": "Tencent Cloud CLI (tccli)",
        "exes": ["tccli"],
        "links": [{"label": "TCCLI", "url": "https://github.com/TencentCloud/tencentcloud-cli"}],
        "steps": _steps(["pip install tccli"], ["pip install tccli"], ["pip install tccli"]),
    },
    "hcloud": {
        "title": "Huawei Cloud CLI (KooCLI)",
        "exes": ["hcloud"],
        "links": [{"label": "KooCLI", "url": "https://support.huaweicloud.com/intl/en-us/qs-hcli/hcli_02_003.html"}],
        "steps": _steps(
            ["Download KooCLI for Windows from the link and put hcloud.exe on PATH."],
            ["Download KooCLI for macOS from the link and put hcloud on PATH."],
            ["Download KooCLI for Linux from the link and put hcloud on PATH."],
        ),
    },
    "oci": {
        "title": "OCI CLI",
        "exes": ["oci"],
        "links": [
            {
                "label": "Install the OCI CLI",
                "url": "https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm",
            }
        ],
        "steps": _steps(["pip install oci-cli"], ["brew install oci-cli"], ["pip install oci-cli"]),
    },
    "ibmcloud": {
        "title": "IBM Cloud CLI",
        "exes": ["ibmcloud"],
        "links": [
            {"label": "Install the IBM Cloud CLI", "url": "https://cloud.ibm.com/docs/cli?topic=cli-getting-started"}
        ],
        "steps": _steps(
            ["iex (New-Object Net.WebClient).DownloadString('https://clis.cloud.ibm.com/install/powershell')"],
            ["curl -fsSL https://clis.cloud.ibm.com/install/osx | sh"],
            ["curl -fsSL https://clis.cloud.ibm.com/install/linux | sh"],
        ),
    },
    "doctl": {
        "title": "DigitalOcean CLI (doctl)",
        "exes": ["doctl"],
        "links": [{"label": "Install doctl", "url": "https://docs.digitalocean.com/reference/doctl/how-to/install/"}],
        "steps": _steps(
            ["Download the Windows zip from the install page and put doctl.exe on PATH."],
            ["brew install doctl"],
            ["sudo snap install doctl"],
        ),
    },
    "wrangler": {
        "title": "Cloudflare Wrangler",
        "exes": ["wrangler"],
        "links": [
            {
                "label": "Install Wrangler",
                "url": "https://developers.cloudflare.com/workers/wrangler/install-and-update/",
            }
        ],
        "steps": _steps(["npm install -g wrangler"], ["npm install -g wrangler"], ["npm install -g wrangler"]),
    },
    "ssh": {
        "title": "OpenSSH client (ssh, scp)",
        "exes": ["ssh"],
        "links": [
            {
                "label": "OpenSSH on Windows",
                "url": "https://learn.microsoft.com/windows-server/administration/openssh/openssh_install_firstuse",
            }
        ],
        "steps": _steps(
            [
                "Settings > System > Optional features > Add a feature > OpenSSH Client,",
                "or in an elevated PowerShell: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0",
            ],
            ["ssh and scp are preinstalled on macOS."],
            ["sudo apt install openssh-client   # or: sudo dnf install openssh-clients"],
        ),
    },
    "docker": {
        "title": "Docker",
        "exes": ["docker"],
        "links": [{"label": "Get Docker", "url": "https://docs.docker.com/get-docker/"}],
        "steps": _steps(
            ["winget install Docker.DockerDesktop", "Start Docker Desktop and wait until it says it is running."],
            ["brew install --cask docker", "Start Docker Desktop."],
            ["curl -fsSL https://get.docker.com | sh", "sudo usermod -aG docker $USER   # then log in again"],
        ),
    },
}

PROVIDER_CLI = {
    "aws": "aws",
    "azure": "az",
    "gcp": "gcloud",
    "alibaba": "aliyun",
    "tencent": "tccli",
    "huawei": "hcloud",
    "oracle": "oci",
    "ibm": "ibmcloud",
    "digitalocean": "doctl",
    "cloudflare": "wrangler",
}

# Environment variables the provider's Terraform plug-in (or pskit) reads.
ENV_HINTS: Dict[str, List[Dict[str, Any]]] = {
    "aws": [
        {"name": "AWS_PROFILE", "help": "Profile from ~/.aws/credentials or ~/.aws/config", "secret": False},
        {"name": "AWS_ACCESS_KEY_ID", "help": "Access key id", "secret": False},
        {"name": "AWS_SECRET_ACCESS_KEY", "help": "Secret access key", "secret": True},
        {"name": "AWS_SESSION_TOKEN", "help": "Session token (temporary credentials)", "secret": True},
        {"name": "AWS_REGION", "help": "Default region", "secret": False},
    ],
    "azure": [
        {"name": "ARM_SUBSCRIPTION_ID", "help": "Subscription to deploy into (required by azurerm 4)", "secret": False},
        {"name": "ARM_TENANT_ID", "help": "Tenant id (service principal)", "secret": False},
        {"name": "ARM_CLIENT_ID", "help": "Service principal app id", "secret": False},
        {"name": "ARM_CLIENT_SECRET", "help": "Service principal secret", "secret": True},
        {
            "name": "AZURE_STORAGE_CONNECTION_STRING",
            "help": "Storage account for Browse account and test messages (default: read from the deployment)",
            "secret": True,
        },
        {
            "name": "AZURE_SERVICEBUS_CONNECTION_STRING",
            "help": "Service Bus namespace for test topic messages (default: read from the deployment)",
            "secret": True,
        },
    ],
    "gcp": [
        {"name": "GOOGLE_CLOUD_PROJECT", "help": "Project id (provider.options.project default)", "secret": False},
        {"name": "GOOGLE_APPLICATION_CREDENTIALS", "help": "Path to a service account key JSON", "secret": False},
    ],
    "alibaba": [
        {"name": "ALICLOUD_ACCESS_KEY", "help": "AccessKey id", "secret": False},
        {"name": "ALICLOUD_SECRET_KEY", "help": "AccessKey secret", "secret": True},
        {"name": "ALICLOUD_REGION", "help": "Default region", "secret": False},
    ],
    "tencent": [
        {"name": "TENCENTCLOUD_SECRET_ID", "help": "SecretId", "secret": False},
        {"name": "TENCENTCLOUD_SECRET_KEY", "help": "SecretKey", "secret": True},
        {"name": "TENCENTCLOUD_REGION", "help": "Default region", "secret": False},
    ],
    "huawei": [
        {"name": "HW_ACCESS_KEY", "help": "Access key (AK)", "secret": False},
        {"name": "HW_SECRET_KEY", "help": "Secret key (SK)", "secret": True},
        {"name": "HW_REGION_NAME", "help": "Default region", "secret": False},
    ],
    "oracle": [
        {
            "name": "OCI_COMPARTMENT_ID",
            "help": "Compartment OCID (provider.options.compartment_id default)",
            "secret": False,
        },
        {"name": "OCI_CLI_CONFIG_FILE", "help": "Alternative to ~/.oci/config", "secret": False},
    ],
    "ibm": [{"name": "IC_API_KEY", "help": "IBM Cloud API key", "secret": True}],
    "digitalocean": [
        {"name": "DIGITALOCEAN_TOKEN", "help": "Personal access token", "secret": True},
        {
            "name": "DO_FUNCTIONS_NAMESPACE",
            "help": "Functions namespace id (options.namespace default)",
            "secret": False,
        },
    ],
    "cloudflare": [
        {"name": "CLOUDFLARE_API_TOKEN", "help": "API token with Workers permissions", "secret": True},
        {"name": "CLOUDFLARE_ACCOUNT_ID", "help": "Account id (options.account_id default)", "secret": False},
    ],
    "onprem": [
        {
            "name": "PSKIT_ADMIN_TOKEN",
            "help": "Admin token for /__pskit/* (options.admin_token default)",
            "secret": True,
        },
        {"name": "PSKIT_SSH_KEY", "help": "Private key for SSH / remote Docker deploys", "secret": False},
    ],
}

# Logins that work without a terminal: they open a browser and wait.
LOGIN_COMMANDS: Dict[str, List[str]] = {
    "az-login": ["az", "login"],
    "gcloud-login": ["gcloud", "auth", "login"],
    "gcloud-adc": ["gcloud", "auth", "application-default", "login"],
    "aws-sso-login": ["aws", "sso", "login"],
}

# Provider options that must have a value: (key, label, env fallback inside the default).
_REQUIRED_OPTIONS: Dict[str, List[Tuple[str, str]]] = {
    "azure": [("subscription_id", "Subscription ID")],
    "gcp": [("project", "Project")],
    "oracle": [("compartment_id", "Compartment OCID"), ("subnet_ids", "Subnet OCIDs")],
    "digitalocean": [("namespace", "Functions namespace")],
    "cloudflare": [("account_id", "Account ID")],
}
_DEFAULT_ENV = {
    ("azure", "subscription_id"): "ARM_SUBSCRIPTION_ID",
    ("gcp", "project"): "GOOGLE_CLOUD_PROJECT",
    ("oracle", "compartment_id"): "OCI_COMPARTMENT_ID",
    ("digitalocean", "namespace"): "DO_FUNCTIONS_NAMESPACE",
    ("cloudflare", "account_id"): "CLOUDFLARE_ACCOUNT_ID",
}
_SDKS: Dict[str, List[Tuple[str, str]]] = {
    "aws": [("boto3", "py-serverless-kit[aws]")],
    "gcp": [
        ("google.cloud.storage", "google-cloud-storage"),
        ("google.cloud.pubsub_v1", "google-cloud-pubsub"),
        ("google.cloud.logging", "google-cloud-logging"),
    ],
    "azure": [("azure.storage.queue", "azure-storage-queue"), ("azure.storage.blob", "azure-storage-blob")],
}
_ENV_REF = re.compile(r"^\s*\$\{\s*env:\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,(.*))?\}\s*$")
_SAFE_HOST = re.compile(r"^[A-Za-z0-9.:\[\]_][A-Za-z0-9._:\[\]-]*$")
_SAFE_USER = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


# --------------------------------------------------------------------- helpers


def os_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _run(argv: List[str], timeout: float = TIMEOUT) -> Optional[Tuple[int, str]]:
    """``(exit code, combined output)``, or None if it couldn't run in time."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()


def _fix(
    summary: str = "",
    links: Optional[List[Dict[str, str]]] = None,
    steps: Optional[Steps] = None,
    commands: Optional[List[str]] = None,
    action: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "summary": summary,
        "links": list(links or []),
        "steps": steps or _steps([], [], []),
        "commands": list(commands or []),
        "action": action,
    }


def _check(cid: str, title: str, status: str, detail: str, fix: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"id": cid, "title": title, "status": status, "detail": detail, "fix": fix or _fix()}


def _env(*names: str) -> bool:
    return all(os.environ.get(n) for n in names)


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _resolved(value: Any) -> Tuple[bool, str]:
    """Whether a config value has a usable value; ``${env:X}`` counts when X is set or has a default."""
    if value is None or value == "" or value == []:
        return False, ""
    if isinstance(value, str):
        match = _ENV_REF.match(value)
        if match:
            var, default = match.group(1), match.group(2)
            if os.environ.get(var):
                return True, f"from ${var}"
            if default is not None and default.strip():
                return True, "default value"
            return False, f"${var} is not set"
    return True, ""


def _options(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    provider = (raw or {}).get("provider")
    if not isinstance(provider, dict):
        return {}
    options = provider.get("options")
    return options if isinstance(options, dict) else {}


# --------------------------------------------------------------------- individual checks


def check_tool(tool: str, required: bool = True, purpose: str = "") -> Dict[str, Any]:
    spec = TOOLS[tool]
    exes = list(spec["exes"])
    if tool == "terraform" and os.environ.get("PSKIT_TERRAFORM_BIN"):
        exes.insert(0, os.environ["PSKIT_TERRAFORM_BIN"])
    found = next((path for path in (_which(e) for e in exes) if path), None)
    if found:
        detail = found
        if tool == "terraform":
            result = _run([found, "version"])
            if result and result[1]:
                detail = f"{result[1].splitlines()[0]} ({found})"
        return _check(f"tool:{tool}", spec["title"], OK, detail)
    status = MISSING if required else WARNING
    detail = f"{' / '.join(spec['exes'])} not found on PATH" + (f"; {purpose}" if purpose else "")
    return _check(
        f"tool:{tool}",
        spec["title"],
        status,
        detail,
        _fix(f"Install {spec['title']}, then open a new terminal.", spec["links"], spec["steps"]),
    )


def check_python() -> Dict[str, Any]:
    version = ".".join(str(v) for v in sys.version_info[:3])
    return _check("python", "Python", OK, f"Python {version} ({sys.executable})")


def _aws_credentials() -> Dict[str, Any]:
    title = "AWS credentials"
    fix = _fix(
        "Add an access key profile here, run `aws configure`, or `aws sso login` for SSO profiles.",
        [
            {
                "label": "Configure the AWS CLI",
                "url": "https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html",
            }
        ],
        commands=["aws configure", "aws sso login --profile <name>"],
        action="aws-profile",
    )
    if _env("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        return _check("credentials", title, OK, "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are set")
    creds = Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or _home() / ".aws" / "credentials")
    conf = Path(os.environ.get("AWS_CONFIG_FILE") or _home() / ".aws" / "config")
    profiles = set()
    for path, prefix in ((creds, ""), (conf, "profile ")):
        parser = configparser.RawConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            continue
        for section in parser.sections():
            name = section[len(prefix) :] if prefix and section.startswith(prefix) else section
            keys = set(parser.options(section))
            if keys & {"aws_access_key_id", "sso_session", "sso_start_url", "role_arn", "credential_process"}:
                profiles.add(name)
    wanted = os.environ.get("AWS_PROFILE") or "default"
    if wanted in profiles:
        return _check("credentials", title, OK, f"profile {wanted!r} found")
    if profiles:
        return _check(
            "credentials",
            title,
            WARNING,
            f"no {wanted!r} profile; found {', '.join(sorted(profiles))}. Set AWS_PROFILE to use one.",
            fix,
        )
    return _check("credentials", title, MISSING, "no AWS credentials in the environment or ~/.aws", fix)


def _azure_credentials() -> Dict[str, Any]:
    title = "Azure credentials"
    fix = _fix(
        "Sign in with the Azure CLI (opens a browser), or set ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID.",
        [
            {
                "label": "Authenticate Terraform to Azure",
                "url": "https://learn.microsoft.com/azure/developer/terraform/authenticate-to-azure",
            }
        ],
        commands=["az login", "az account set --subscription <id>"],
        action="az-login",
    )
    if _env("ARM_CLIENT_ID", "ARM_TENANT_ID") and (
        os.environ.get("ARM_CLIENT_SECRET")
        or os.environ.get("ARM_CLIENT_CERTIFICATE_PATH")
        or os.environ.get("ARM_USE_OIDC")
    ):
        return _check("credentials", title, OK, "service principal from ARM_* variables")
    folder = Path(os.environ.get("AZURE_CONFIG_DIR") or _home() / ".azure")
    profile = folder / "azureProfile.json"
    try:
        text = profile.read_text("utf-8-sig")
    except OSError:
        text = ""
    if '"subscriptions"' in text and '"id"' in text:
        return _check("credentials", title, OK, f"Azure CLI login found ({profile})")
    return _check("credentials", title, MISSING, "not signed in with `az login` and no ARM_* service principal", fix)


def _gcp_adc_path() -> Path:
    if os.environ.get("CLOUDSDK_CONFIG"):
        base = Path(os.environ["CLOUDSDK_CONFIG"])
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or _home() / "AppData" / "Roaming") / "gcloud"
    else:
        base = _home() / ".config" / "gcloud"
    return base / "application_default_credentials.json"


def _gcp_credentials() -> Dict[str, Any]:
    title = "Google Cloud credentials"
    fix = _fix(
        "Create Application Default Credentials (opens a browser), or point GOOGLE_APPLICATION_CREDENTIALS at a key file.",
        [{"label": "Set up ADC", "url": "https://cloud.google.com/docs/authentication/provide-credentials-adc"}],
        commands=["gcloud auth application-default login"],
        action="gcloud-adc",
    )
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key:
        if Path(key).is_file():
            return _check("credentials", title, OK, f"GOOGLE_APPLICATION_CREDENTIALS={key}")
        return _check(
            "credentials", title, MISSING, f"GOOGLE_APPLICATION_CREDENTIALS points to a missing file: {key}", fix
        )
    if os.environ.get("GOOGLE_CREDENTIALS"):
        return _check("credentials", title, OK, "GOOGLE_CREDENTIALS is set")
    adc = _gcp_adc_path()
    if adc.is_file():
        return _check("credentials", title, OK, f"Application Default Credentials ({adc})")
    return _check("credentials", title, MISSING, "no Application Default Credentials found", fix)


def _env_credentials(provider: str, title: str, groups: List[List[str]], files: List[Path], doc: str) -> Dict[str, Any]:
    fix = _fix(
        "Set the credential environment variables below (studio can set them for this session), "
        "or configure the provider's CLI profile.",
        [{"label": "Provider authentication", "url": doc}],
        commands=[f"set {n}=..." if sys.platform == "win32" else f"export {n}=..." for n in groups[0]],
        action="env",
    )
    for group in groups:
        if _env(*group):
            return _check("credentials", title, OK, f"{' / '.join(group)} set")
    for path in files:
        if path.exists():
            return _check("credentials", title, OK, f"CLI configuration found ({path})")
    return _check("credentials", title, MISSING, f"set {' and '.join(groups[0])}", fix)


def _oracle_credentials(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    title = "OCI credentials"
    opts = _options(raw)
    if str(opts.get("auth") or "").lower() in ("instanceprincipal", "resourceprincipal", "instance_principal"):
        return _check("credentials", title, OK, f"auth = {opts['auth']}")
    config = Path(os.environ.get("OCI_CLI_CONFIG_FILE") or _home() / ".oci" / "config")
    if config.is_file():
        return _check("credentials", title, OK, f"OCI config found ({config})")
    return _check(
        "credentials",
        title,
        MISSING,
        f"{config} not found",
        _fix(
            "Create an API key and config file with `oci setup config` (or the console's API keys page).",
            [
                {
                    "label": "SDK/CLI config file",
                    "url": "https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm",
                }
            ],
            commands=["oci setup config"],
        ),
    )


def credentials_check(provider: str, raw: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    home = _home()
    if provider == "aws":
        return _aws_credentials()
    if provider == "azure":
        return _azure_credentials()
    if provider == "gcp":
        return _gcp_credentials()
    if provider == "oracle":
        return _oracle_credentials(raw)
    if provider == "alibaba":
        return _env_credentials(
            provider,
            "Alibaba Cloud credentials",
            [["ALICLOUD_ACCESS_KEY", "ALICLOUD_SECRET_KEY"]],
            [home / ".aliyun" / "config.json"] if _options(raw).get("profile") else [],
            "https://registry.terraform.io/providers/aliyun/alicloud/latest/docs",
        )
    if provider == "tencent":
        return _env_credentials(
            provider,
            "Tencent Cloud credentials",
            [["TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY"]],
            [home / ".tccli"] if _options(raw).get("profile") else [],
            "https://registry.terraform.io/providers/tencentcloudstack/tencentcloud/latest/docs",
        )
    if provider == "huawei":
        return _env_credentials(
            provider,
            "Huawei Cloud credentials",
            [["HW_ACCESS_KEY", "HW_SECRET_KEY"]],
            [home / ".hcloud" / "config.json"] if _options(raw).get("profile") else [],
            "https://registry.terraform.io/providers/huaweicloud/huaweicloud/latest/docs",
        )
    if provider == "ibm":
        return _env_credentials(
            provider,
            "IBM Cloud credentials",
            [["IC_API_KEY"], ["IBMCLOUD_API_KEY"]],
            [],
            "https://registry.terraform.io/providers/IBM-Cloud/ibm/latest/docs",
        )
    if provider == "digitalocean":
        return _env_credentials(
            provider,
            "DigitalOcean credentials",
            [["DIGITALOCEAN_TOKEN"], ["DIGITALOCEAN_ACCESS_TOKEN"]],
            [],
            "https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs",
        )
    if provider == "cloudflare":
        return _env_credentials(
            provider,
            "Cloudflare credentials",
            [["CLOUDFLARE_API_TOKEN"], ["CLOUDFLARE_API_KEY", "CLOUDFLARE_EMAIL"]],
            [],
            "https://developers.cloudflare.com/fundamentals/api/get-started/create-token/",
        )
    return None


def options_checks(provider: str, raw: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    opts = _options(raw)
    for key, label in _REQUIRED_OPTIONS.get(provider, []):
        value = opts.get(key)
        env = _DEFAULT_ENV.get((provider, key))
        if value is None and env:
            value = f"${{env:{env}}}"  # the studio/template default
        good, how = _resolved(value)
        cid = f"option:{key}"
        title = f"provider.options.{key}"
        if good:
            out.append(_check(cid, title, OK, how or "set"))
            continue
        commands = [f"set {env}=..." if sys.platform == "win32" else f"export {env}=..."] if env else []
        out.append(
            _check(
                cid,
                title,
                MISSING,
                how or f"{label} is required",
                _fix(
                    f"Set {label} on the Overview page (provider options)"
                    + (f" or the {env} variable." if env else "."),
                    commands=commands,
                    action="env" if env else None,
                ),
            )
        )
    return out


def sdk_checks(provider: str) -> List[Dict[str, Any]]:
    out = []
    for module, package in _SDKS.get(provider, []):
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            present = False
        cid = f"sdk:{package}"
        title = f"Python package {package}"
        if present:
            out.append(_check(cid, title, OK, "installed"))
        else:
            out.append(
                _check(
                    cid,
                    title,
                    INFO,
                    "optional: lets studio browse existing resources and read logs",
                    _fix("Install it to enable these features.", commands=[f'pip install "{package}"']),
                )
            )
    return out


# --------------------------------------------------------------------- on-premises


def _deploy(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    deploy = _options(raw).get("deploy")
    if isinstance(deploy, str):
        return {"method": deploy}
    return dict(deploy) if isinstance(deploy, dict) else {}


def _key_path(deploy: Dict[str, Any]) -> str:
    for name in ("pem", "identity_file", "identity"):
        value = deploy.get(name)
        if isinstance(value, str) and value.strip():
            return os.path.expanduser(value.strip())
    return os.environ.get("PSKIT_SSH_KEY") or ""


def _key_check(deploy: Dict[str, Any], required: bool) -> Dict[str, Any]:
    path = _key_path(deploy)
    title = "SSH private key"
    fix = _fix(
        "Choose the .pem / private key file for the server (Overview > On-premises deployment > Private key).",
        steps=_steps(
            ['Remove access for other users: icacls key.pem /inheritance:r /grant:r "%USERNAME%:R"'],
            ["chmod 600 ~/.ssh/server.pem"],
            ["chmod 600 ~/.ssh/server.pem"],
        ),
    )
    if not path:
        if required:
            return _check("ssh:key", title, MISSING, "no key set (options.deploy.pem or PSKIT_SSH_KEY)", fix)
        return _check("ssh:key", title, INFO, "no key set: the SSH agent or your default key is used", fix)
    key = Path(path)
    if not key.is_file():
        return _check("ssh:key", title, MISSING, f"not found: {path}", fix)
    try:
        with key.open("rb"):
            pass
    except OSError as exc:
        return _check("ssh:key", title, MISSING, f"cannot read {path}: {exc.strerror or exc}", fix)
    if sys.platform != "win32":
        mode = stat.S_IMODE(key.stat().st_mode)
        if mode & 0o077:
            return _check(
                "ssh:key", title, WARNING, f"{path} is readable by others ({oct(mode)}); ssh may refuse it", fix
            )
        return _check("ssh:key", title, OK, path)
    return _check(
        "ssh:key",
        title,
        OK,
        f"{path} (Windows OpenSSH refuses keys other users can read; see the fix if ssh says 'UNPROTECTED')",
        fix,
    )


def onprem_checks(raw: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deploy = _deploy(raw)
    method = str(deploy.get("method") or "local")
    out: List[Dict[str, Any]] = []
    if method == "local":
        out.append(_check("onprem:method", "Deploy method", OK, "local: the host runs on this machine"))
        return out
    host = str(deploy.get("host") or "").strip()
    remote = method == "ssh" or bool(host)
    out.append(_check("onprem:method", "Deploy method", OK, method + (f" on {host}" if host else "")))
    if remote:
        out.append(check_tool("ssh", required=True, purpose="needed to reach the server"))
        if not _which("scp"):
            out.append(
                _check(
                    "tool:scp",
                    "scp",
                    MISSING,
                    "scp not found on PATH",
                    _fix("Install the OpenSSH client.", TOOLS["ssh"]["links"], TOOLS["ssh"]["steps"]),
                )
            )
        if not host:
            out.append(
                _check(
                    "ssh:host",
                    "SSH host",
                    MISSING,
                    "options.deploy.host is empty",
                    _fix("Set the server address on the Overview page (On-premises deployment)."),
                )
            )
        elif not _SAFE_HOST.match(host):
            out.append(_check("ssh:host", "SSH host", MISSING, f"invalid host {host!r}"))
        else:
            out.append(
                _check(
                    "ssh:host",
                    "SSH connection",
                    INFO,
                    f"{deploy.get('user') or 'current user'}@{host}:{deploy.get('port') or 22}",
                    _fix("Test that the server accepts the key without a password prompt.", action="ssh-test"),
                )
            )
        out.append(_key_check(deploy, required=method == "docker"))
    if method == "docker":
        out.append(check_tool("docker", required=True, purpose="builds the host image"))
        if _which("docker"):
            out.append(_docker_daemon())
        if deploy.get("docker_host"):
            out.append(
                _check(
                    "docker:host",
                    "Remote Docker host",
                    INFO,
                    f"docker_host = {deploy['docker_host']}; it must be reachable from this machine",
                )
            )
    return out


def _docker_daemon() -> Dict[str, Any]:
    exe = _which("docker") or "docker"
    result = _run([exe, "version", "--format", "{{.Server.Version}}"], timeout=TIMEOUT)
    if result is not None and result[0] == 0 and result[1]:
        return _check("docker:daemon", "Docker daemon", OK, f"running (server {result[1].splitlines()[-1]})")
    detail = (result[1].splitlines()[-1] if result and result[1] else "no answer") if result else "timed out"
    return _check(
        "docker:daemon",
        "Docker daemon",
        MISSING,
        f"the Docker daemon is not reachable: {detail}",
        _fix(
            "Start Docker Desktop (Windows/macOS) or the docker service (Linux).",
            TOOLS["docker"]["links"],
            _steps(["Start Docker Desktop."], ["Start Docker Desktop."], ["sudo systemctl start docker"]),
        ),
    )


# --------------------------------------------------------------------- entry points


def check(provider: str, raw: Optional[Dict[str, Any]] = None, root: Optional[Path] = None) -> Dict[str, Any]:
    """Every check for ``provider``; ``raw`` is the pskit.yml mapping as written (optional)."""
    del root  # reserved: project-relative checks
    checks: List[Dict[str, Any]] = [
        check_python(),
        check_tool("terraform", required=True, purpose="pskit deploys with it"),
    ]
    if provider == "onprem":
        checks.extend(onprem_checks(raw))
    else:
        cli = PROVIDER_CLI.get(provider)
        creds = credentials_check(provider, raw)
        if cli:
            purpose = "used to sign in and inspect resources"
            checks.append(check_tool(cli, required=False, purpose=purpose))
        if creds is not None:
            checks.append(creds)
        checks.extend(options_checks(provider, raw))
        checks.extend(sdk_checks(provider))
    return {"provider": provider, "ok": not any(c["status"] == MISSING for c in checks), "checks": checks}


def login_argv(action: str) -> List[str]:
    """argv for a browser login action; raises ValueError if unknown or the CLI is missing."""
    if action not in LOGIN_COMMANDS:
        raise ValueError(f"unknown login action {action!r}; known: {', '.join(sorted(LOGIN_COMMANDS))}")
    argv = list(LOGIN_COMMANDS[action])
    exe = _which(argv[0])
    if not exe:
        raise ValueError(f"{argv[0]} is not installed (not on PATH)")
    return [exe, *argv[1:]]


def ssh_test_argv(deploy: Dict[str, Any]) -> List[str]:
    """``ssh`` argv that checks the server accepts the key without prompting."""
    host = str(deploy.get("host") or "").strip()
    if not host or not _SAFE_HOST.match(host):
        raise ValueError(f"invalid SSH host {host!r}")
    user = str(deploy.get("user") or "").strip()
    if user and not _SAFE_USER.match(user):
        raise ValueError(f"invalid SSH user {user!r}")
    try:
        raw_port = deploy.get("port")
        port = 22 if raw_port is None or raw_port == "" else int(raw_port)
    except (TypeError, ValueError):
        raise ValueError("SSH port must be a number") from None
    if not 1 <= port <= 65535:
        raise ValueError("SSH port must be 1-65535")
    exe = _which("ssh")
    if not exe:
        raise ValueError("ssh is not installed (not on PATH)")
    argv = [exe, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", str(port)]
    key = _key_path(deploy)
    if key:
        if not Path(key).is_file():
            raise ValueError(f"SSH private key not found: {key}")
        argv += ["-i", str(Path(key).resolve()), "-o", "IdentitiesOnly=yes"]
    known = str(deploy.get("known_hosts") or "accept-new")
    if known == "accept-new":
        argv += ["-o", "StrictHostKeyChecking=accept-new"]
    elif known == "ignore":
        argv += [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=" + ("NUL" if sys.platform == "win32" else "/dev/null"),
        ]
    else:
        if known.startswith("-") or any(c in known for c in "\r\n"):
            raise ValueError("invalid known_hosts value")
        argv += ["-o", f"UserKnownHostsFile={known}", "-o", "StrictHostKeyChecking=yes"]
    argv += ["--", f"{user}@{host}" if user else host, "echo pskit-ok"]
    return argv


_PROFILE_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,64}$")
_KEY_ID_RE = re.compile(r"^[A-Z0-9]{16,128}$")
_REGION_RE = re.compile(r"^[a-z]{2}(-[a-z0-9]+){1,3}-\d{1,2}$")
_TOKEN_RE = re.compile(r"^\S+$")


def write_aws_profile(
    profile: str,
    access_key_id: str,
    secret_access_key: str,
    region: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Add or replace one profile in ~/.aws/credentials (and its region in ~/.aws/config)."""
    profile = (profile or "default").strip()
    access_key_id = (access_key_id or "").strip()
    secret_access_key = (secret_access_key or "").strip()
    region = (region or "").strip() or None
    session_token = (session_token or "").strip() or None
    if not _PROFILE_RE.match(profile):
        raise ValueError("profile name may use letters, digits and . _ + - (max 64)")
    if not _KEY_ID_RE.match(access_key_id):
        raise ValueError("access key id should look like AKIA... (16-128 uppercase letters and digits)")
    if not secret_access_key or not _TOKEN_RE.match(secret_access_key) or len(secret_access_key) > 256:
        raise ValueError("secret access key is empty or contains whitespace")
    if session_token is not None and (not _TOKEN_RE.match(session_token) or len(session_token) > 4096):
        raise ValueError("session token contains whitespace")
    if region is not None and not _REGION_RE.match(region):
        raise ValueError(f"invalid region {region!r}, e.g. us-east-1")
    creds = Path(os.environ.get("AWS_SHARED_CREDENTIALS_FILE") or _home() / ".aws" / "credentials")
    conf = Path(os.environ.get("AWS_CONFIG_FILE") or _home() / ".aws" / "config")

    values = {"aws_access_key_id": access_key_id, "aws_secret_access_key": secret_access_key}
    if session_token:
        values["aws_session_token"] = session_token

    def update(path: Path, section: str, items: Dict[str, str], drop: Tuple[str, ...] = ()) -> None:
        parser = configparser.RawConfigParser()
        if path.is_file():
            parser.read(path, encoding="utf-8")
        if not parser.has_section(section):
            parser.add_section(section)
        for key in drop:
            parser.remove_option(section, key)
        for key, value in items.items():
            parser.set(section, key, value)
        _write_private(path, parser)

    update(creds, profile, values, drop=() if session_token else ("aws_session_token",))
    if region:
        update(conf, profile if profile == "default" else f"profile {profile}", {"region": region})
    return {"profile": profile, "credentials_file": str(creds), "config_file": str(conf) if region else None}


def _write_private(path: Path, parser: configparser.RawConfigParser) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    fd, tmp = tempfile.mkstemp(prefix=".pskit-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            parser.write(fh)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


__all__ = [
    "ENV_HINTS",
    "LOGIN_COMMANDS",
    "TOOLS",
    "check",
    "login_argv",
    "os_key",
    "ssh_test_argv",
    "write_aws_profile",
]
