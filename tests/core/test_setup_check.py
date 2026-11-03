import configparser
import os
import sys
from pathlib import Path

import pytest

from py_serverless_kit.cli.templates import DEFAULT_REGIONS
from py_serverless_kit.config.schema import PROVIDERS
from py_serverless_kit.core import setup_check as sc
from py_serverless_kit.providers.regions import REGIONS, regions_for

CRED_VARS = [h["name"] for hints in sc.ENV_HINTS.values() for h in hints] + [
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
    "AZURE_CONFIG_DIR",
    "CLOUDSDK_CONFIG",
    "GOOGLE_CREDENTIALS",
    "IBMCLOUD_API_KEY",
    "DIGITALOCEAN_ACCESS_TOKEN",
    "CLOUDFLARE_API_KEY",
    "CLOUDFLARE_EMAIL",
    "PSKIT_TERRAFORM_BIN",
    "APPDATA",
]


@pytest.fixture
def clean(tmp_path, monkeypatch):
    """No credentials, no tools, home in tmp_path."""
    for var in CRED_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sc, "_home", lambda: tmp_path)
    monkeypatch.setattr(sc, "_which", lambda name: None)
    monkeypatch.setattr(sc, "_run", lambda argv, timeout=8.0: None)
    return tmp_path


def by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_shape_for_every_provider(clean):
    for provider in PROVIDERS:
        report = sc.check(provider, {"provider": {"name": provider}})
        assert report["provider"] == provider
        assert isinstance(report["ok"], bool)
        for item in report["checks"]:
            assert set(item) == {"id", "title", "status", "detail", "fix"}
            assert item["status"] in ("ok", "missing", "warning", "info")
            assert set(item["fix"]) == {"summary", "links", "steps", "commands", "action"}
            assert set(item["fix"]["steps"]) == {"windows", "macos", "linux"}


def test_missing_terraform_has_install_steps(clean):
    report = sc.check("aws")
    tf = by_id(report)["tool:terraform"]
    assert tf["status"] == "missing" and not report["ok"]
    assert any("hashicorp.com" in link["url"] for link in tf["fix"]["links"])
    assert tf["fix"]["steps"]["windows"] and tf["fix"]["steps"]["macos"] and tf["fix"]["steps"]["linux"]
    # A missing cloud CLI is only a warning; credentials decide.
    assert by_id(report)["tool:aws"]["status"] == "warning"
    assert by_id(report)["credentials"]["status"] == "missing"
    assert by_id(report)["credentials"]["fix"]["action"] == "aws-profile"


