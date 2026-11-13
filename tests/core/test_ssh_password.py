"""pskit's sshpass replacement: an askpass wrapper that works on Windows, macOS and Linux."""

from __future__ import annotations

import sys
from pathlib import Path

from py_serverless_kit.core import ssh_password

# A stand-in for ssh: runs the askpass program ssh would run, and prints what it answered.
FAKE_SSH = (
    "import os, subprocess, sys; "
    "assert os.environ['SSH_ASKPASS_REQUIRE'] == 'force'; "
    "out = subprocess.run([os.environ['SSH_ASKPASS'], sys.argv[1]], capture_output=True).stdout; "
    "sys.stdout.write('ANSWER=' + out.decode().strip() + '\\n'); sys.exit(7)"
)


def test_prefix_prefers_sshpass_and_falls_back_to_the_wrapper(monkeypatch):
    monkeypatch.setattr(ssh_password.shutil, "which", lambda name: "/usr/bin/sshpass")
    assert ssh_password.prefix("/p") == ["sshpass", "-f", "/p"]
    assert ssh_password.prefix() == ["sshpass", "-e"]
    monkeypatch.setattr(ssh_password.shutil, "which", lambda name: None)
    assert ssh_password.prefix("/p") == [sys.executable, "-m", ssh_password.MODULE, "-f", "/p"]
    assert ssh_password.is_wrapper(ssh_password.prefix("/p") + ["ssh"])
    assert ssh_password.is_wrapper(["sshpass", "-e", "ssh"])
    assert not ssh_password.is_wrapper(["ssh", "host"]) and not ssh_password.is_wrapper([])


def test_wrapper_answers_the_password_prompt_from_a_file(tmp_path: Path, capfd):
    secret = tmp_path / "pass"
    secret.write_bytes(b"Pa$$ w0rd!\nignored second line\n")
    code = ssh_password.main(["-f", str(secret), sys.executable, "-c", FAKE_SSH, "nkor@host's password:"])
    assert code == 7  # ssh's own exit code comes back
    assert "ANSWER=Pa$$ w0rd!" in capfd.readouterr().out


def test_wrapper_reads_sshpass_variable(monkeypatch, capfd):
    monkeypatch.setenv("SSHPASS", "from-env")
    assert ssh_password.main(["-e", sys.executable, "-c", FAKE_SSH, "Password:"]) == 7
    assert "ANSWER=from-env" in capfd.readouterr().out


def test_host_key_question_is_never_answered_with_the_password(monkeypatch, capsys):
    monkeypatch.setenv("SSHPASS", "secret")
    assert ssh_password.main(["--askpass", "Are you sure you want to continue connecting (yes/no/[fingerprint])?"]) == 0
    assert capsys.readouterr().out == "no\n"


def test_wrapper_reports_missing_inputs(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SSHPASS", raising=False)
    assert ssh_password.main(["-e", "ssh", "h"]) == 2
    assert ssh_password.main(["-f", str(tmp_path / "nope"), "ssh", "h"]) == 2
    assert ssh_password.main([]) == 2
