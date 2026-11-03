"""Run the Alibaba / Tencent / Huawei / Oracle / IBM / DigitalOcean JS adapter tests with ``node --test``."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROVIDERS = ("alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
@pytest.mark.parametrize("provider", PROVIDERS)
def test_js_adapter(provider):
    test_file = HERE / f"adapter_{provider}.test.js"
    proc = subprocess.run(["node", "--test", str(test_file)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