def test_tools_found(clean, monkeypatch):
    monkeypatch.setattr(sc, "_which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(sc, "_run", lambda argv, timeout=8.0: (0, "Terraform v1.9.0\non linux_amd64"))
    checks = by_id(sc.check("aws"))
    assert checks["tool:terraform"]["status"] == "ok"
    assert checks["tool:terraform"]["detail"].startswith("Terraform v1.9.0")
    assert checks["tool:aws"]["status"] == "ok"


def test_aws_credentials_from_env_and_profile(clean, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE000000000")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")
    assert by_id(sc.check("aws"))["credentials"]["status"] == "ok"
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    sc.write_aws_profile("work", "AKIAEXAMPLE000000000", "secret/with+chars%", region="eu-west-1")
    assert by_id(sc.check("aws"))["credentials"]["status"] == "warning"  # profile exists but isn't selected
    monkeypatch.setenv("AWS_PROFILE", "work")
    assert by_id(sc.check("aws"))["credentials"]["status"] == "ok"


def test_write_aws_profile_keeps_other_profiles(clean):
    aws = clean / ".aws"
    aws.mkdir()
    (aws / "credentials").write_text(
        "[default]\naws_access_key_id = AKIAOLD0000000000000\naws_secret_access_key = old\n"
    )
    result = sc.write_aws_profile("dev", "AKIANEW0000000000000", "s3cr%t", region="us-east-2", session_token="tok")
    parser = configparser.RawConfigParser()
    parser.read(aws / "credentials")
    assert parser.get("default", "aws_access_key_id") == "AKIAOLD0000000000000"
    assert parser.get("dev", "aws_secret_access_key") == "s3cr%t"
    assert parser.get("dev", "aws_session_token") == "tok"
    config = configparser.RawConfigParser()
    config.read(aws / "config")
    assert config.get("profile dev", "region") == "us-east-2"
    assert result["profile"] == "dev" and "s3cr" not in str(result)
    # Re-writing without a token drops the old one.
    sc.write_aws_profile("dev", "AKIANEW0000000000000", "other")
    parser = configparser.RawConfigParser()
    parser.read(aws / "credentials")
    assert not parser.has_option("dev", "aws_session_token")
    if sys.platform != "win32":
        assert oct(os.stat(aws / "credentials").st_mode & 0o777) == "0o600"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profile": "bad name", "access_key_id": "AKIAEXAMPLE000000000", "secret_access_key": "x"},
        {"profile": "p", "access_key_id": "short", "secret_access_key": "x"},
        {"profile": "p", "access_key_id": "AKIAEXAMPLE000000000", "secret_access_key": "has space"},
        {"profile": "p", "access_key_id": "AKIAEXAMPLE000000000", "secret_access_key": "x", "region": "nowhere"},
        {"profile": "p", "access_key_id": "AKIAEXAMPLE000000000", "secret_access_key": "x\n[evil]"},
    ],
)
def test_write_aws_profile_rejects_bad_input(clean, kwargs):
    with pytest.raises(ValueError):
        sc.write_aws_profile(**kwargs)
    assert not (clean / ".aws" / "credentials").exists()


def test_azure_and_gcp_credentials(clean, monkeypatch):
    assert by_id(sc.check("azure"))["credentials"]["fix"]["action"] == "az-login"
    (clean / ".azure").mkdir()
    (clean / ".azure" / "azureProfile.json").write_text('{"subscriptions": [{"id": "x"}]}', encoding="utf-8")
    assert by_id(sc.check("azure"))["credentials"]["status"] == "ok"

    monkeypatch.setenv("CLOUDSDK_CONFIG", str(clean / "gcloud"))
    gcp = by_id(sc.check("gcp"))["credentials"]
    assert gcp["status"] == "missing" and gcp["fix"]["action"] == "gcloud-adc"
    (clean / "gcloud").mkdir()
    (clean / "gcloud" / "application_default_credentials.json").write_text("{}")
    assert by_id(sc.check("gcp"))["credentials"]["status"] == "ok"
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(clean / "missing.json"))
    assert by_id(sc.check("gcp"))["credentials"]["status"] == "missing"


def test_env_credentials(clean, monkeypatch):
    assert by_id(sc.check("cloudflare"))["credentials"]["status"] == "missing"
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    assert by_id(sc.check("cloudflare"))["credentials"]["status"] == "ok"
    monkeypatch.setenv("DIGITALOCEAN_ACCESS_TOKEN", "t")
    assert by_id(sc.check("digitalocean"))["credentials"]["status"] == "ok"


def test_required_options(clean, monkeypatch):
    raw = {"provider": {"name": "gcp", "options": {"project": "${env:GOOGLE_CLOUD_PROJECT}"}}}
    opt = by_id(sc.check("gcp", raw))["option:project"]
    assert opt["status"] == "missing" and "GOOGLE_CLOUD_PROJECT" in opt["detail"]
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    assert by_id(sc.check("gcp", raw))["option:project"]["status"] == "ok"
    literal = {"provider": {"name": "oracle", "options": {"compartment_id": "ocid1.x", "subnet_ids": []}}}
    checks = by_id(sc.check("oracle", literal))
    assert checks["option:compartment_id"]["status"] == "ok"
    assert checks["option:subnet_ids"]["status"] == "missing"


