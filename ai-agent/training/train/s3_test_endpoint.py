"""Smoke-test a running Hana server (llama-server in Colab, or the Docker image on your PC). Standard library only.

Run:  URL=http://127.0.0.1:8080 python ai-agent/training/train/s3_test_endpoint.py
Sends the Hana system prompt, the 10 tool definitions and four questions to the OpenAI-compatible
/v1/chat/completions endpoint, and checks the first step of each answer:
  who made you?                    -> text that names Asif Khan
  how do I add a schedule in studio? -> a search_docs call (or a text answer with "In studio")
  add a GET /health endpoint       -> a get_project / read_file / search_docs / propose_plan call
  deploy it to prod                -> text (points to the Deploy page), no deploying tool exists anyway
A call that comes back as raw "<tool_call>" text instead of tool_calls means the server isn't parsing tools:
start llama-server with --jinja.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from task_common import ENV_LINE, SYSTEM_PROMPT, TOOLS  # noqa: E402

URL = os.environ.get("URL", "http://127.0.0.1:8080").rstrip("/")
if not URL.startswith(("http://", "https://")):
    raise SystemExit("URL must start with http:// or https://")
ENV = ENV_LINE.format(provider="onprem", stage="dev", mode="ask", page="Functions")
CASES = [
    ("who made you?", lambda kind, x: kind == "text" and "Asif Khan" in x),
    ("how do I add a schedule in studio?", lambda kind, x: (kind == "tool" and x == "search_docs")
     or (kind == "text" and "In studio" in x)),
    ("add a GET /health endpoint that returns ok",
     lambda kind, x: kind == "tool" and x in ("get_project", "read_file", "search_docs", "propose_plan")),
    ("deploy it to prod", lambda kind, x: kind == "text" or x in ("get_project", "search_docs", "ask_user")),
]


def post(path, body, timeout=600):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode("utf-8"),  # noqa: S310 (scheme checked)
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def wait_ready():
    for _ in range(120):
        try:
            with urllib.request.urlopen(URL + "/health", timeout=5) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    raise SystemExit(f"{URL}/health did not answer in 4 minutes; is the server running?")


def main():
    wait_ready()
    passed = 0
    for question, test in CASES:
        t0 = time.time()
        out = post("/v1/chat/completions", {
            "model": "hana", "temperature": 0, "max_tokens": 400, "tools": TOOLS,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + "\n" + ENV},
                         {"role": "user", "content": question}]})
        msg = out["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        text = msg.get("content") or ""
        if calls:
            kind, what = "tool", calls[0]["function"]["name"]
            shown = f"tool {what} {calls[0]['function'].get('arguments', '')}"
        else:
            kind, what = "text", text
            shown = text.replace("\n", " ")
        ok = test(kind, what)
        passed += ok
        raw = "<tool_call>" in text
        print(f"[{'PASS' if ok else 'FAIL'}] {question!r} ({time.time() - t0:.1f}s)\n       {shown[:300]}")
        if raw:
            print("       raw <tool_call> in the text: start llama-server with --jinja")
    print(f"\n{passed}/{len(CASES)} passed against {URL}")


if __name__ == "__main__":
    main()
