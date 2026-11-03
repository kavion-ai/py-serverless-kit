"""after_deploy hook: call the freshly deployed API once.

Reads the endpoint from the deployment record that `pskit deploy` writes to
$PSKIT_WORK_DIR/deployment.json, so it works for any stage.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

record = json.loads((Path(os.environ["PSKIT_WORK_DIR"]) / "deployment.json").read_text())
endpoint = record.get("endpoint")
if not endpoint:
    sys.exit("no endpoint in deployment record")

req = urllib.request.Request(
    endpoint.rstrip("/") + "/orders",
    data=json.dumps({"item": "smoke-test"}).encode(),
    headers={"content-type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - our own endpoint
    assert resp.status == 201, resp.status
    print("smoke test ok:", json.loads(resp.read())["id"])