def test_onprem_local_needs_nothing_else(clean, monkeypatch):
    monkeypatch.setattr(sc, "_which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(sc, "_run", lambda argv, timeout=8.0: (0, "Terraform v1.9.0"))
    report = sc.check("onprem", {"provider": {"name": "onprem"}})
    assert report["ok"]
    assert [c["id"] for c in report["checks"]] == ["python", "tool:terraform", "onprem:method"]


def test_onprem_ssh(clean, monkeypatch):
    monkeypatch.setattr(sc, "_which", lambda name: f"/bin/{name}" if name != "scp" else None)
    raw = {"provider": {"name": "onprem", "options": {"deploy": {"method": "ssh", "pem": str(clean / "k.pem")}}}}
    checks = by_id(sc.check("onprem", raw))
    assert checks["tool:scp"]["status"] == "missing"
    assert checks["ssh:host"]["status"] == "missing"
    assert checks["ssh:key"]["status"] == "missing"
    (clean / "k.pem").write_text("key")
    if sys.platform != "win32":
        os.chmod(clean / "k.pem", 0o600)
    raw["provider"]["options"]["deploy"]["host"] = "10.0.0.5"
    checks = by_id(sc.check("onprem", raw))
    assert checks["ssh:key"]["status"] == "ok"
    assert checks["ssh:host"]["fix"]["action"] == "ssh-test"


def test_onprem_docker_daemon(clean, monkeypatch):
    monkeypatch.setattr(sc, "_which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(sc, "_run", lambda argv, timeout=8.0: (1, "Cannot connect to the Docker daemon"))
    raw = {"provider": {"name": "onprem", "options": {"deploy": "docker"}}}
    daemon = by_id(sc.check("onprem", raw))["docker:daemon"]
    assert daemon["status"] == "missing" and "Cannot connect" in daemon["detail"]


def test_ssh_test_argv(clean, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_which", lambda name: "/usr/bin/ssh")
    key = tmp_path / "id.pem"
    key.write_text("k")
    argv = sc.ssh_test_argv({"host": "10.0.1.12", "user": "ubuntu", "port": 2222, "pem": str(key)})
    assert argv[0] == "/usr/bin/ssh"
    assert "BatchMode=yes" in argv and "2222" in argv and str(key.resolve()) in argv
    assert argv[-3:] == ["--", "ubuntu@10.0.1.12", "echo pskit-ok"]
    for bad in (
        {"host": "-oProxyCommand=evil"},
        {"host": "a b"},
        {"host": ""},
        {"host": "h", "user": "-x"},
        {"host": "h", "port": 0},
        {"host": "h", "pem": str(tmp_path / "nope")},
        {"host": "h", "known_hosts": "-oProxyCommand=x"},
    ):
        with pytest.raises(ValueError):
            sc.ssh_test_argv(bad)


def test_login_argv(monkeypatch):
    monkeypatch.setattr(sc, "_which", lambda name: r"C:\Tools\az.cmd" if name == "az" else None)
    assert sc.login_argv("az-login") == [r"C:\Tools\az.cmd", "login"]
    with pytest.raises(ValueError):
        sc.login_argv("gcloud-adc")  # CLI not installed
    with pytest.raises(ValueError):
        sc.login_argv("rm-rf")


def test_regions_cover_default_region():
    for provider in PROVIDERS:
        ids = [r["id"] for r in REGIONS[provider]]
        assert DEFAULT_REGIONS[provider] in ids, provider
        assert len(ids) == len(set(ids)), provider
        assert all(r["label"] for r in REGIONS[provider])
    assert regions_for("nope") == []
    regions_for("aws")[0]["id"] = "changed"
    assert REGIONS["aws"][0]["id"] == "us-east-1"


def test_home_is_used(clean):
    assert sc._home() == Path(clean)
