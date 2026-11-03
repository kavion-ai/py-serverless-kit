"""Hana, the studio's AI assistant: tools, the chat loop and its approvals, the API. A scripted fake model stands in
for the real one, so nothing here needs Docker, a GPU or the network."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from py_serverless_kit.studio.hana import docs_index, prompt
from py_serverless_kit.studio.hana import session as hana_session
from py_serverless_kit.studio.hana.knowledge import search
from py_serverless_kit.studio.hana.model import parse_message
from py_serverless_kit.studio.hana.session import Hana, docs_query, fit
from py_serverless_kit.studio.hana.tools import ProjectTools, redact, set_dotted
from py_serverless_kit.studio.server import make_server

from .test_studio import call

TOKEN = "test-token-123"
REPO = Path(__file__).resolve().parents[2]

CONFIG = """
service: hana-demo
provider:
  name: aws
  region: us-east-1
functions:
  hello:
    handler: app.handlers.hello
    events:
      - http: GET /hello
"""


@pytest.fixture(autouse=True)
def _no_docs_first(request, monkeypatch):
    """The chat-loop tests script exact steps; the docs search studio runs first is tested on its own
    (tests named ``test_docs_first_*``)."""
    if not request.node.name.startswith("test_docs_first"):
        monkeypatch.setattr(hana_session, "PRE_SEARCH_CARDS", 0)


class FakeModel:
    """Replays scripted steps: ``("call", name, args)`` or ``("text", answer)``; records what it was sent."""

    def __init__(self, steps: List[Any]) -> None:
        self.steps = list(steps)
        self.sent: List[List[Dict[str, Any]]] = []

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int = 900) -> Dict[str, Any]:
        assert tools == prompt.TOOLS
        self.sent.append(messages)
        step = self.steps.pop(0)
        if step[0] == "text":
            return {"content": step[1], "tool_calls": [], "usage": {}}
        return {"content": "", "tool_calls": [{"id": "x", "name": step[1], "arguments": step[2]}], "usage": {}}


def run_turn(hana: Hana, text: str, mode: str = "ask", answers: Any = None, sid: Any = None,
             first: str = "model") -> Dict[str, Any]:
    """Send ``text`` and answer every pending question with ``answers(pending) -> (decision, text)``."""
    turn = hana.send(sid, text, {"provider": "aws", "stage": "dev", "mode": mode, "page": "Functions", "first": first})
    deadline = time.time() + 60
    while time.time() < deadline:
        snap = turn.snapshot()
        if snap["pending"] and answers:
            decision, value = answers(snap["pending"])
            turn.respond(snap["pending"]["id"], {"decision": decision, "text": value})
        if snap["status"] in ("done", "error", "stopped"):
            return snap
        time.sleep(0.02)
    raise AssertionError("turn did not finish")


def types_of(snap: Dict[str, Any]) -> List[str]:
    return [e["type"] for e in snap["events"] if e["type"] != "thinking"]


# --------------------------------------------------------------------------- prompt / docs


def test_prompt_is_what_hana_was_trained_with():
    training = REPO / "ai-agent" / "training" / "tools"
    if not (training / "task_common.py").exists():
        pytest.skip("training data not in this checkout")
    sys.path.insert(0, str(training))
    try:
        import task_common  # type: ignore[import-not-found]
    finally:
        sys.path.remove(str(training))
    assert prompt.SYSTEM_PROMPT == task_common.SYSTEM_PROMPT
    assert prompt.ENV_LINE == task_common.ENV_LINE
    assert prompt.TOOLS == task_common.TOOLS
    assert prompt.TERMINAL_LINE == task_common.TERMINAL_LINE
    assert prompt.DOCS_LINE == task_common.DOCS_LINE
    assert prompt.system_message("aws", "dev", "ask", "Functions", servers=[]).split("\n")[-2] == prompt.DOCS_LINE
    assert prompt.system_message("onprem", "dev", "ask", "Logs", servers=["app-1"]) == task_common.system_message(
        "onprem", "dev", "ask", "Logs", servers=["app-1"])
    assert prompt.system_message("onprem", "dev", "ask", "Logs").endswith(
        "Environment: provider=onprem stage=dev mode=ask page=Logs")


def test_search_docs_returns_cited_excerpts():
    text, ids = search()("schedule trigger cron")
    assert len(ids) == 2
    assert text.startswith("[") and "]\n" in text


def test_docs_index_is_up_to_date():
    if not (REPO / "docs").is_dir():
        pytest.skip("docs not in this checkout")
    assert docs_index.INDEX.read_bytes() == docs_index.encode(docs_index.build(REPO)), (
        "docs changed: run python scripts/build_hana_docs_index.py")


def test_docs_index_cards_cite_sections_and_carry_search_terms():
    text = "# Load balancers\n\nSearch terms: LB, nginx, round robin\n\nIntro.\n\n## Create a load balancer\n\n" \
           "Steps.\n\n```bash\n## not a heading\n```\n\n## See also\n\n- x\n"
    cards = docs_index.page_cards("docs/onprem/lb.md", text)
    assert [c["sources"][0] for c in cards] == ["docs/onprem/lb.md", "docs/onprem/lb.md#create-a-load-balancer"]
    assert cards[1]["text"].startswith("Load balancers > Create a load balancer\n\n")
    assert "## not a heading" in cards[1]["text"]  # headings inside code fences do not split
    assert all(c["tags"] == ["LB", "nginx", "round robin"] for c in cards)
    assert docs_index.encode(cards) == docs_index.encode(cards)


def test_search_finds_the_new_docs():
    _, ids = search()("shared load balancer for several clusters", k=3)
    assert any(i.startswith("docs/") for i in ids)


def test_docs_query_joins_a_short_reply_to_the_previous_question():
    history = [{"role": "user", "content": "how do I scale postgres with read replicas?"},
               {"role": "assistant", "content": "..."}]
    assert docs_query("yes", history) == "how do I scale postgres with read replicas? yes"
    assert docs_query("how do I add a cron schedule", history) == "how do I add a cron schedule"
    assert docs_query("?!", []) == ""


# --------------------------------------------------------------------------- tools


def test_set_dotted():
    cfg: Dict[str, Any] = {"functions": {"w": {"events": [{"queue": "a"}]}}}
    set_dotted(cfg, "functions.w.events.0.queue", "b")
    set_dotted(cfg, "functions.w.events.1", {"http": "GET /x"})
    set_dotted(cfg, "functions.w.timeout", 20)
    set_dotted(cfg, "functions.n.handler", "app.n.run")
    assert cfg["functions"]["w"] == {"events": [{"queue": "b"}, {"http": "GET /x"}], "timeout": 20}
    assert cfg["functions"]["n"] == {"handler": "app.n.run"}
    set_dotted(cfg, "functions.w.timeout", None)
    set_dotted(cfg, "functions.w.events.0", None)
    assert cfg["functions"]["w"] == {"events": [{"http": "GET /x"}]}


def test_redact_keeps_env_references():
    text = "password: hunter2\n  api_key: ${env:KEY}\n  db_token: abc\nname: x"
    assert redact(text) == "password: <redacted>\n  api_key: ${env:KEY}\n  db_token: <redacted>\nname: x"


def test_tools_on_a_project(make_project, tmp_path):
    make_project(CONFIG, files={".env": "SECRET=1\n"})
    tools = ProjectTools(tmp_path)
    project = tools.run("get_project", {}, "aws", "dev")
    assert project.startswith("\nservice: hana-demo") or project.startswith("service: hana-demo")
    assert "\nfiles:\n" in project and "app/handlers.py" in project and "pskit.yml" in project
    assert "hello" in tools.run("read_file", {"path": "app/handlers.py"}, "aws", "dev")
    assert "secrets" in tools.run("read_file", {"path": ".env"}, "aws", "dev")
    assert tools.run("read_file", {"path": "../outside.txt"}, "aws", "dev").startswith("error:")
    assert tools.run("write_file", {"path": ".pskit/x.json", "content": "{}"}, "aws", "dev").startswith("error:")

    out = tools.run("validate", {}, "aws", "dev")
    assert "Configuration is valid." in out and str(tmp_path) not in out

    assert tools.run("write_file", {"path": "app/health.py", "content": "def health(event, ctx):\n    return 'ok'\n"},
                     "aws", "dev") == "ok"
    out = tools.run("set_config", {"path": "functions.health",
                                   "value": {"handler": "app.health.health", "events": [{"http": "GET /health"}]}},
                    "aws", "dev")
    assert out.startswith("ok\n") and "2 function(s)" in out
    assert list((tmp_path / ".pskit" / "studio" / "backups").glob("pskit.*.yml"))  # saved like studio's Save
    assert tools.changed == ["app/health.py", "pskit.yml"]

    out = tools.run("invoke_local", {"function": "health", "method": "GET", "path": "/health"}, "aws", "dev")
    assert '"status": 200' in out and '"ok"' in out


# --------------------------------------------------------------------------- model output parsing


def test_parse_message_tool_calls_and_raw_text():
    content, calls = parse_message({"content": None, "tool_calls": [
        {"id": "c1", "function": {"name": "validate", "arguments": "{\"provider\": \"gcp\"}"}}]})
    assert content == "" and calls == [{"id": "c1", "name": "validate", "arguments": {"provider": "gcp"}}]
    content, calls = parse_message({"content": 'ok\n<tool_call>\n{"name": "get_project", "arguments": {}}\n</tool_call>'})
    assert content == "ok" and calls[0]["name"] == "get_project" and calls[0]["arguments"] == {}
    _, calls = parse_message({"tool_calls": [{"function": {"name": "read_file", "arguments": "{bad"}}]})
    assert "__invalid__" in calls[0]["arguments"]


# --------------------------------------------------------------------------- chat loop


def test_answer_without_tools(tmp_path):
    model = FakeModel([("text", "I'm Hana.")])
    hana = Hana(tmp_path, lambda: model)
    snap = run_turn(hana, "is redis supported on azure?")
    assert snap["status"] == "done" and types_of(snap) == ["user", "answer", "end"]
    system = model.sent[0][0]
    assert system["role"] == "system" and system["content"] == prompt.system_message("aws", "dev", "ask", "Functions",
                                                                                     servers=[])
    assert system["content"].endswith("Never say you cannot run commands. Saved servers: none.")
    assert model.sent[0][1] == {"role": "user", "content": "is redis supported on azure?"}


def test_docs_first_studio_searches_before_the_model_answers(tmp_path):
    model = FakeModel([("text", "Use a shared load balancer [docs/onprem/load-balancers.md#x].")])
    snap = run_turn(Hana(tmp_path, lambda: model), "how do I put one load balancer in front of two clusters?")
    assert snap["status"] == "done" and types_of(snap) == ["user", "tool_call", "tool_result", "answer", "end"]
    call = next(e for e in snap["events"] if e["type"] == "tool_call")
    assert call["name"] == "search_docs" and call["args"] == {
        "query": "how do I put one load balancer in front of two clusters?"}
    sent = model.sent[0]  # the model sees the search call and its excerpts before its first answer
    assert sent[2]["tool_calls"][0]["function"]["name"] == "search_docs"
    assert sent[3]["role"] == "tool" and sent[3]["content"].startswith("[")
    assert sent[3]["content"].count("\n\n[") == hana_session.PRE_SEARCH_CARDS - 1


def test_docs_first_short_reply_searches_with_the_previous_question(tmp_path):
    model = FakeModel([("text", "first"), ("text", "second")])
    hana = Hana(tmp_path, lambda: model)
    first = run_turn(hana, "how do I scale postgres with read replicas?")
    second = run_turn(hana, "ok", sid=first["session_id"])
    call = next(e for e in second["events"] if e["type"] == "tool_call")
    assert call["args"] == {"query": "how do I scale postgres with read replicas? ok"}


def test_plan_approved_then_changes_run(make_project, tmp_path):
    make_project(CONFIG)
    model = FakeModel([
        ("call", "propose_plan", {"steps": ["Write app/health.py", "Validate"]}),
        ("call", "write_file", {"path": "app/health.py", "content": "def health(e, c):\n    return 'ok'\n"}),
        ("call", "validate", {}),
        ("text", "Done."),
    ])
    hana = Hana(tmp_path, lambda: model)
    asked = []

    def answers(pending):
        asked.append(pending["kind"])
        return "approve", "use 4 workers"

    snap = run_turn(hana, "add a health endpoint", answers=answers)
    assert snap["status"] == "done" and asked == ["plan"]  # the write after the approved plan asks nothing
    assert (tmp_path / "app" / "health.py").exists()
    assert snap["changed"] == ["app/health.py"]
    # what the model saw: the exact result format of the training data
    tool_results = [m for m in model.sent[-1] if m["role"] == "tool"]
    assert tool_results[0] == {"role": "tool", "tool_call_id": "call_01", "name": "propose_plan",
                               "content": json.dumps({"decision": "approved", "note": "use 4 workers"})}
    assert tool_results[1]["content"] == "ok"
    assert "Configuration is valid." in tool_results[2]["content"]
    call_msg = model.sent[1][-2]
    assert call_msg["role"] == "assistant"
    assert call_msg["tool_calls"][0]["function"] == {"name": "propose_plan",
                                                     "arguments": json.dumps({"steps": ["Write app/health.py", "Validate"]})}


def test_auto_mode_approves_the_plan(make_project, tmp_path):
    make_project(CONFIG)
    model = FakeModel([("call", "propose_plan", {"steps": ["x"]}),
                       ("call", "write_file", {"path": "notes.txt", "content": "hi"}), ("text", "ok")])
    snap = run_turn(Hana(tmp_path, lambda: model), "write notes", mode="auto")
    assert snap["status"] == "done" and (tmp_path / "notes.txt").read_text() == "hi"
    assert model.sent[1][-1]["content"] == json.dumps({"decision": "auto_approved"})


def test_change_without_a_plan_needs_the_user(make_project, tmp_path):
    make_project(CONFIG)
    model = FakeModel([("call", "write_file", {"path": "notes.txt", "content": "hi"}), ("text", "Okay, I stopped.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "write notes", answers=lambda p: ("reject", ""))
    assert snap["status"] == "done" and not (tmp_path / "notes.txt").exists()
    assert model.sent[1][-1]["content"].startswith("rejected")
    waiting = [e for e in snap["events"] if e["type"] == "waiting"]
    assert waiting[0]["kind"] == "step" and waiting[0]["tool"] == "write_file"


def test_ask_user_and_follow_up_keeps_history(make_project, tmp_path):
    make_project(CONFIG)
    model = FakeModel([("call", "ask_user", {"question": "Which server?", "options": ["app-1", "db-1"]}),
                       ("text", "Using app-1."), ("text", "Still app-1.")])
    hana = Hana(tmp_path, lambda: model)
    snap = run_turn(hana, "which target?", answers=lambda p: ("answer", p["options"][0]))
    assert model.sent[1][-1] == {"role": "tool", "tool_call_id": "call_01", "name": "ask_user", "content": "app-1"}
    run_turn(hana, "and again?", sid=snap["session_id"])
    assert [m["role"] for m in model.sent[2]] == ["system", "user", "assistant", "tool", "assistant", "user"]
    # the chat is saved and comes back after a studio restart
    again = Hana(tmp_path, lambda: model)
    assert again.get(snap["session_id"]).display[0] == {"role": "user", "text": "which target?", "m": 0}


def test_stop_while_waiting(make_project, tmp_path):
    make_project(CONFIG)
    model = FakeModel([("call", "propose_plan", {"steps": ["x"]})])
    hana = Hana(tmp_path, lambda: model)
    turn = hana.send(None, "change it", {"provider": "aws", "stage": "dev", "mode": "ask", "page": "none"})
    for _ in range(200):
        if turn.snapshot()["pending"]:
            break
        time.sleep(0.02)
    turn.stop()
    for _ in range(200):
        if turn.status == "stopped":
            break
        time.sleep(0.02)
    assert turn.status == "stopped"
    roles = [m["role"] for m in turn.session.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]  # the open call got a result


def test_one_turn_at_a_time(tmp_path):
    gate = threading.Event()

    class Slow(FakeModel):
        def chat(self, messages, tools, max_tokens=900):
            gate.wait(10)
            return {"content": "hi", "tool_calls": [], "usage": {}}

    hana = Hana(tmp_path, lambda: Slow([]))
    turn = hana.send(None, "one", {"mode": "ask"})
    with pytest.raises(Exception, match="still working"):
        hana.send(turn.session.id, "two", {"mode": "ask"})
    gate.set()


def test_fit_shortens_old_results_then_drops_old_exchanges():
    system = {"role": "system", "content": "s"}
    old = [{"role": "user", "content": "q1"}, {"role": "tool", "content": "x" * 5000}, {"role": "assistant", "content": "a1"}]
    new = [{"role": "user", "content": "q2"}]
    out = fit([system, *old, *new], limit=2000, keep_from=4)
    assert out[0] == system and out[-1] == new[0]
    assert len(json.dumps(out)) <= 2000 or len(out) == 2
    out = fit([system, *old, *new], limit=300, keep_from=4)
    assert out == [system, *new]


# --------------------------------------------------------------------------- API


@pytest.fixture
def studio(make_project, tmp_path):
    make_project(CONFIG)
    httpd = make_server(tmp_path, "127.0.0.1", 0, token=TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path, httpd
    httpd.shutdown()
    httpd.server_close()


def test_api_setup_and_chat(studio, monkeypatch):
    base, root, httpd = studio
    from py_serverless_kit.studio.hana import runtime as rt

    monkeypatch.setattr(rt.Runtime, "docker_info", lambda self: {"available": False, "error": "no docker here"})
    status, body = call(base, "GET", "/api/hana")
    assert status == 200 and body["runtime"]["configured"] is False and body["sessions"] == []
    status, body = call(base, "POST", "/api/hana/messages", {"text": "hi", "env": {}})
    assert status == 409 and body["code"] == "hana-setup"
    status, body = call(base, "POST", "/api/hana/endpoint", {"url": "file:///etc/passwd"})
    assert status == 400
    status, body = call(base, "POST", "/api/hana/endpoint", {"url": "http://127.0.0.1:9/v1"})
    assert status == 200 and body["configured"] and body["url"] == "http://127.0.0.1:9" and body["ready"] is False
    assert json.loads((root / ".pskit" / "studio" / "hana.json").read_text())["target"] == "endpoint"

    model = FakeModel([("call", "propose_plan", {"steps": ["a"]}), ("text", "Plan rejected, nothing changed.")])
    runtime, chat = httpd.studio.hana()
    chat.model_factory = lambda: model
    status, body = call(base, "POST", "/api/hana/messages",
                        {"text": "change it", "env": {"provider": "aws", "stage": "dev", "mode": "ask", "page": "YAML"}})
    assert status == 202
    turn_id = body["turn_id"]
    for _ in range(200):
        _, snap = call(base, "GET", f"/api/hana/turns/{turn_id}")
        if snap["pending"]:
            break
        time.sleep(0.02)
    pid = snap["pending"]["id"]
    assert call(base, "POST", f"/api/hana/turns/{turn_id}/answer", {"pending_id": pid, "decision": "maybe"})[0] == 400
    assert call(base, "POST", f"/api/hana/turns/{turn_id}/answer",
                {"pending_id": pid, "decision": "reject", "text": "not now"})[0] == 200
    for _ in range(200):
        _, snap = call(base, "GET", f"/api/hana/turns/{turn_id}")
        if snap["status"] == "done":
            break
        time.sleep(0.02)
    assert snap["status"] == "done"
    assert model.sent[1][-1]["content"] == json.dumps({"decision": "rejected", "note": "not now"})
    _, listing = call(base, "GET", "/api/hana")
    sid = listing["sessions"][0]["id"]
    _, detail = call(base, "GET", f"/api/hana/sessions/{sid}")
    assert detail["display"][0] == {"role": "user", "text": "change it", "m": 0} and detail["turn_id"] is None
    assert call(base, "DELETE", f"/api/hana/sessions/{sid}")[0] == 200
    assert call(base, "GET", f"/api/hana/sessions/{sid}")[0] == 404
    assert call(base, "POST", "/api/hana/install", {"target": "local", "image": "bad image;rm"})[0] == 400


def test_local_install_runs_the_image_on_loopback(tmp_path, monkeypatch):
    from py_serverless_kit.studio.hana import runtime as rt

    seen: List[List[str]] = []

    class Proc:
        def __init__(self, code=0, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def runner(cmd, timeout):
        seen.append(cmd)
        if cmd[1] == "version":
            return Proc(0, "29.0")
        if cmd[1:3] == ["container", "inspect"]:
            return Proc(1)
        return Proc(0)

    monkeypatch.setattr(rt.Runtime, "_stream", staticmethod(lambda cmd, emit: 0))
    monkeypatch.setattr(rt, "wait_ready", lambda url, timeout, emit=None: True)
    monkeypatch.setattr(rt, "_free_port", lambda preferred=rt.DEFAULT_PORT: 8790)

    class Job:
        lines: List[str] = []

        def emit(self, text, stream="stdout"):
            self.lines.append(text)

    runtime = rt.Runtime(tmp_path, runner=runner)
    assert runtime.install_local(Job(), "example/hana:1") == 0
    run = next(c for c in seen if c[1] == "run")
    assert "127.0.0.1:8790:8080" in run and run[-1] == "example/hana:1" and "--restart" in run
    assert runtime.config() == {"target": "local", "url": "http://127.0.0.1:8790", "image": "example/hana:1"}


# --------------------------------------------------------------------------- studio actions (servers, services)

PASTED = (
    'app_url = "http://203.0.113.65:8080"\n'
    'pem_file = "./onprem-demo.pem"\n'
    'public_ip = "203.0.113.65"\n'
    'ssh_command = "ssh -i onprem-demo.pem ubuntu@203.0.113.65"\n'
    'ssh_user = "ubuntu"\n'
    r"pem located in:C:\keys\demo\onprem-demo.pem" "\n"
    "i have this  create it"
)


def test_server_details_from_terraform_outputs(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    found = detect(PASTED, tmp_path, [], provider="aws")
    assert found and found["direct"]
    assert sub(found["card"], kind="server", mode="add", name="server-1", host="203.0.113.65", user="ubuntu",
               port=22, identity_file=r"C:\keys\demo\onprem-demo.pem")
    card = detect("can u create server for me", tmp_path, [], provider="aws")["card"]
    assert card["kind"] == "server" and card["host"] == ""
    card = detect("ssh -p 2222 -i ~/k.pem root@app.example.com, add it as gpu-box", tmp_path, [])["card"]
    assert sub(card, name="gpu-box", host="app.example.com", user="root", port=2222, identity_file="~/k.pem")


def sub(card: Dict[str, Any], **want: Any) -> bool:
    got = {k: card.get(k) for k in want}
    assert got == want, got
    return True


def test_the_servers_conversation(tmp_path):
    """The conversation that went wrong: list, add, add folders to "this server", re-paste, remove."""
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    history: List[Dict[str, Any]] = []

    def ask(text):
        found = detect(text, tmp_path, history, provider="onprem")
        history.append({"role": "user", "text": text})
        if found:
            history.append({"role": "assistant", "text": found["reply"]})
            if found["card"]:
                history.append({"role": "action", "card": found["card"]})
        return found

    found = ask("how many server arethere in this project")
    assert found["card"] is None and "no saved servers" in found["reply"]
    assert sub(ask(PASTED)["card"], kind="server", mode="add", name="server-1")
    # not saved yet: "this server" is the card above, now with the folder fields
    found = ask("for this server can u also add the home path and data path")
    assert sub(found["card"], mode="add", name="server-1", host="203.0.113.65", focus=["home", "data_dir"])

    save_server(tmp_path, "server-1", {"host": "203.0.113.65", "user": "ubuntu"})  # the user clicked Save & test
    history.append({"role": "note", "text": "Saved server **server-1** (ubuntu@203.0.113.65:22). SSH test passed."})
    found = ask("how many servers are there in this project")
    assert "**1** (one) saved server" in found["reply"] and "server-1" in found["reply"]
    assert sub(ask("for this server can u also add the home path and data path")["card"], mode="edit", name="server-1")
    assert sub(ask("set home to /opt/pskit and data to /data/pskit for server-1")["card"],
               mode="edit", home="/opt/pskit", data_dir="/data/pskit")
    found = ask(PASTED)  # the same machine again: update, not a duplicate
    assert "already saved as **server-1**" in found["reply"] and found["card"]["mode"] == "edit"
    assert ask("create a new server for me")["card"]["name"] == "server-2"
    assert ask("remove the server-1")["card"] == {"kind": "server-remove", "name": "server-1",
                                                  "label": "ubuntu@203.0.113.65:22"}
    assert "nothing to remove" in detect("remove server", tmp_path / "empty", [])["reply"]


def test_detect_leaves_project_work_to_the_model(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    for text in ("add a GET /health endpoint", "how do I add a schedule in studio?", "what is a queue trigger?",
                 "is redis supported on azure?"):
        assert detect(text, tmp_path, [], provider="aws") is None, text
    assert "Servers and on-prem services" in detect("do u have tools ?", tmp_path, [])["reply"]


def test_service_card_on_a_saved_server(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    save_server(tmp_path, "app-1", {"host": "192.0.2.10", "user": "ubuntu"})
    card = detect("create redis on app-1 as cache", tmp_path, [], provider="aws")["card"]
    assert card == {"kind": "service", "service": "redis", "role": "cache", "key": "redis-1", "server": "app-1",
                    "servers": ["app-1"], "cluster": ""}
    found = detect("what services do i have", tmp_path, [])
    assert found["card"] is None and "no on-prem services" in found["reply"]
    card = detect("create a postgres database", tmp_path, [], provider="onprem")["card"]
    assert card["service"] == "postgres" and card["role"] == "database" and card["server"] == "app-1"


def test_action_turn_answers_without_the_model(tmp_path):
    model = FakeModel([])  # any call would fail: pop from an empty list
    hana = Hana(tmp_path, lambda: model)
    snap = run_turn(hana, PASTED, first="studio")  # the "studio answers first" setting
    assert snap["status"] == "done" and types_of(snap) == ["user", "answer", "action", "end"]
    session = hana.get(snap["session_id"])
    assert session.display[-1]["role"] == "action" and session.display[-1]["card"]["host"] == "203.0.113.65"
    hana.note(session.id, "Saved server **server-1**. SSH test passed.")
    assert session.messages[-1] == {"role": "assistant", "content": "Saved server **server-1**. SSH test passed."}
    assert Hana(tmp_path, lambda: model).get(session.id).display[-1]["role"] == "note"


# --------------------------------------------------------------------------- full removal, optional fields, HF

REMOVE_CONFIG = """
service: demo
provider: {name: onprem}
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
  bye: {handler: app.handlers.bye}
  solo: {handler: app.only.solo}
  step: {handler: app.handlers.bye}
workflows:
  flow: {engine: embedded, start_at: Go, states: {Go: {type: task, function: step, end: true}}}
"""


def _removal_project(tmp_path):
    (tmp_path / "pskit.yml").write_text(REMOVE_CONFIG)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text(
        "import json\n\n\n@decorated\ndef hello(event, ctx):\n    return 'hi'\n\n\ndef bye(event, ctx):\n    return 'bye'\n")
    (tmp_path / "app" / "only.py").write_text("import os\n\n\ndef solo(event, ctx):\n    return 1\n")


def test_remove_a_function_takes_the_yml_entry_and_its_code(tmp_path):
    from py_serverless_kit.studio.hana import edits

    _removal_project(tmp_path)
    plan = edits.plan_removal(tmp_path, "function", "hello")
    assert plan["code"]["action"] == "delete-function" and plan["code"]["lines"] == [4, 6]  # the decorator too
    out = edits.remove(tmp_path, "function", "hello")
    assert out["changed"] == ["pskit.yml", "app/handlers.py"] and out["code"] == "function removed"
    assert "hello" not in edits.names(edits.raw_config(tmp_path), "function")
    code = (tmp_path / "app" / "handlers.py").read_text()
    assert "def hello" not in code and "@decorated" not in code and "def bye" in code
    assert list((tmp_path / ".pskit" / "studio" / "backups").glob("pskit.*.yml"))

    assert edits.remove(tmp_path, "function", "solo")["code"] == "deleted"  # nothing else in the file
    assert not (tmp_path / "app" / "only.py").exists()
    with pytest.raises(Exception, match="workflow flow still runs step"):  # a workflow uses it: not removed
        edits.remove(tmp_path, "function", "step")
    with pytest.raises(Exception, match="no function 'hello'"):  # already gone
        edits.plan_removal(tmp_path, "function", "hello")
    assert edits.remove(tmp_path, "workflow", "flow")["changed"] == ["pskit.yml"]
    assert edits.remove(tmp_path, "function", "step", delete_code=False)["code"] == "kept"


def test_remove_requests_in_the_chat(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    _removal_project(tmp_path)
    found = detect("remove the hello function", tmp_path, [])
    assert found["card"]["kind"] == "item-remove" and found["card"]["item_kind"] == "function"
    assert "`functions.hello` from pskit.yml" in found["reply"] and "`hello()` from `app/handlers.py`" in found["reply"]
    assert "**step**: not removed, workflow flow still runs step" in detect("remove function step", tmp_path, [])["reply"]
    assert "no function **hello2**" in detect("remove the function hello2", tmp_path, [])["reply"]
    assert "Which function" in detect("remove function", tmp_path, [])["reply"]


def test_server_optional_fields_and_password_never_kept(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect, redact_password

    card = detect("add server 203.0.113.7 user is ubuntu, ssh port 2222, with sudo, home /srv/pskit, "
                  "data /data/pskit, bind 10.0.0.5, description: lab box", tmp_path, [])["card"]
    assert sub(card, host="203.0.113.7", user="ubuntu", port=2222, sudo=True, home="/srv/pskit",
               data_dir="/data/pskit", bind="10.0.0.5", description="lab box")
    history = [{"role": "action", "card": card}]
    card = detect("for this server also add a description and use sudo", tmp_path, history)["card"]
    assert sub(card, description="lab box", sudo=True, focus=["sudo", "description"])  # no invented value
    text = redact_password("change it to log in with a password, the password is hunter2")
    assert "hunter2" not in text
    found = detect("add server 192.0.2.4 with a password login", tmp_path, [])
    assert found["card"]["auth"] == "password"


def test_removed_names_are_not_acted_on(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    history = [{"role": "note", "text": "Removed saved server **server-1** (ubuntu@192.0.2.1:22)."},
               {"role": "action", "card": {"kind": "server-remove", "name": "server-1", "label": "x"}}]
    for text in ("remove server-1", "what should I do with server-1"):
        assert "isn't a saved server anymore" in detect(text, tmp_path, history)["reply"]


def test_delete_all_chats(tmp_path):
    hana = Hana(tmp_path, lambda: FakeModel([("text", "a"), ("text", "b")]))
    run_turn(hana, "one")
    run_turn(hana, "two")
    assert len(hana.list()) == 2
    assert hana.delete_all() == {"deleted": 2}
    assert hana.list() == [] and not list((tmp_path / ".pskit" / "studio" / "hana" / "sessions").glob("*.json"))


def test_password_typed_in_the_chat_is_not_stored(tmp_path):
    model = FakeModel([("text", "ok")])
    hana = Hana(tmp_path, lambda: model)
    snap = run_turn(hana, "my ssh password is hunter2, what now?")
    assert "hunter2" not in json.dumps(hana.get(snap["session_id"]).to_json()) and "hunter2" not in json.dumps(model.sent)


def test_huggingface_runtime(tmp_path, monkeypatch):
    import types

    from py_serverless_kit.studio.hana import runtime as rt

    seen: Dict[str, Any] = {}

    class FakeLlama:
        def __init__(self, model_path, n_ctx, verbose):
            seen["path"] = model_path

        def create_chat_completion(self, messages, tools, temperature, max_tokens):
            seen["messages"] = messages
            return {"choices": [{"message": {"content": '<tool_call>\n{"name": "get_project", "arguments": {}}\n</tool_call>'}}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    monkeypatch.setattr(rt.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(rt, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(rt.Runtime, "_download", staticmethod(lambda url, path, emit: path.write_bytes(b"gguf")))

    class Job:
        def emit(self, text, stream="stdout"):
            pass

    runtime = rt.Runtime(tmp_path)
    assert runtime.install_hf(Job(), "hana-pskit-1.5b-q4_k_m.gguf") == 0
    assert runtime.config()["target"] == "huggingface" and seen["path"].endswith("hana-pskit-1.5b-q4_k_m.gguf")
    status = runtime.status()
    assert status["configured"] and status["ready"] and status["target"] == "huggingface"
    model = runtime.model()
    out = model.chat([{"role": "system", "content": "s"}, {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "validate", "arguments": "{\"provider\": \"aws\"}"}}]}],
        prompt.TOOLS)
    assert out["tool_calls"][0]["name"] == "get_project"  # the raw <tool_call> text is parsed
    # the template gets the arguments as an object, as in training
    assert seen["messages"][1]["tool_calls"][0]["function"]["arguments"] == {"provider": "aws"}
    assert runtime.install_hf(Job(), "../../etc/passwd") == 1
    runtime.stop()
    assert runtime.config() == {} and (tmp_path / "models" / "hana-pskit-1.5b-q4_k_m.gguf").exists()


# --------------------------------------------------------------------------- several items in one message

FOUR_SERVERS = r'''AZ_VM_01_4cpu

app_url = "http://203.0.113.36:8080"
pem_file = "C:\keys\azure-4cpu-1\onprem-4cpu-1.pem"
public_ip = "203.0.113.36"
ssh_command = "ssh -i onprem-4cpu-1.pem azureuser@203.0.113.36"
ssh_user = "azureuser"


AZ_VM_01_2cpu

app_url = "http://198.51.100.10:8080"
pem_file = "C:\keys\azure-small\onprem-demo.pem"
public_ip = "198.51.100.10"
ssh_command = "ssh -i onprem-demo.pem azureuser@198.51.100.10"
ssh_user = "azureuser"


AZ_VM_02_2cpu

app_url = "http://198.51.100.51:8080"
pem_file = "C:\keys\azure-small-2\onprem-demo-2.pem"
public_ip = "198.51.100.51"
ssh_command = "ssh -i onprem-demo-2.pem azureuser@198.51.100.51"
ssh_user = "azureuser"


AZ_VM_04_2cpu

app_url = "http://192.0.2.117:8080"
pem_file = "C:\keys\azure-small-4\onprem-demo-4.pem"
public_ip = "192.0.2.117"
ssh_command = "ssh -i onprem-demo-4.pem azureuser@192.0.2.117"
ssh_user = "azureuser

add this for severs'''


def test_four_servers_in_one_message_get_four_cards(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    found = detect(FOUR_SERVERS, tmp_path, [], provider="onprem")
    cards = found["cards"]
    assert [c["name"] for c in cards] == ["AZ_VM_01_4cpu", "AZ_VM_01_2cpu", "AZ_VM_02_2cpu", "AZ_VM_04_2cpu"]
    assert [c["host"] for c in cards] == ["203.0.113.36", "198.51.100.10", "198.51.100.51", "192.0.2.117"]
    assert all(c["user"] == "azureuser" and c["mode"] == "add" for c in cards)
    assert cards[2]["identity_file"] == r"C:\keys\azure-small-2\onprem-demo-2.pem"
    assert "**4 servers**" in found["reply"]

    save_server(tmp_path, "AZ_VM_01_2cpu", {"host": "198.51.100.10", "user": "azureuser"})
    cards = detect(FOUR_SERVERS, tmp_path, [], provider="onprem")["cards"]
    assert [c["mode"] for c in cards] == ["add", "edit", "add", "add"]  # the saved one is updated, not duplicated

    cards = detect("ssh -i a.pem ubuntu@192.0.2.1\nssh -i b.pem ubuntu@192.0.2.2\nadd both", tmp_path, [])["cards"]
    assert [(c["name"], c["host"]) for c in cards] == [("server-1", "192.0.2.1"), ("server-2", "192.0.2.2")]


def test_several_services_and_removals_in_one_message(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana import actions

    _removal_project(tmp_path)
    save_server(tmp_path, "app-1", {"host": "192.0.2.50", "user": "ubuntu"})
    save_server(tmp_path, "app-2", {"host": "192.0.2.51", "user": "ubuntu"})
    cards = actions.detect("create redis and postgres on app-1", tmp_path, [])["cards"]
    assert [(c["service"], c["key"], c["server"]) for c in cards] == [("redis", "redis-1", "app-1"),
                                                                       ("postgres", "postgres-1", "app-1")]
    cards = actions.detect("remove app-1 and app-2", tmp_path, [])["cards"]
    assert [c["name"] for c in cards] == ["app-1", "app-2"] and cards[0]["kind"] == "server-remove"
    found = actions.detect("remove functions hello and solo", tmp_path, [])
    assert [c["name"] for c in found["cards"]] == ["hello", "solo"]
    found = actions.detect("remove all functions", tmp_path, [])
    assert [c["name"] for c in found["cards"]] == ["hello", "bye", "solo"]  # step: a workflow runs it
    assert "**step**: not removed" in found["reply"]
    assert "doesn't create virtual machines" in actions.detect("create a server on aws", tmp_path, [])["reply"]


def test_cards_all_reach_the_chat(tmp_path):
    hana = Hana(tmp_path, lambda: FakeModel([]))
    snap = run_turn(hana, FOUR_SERVERS, first="studio")
    assert types_of(snap) == ["user", "answer", "action", "action", "action", "action", "end"]
    assert [d["card"]["name"] for d in hana.get(snap["session_id"]).display if d["role"] == "action"] == [
        "AZ_VM_01_4cpu", "AZ_VM_01_2cpu", "AZ_VM_02_2cpu", "AZ_VM_04_2cpu"]


def test_edit_a_message_replays_from_there(tmp_path):
    model = FakeModel([("text", "first answer"), ("text", "second answer"), ("text", "edited answer")])
    hana = Hana(tmp_path, lambda: model)
    snap = run_turn(hana, "hello")
    run_turn(hana, "tell me about queues", sid=snap["session_id"])
    session = hana.get(snap["session_id"])
    assert [d["text"] for d in session.display] == ["hello", "first answer", "tell me about queues", "second answer"]
    turn = hana.edit(session.id, 2, "tell me about schedules", {"mode": "ask"})
    for _ in range(300):
        if turn.status == "done":
            break
        time.sleep(0.02)
    assert [d["text"] for d in session.display] == ["hello", "first answer", "tell me about schedules", "edited answer"]
    assert [m.get("content") for m in session.messages] == ["hello", "first answer", "tell me about schedules",
                                                            "edited answer"]
    assert model.sent[-1][-1] == {"role": "user", "content": "tell me about schedules"}
    with pytest.raises(Exception, match="not one of your messages"):
        hana.edit(session.id, 1, "x", {"mode": "ask"})


def test_set_config_refuses_invented_keys_and_missing_deletes(tmp_path):
    from py_serverless_kit.studio.hana.tools import ProjectTools

    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "handlers.py").write_text("def hello(event, ctx):\n    return 'hi'\n")
    before = (tmp_path / "pskit.yml").read_bytes()
    tools = ProjectTools(tmp_path)
    out = tools.run("set_config", {"path": "functions.hello.foo_bar", "value": 5}, "aws", "dev")
    assert out.startswith("error: functions.hello.foo_bar is not a pskit.yml option") and "undone" in out
    out = tools.run("set_config", {"path": "functions.all", "value": None}, "aws", "dev")
    assert out == "error: functions.all doesn't exist in pskit.yml, so there is nothing to delete"
    assert (tmp_path / "pskit.yml").read_bytes() == before and tools.changed == []


def test_clusters_load_balancers_deploy(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    for i, name in enumerate(["vm-a", "vm-b", "vm-c"]):
        save_server(tmp_path, name, {"host": f"192.0.2.{10 + i}", "user": "ubuntu"})
    found = detect("create a cluster with 2 server and another cluste with 1 server", tmp_path, [], provider="onprem")
    assert [(c["name"], c["master"], c["workers"]) for c in found["cards"]] == [
        ("cluster-1", "vm-a", ["vm-b"]), ("cluster-2", "vm-c", [])]
    found = detect("create a cluster with 3 servers", tmp_path, [], provider="onprem")
    assert found["cards"][0]["workers"] == ["vm-b", "vm-c"]
    card = detect("i want load balancer on vm-c", tmp_path, [], provider="onprem")["cards"][0]
    assert card["kind"] == "balancer" and card["server"] == "vm-c" and card["port"] == 80
    assert "provider.options.balancer: lb-1" in detect("can u create a load balancer", tmp_path, [])["reply"]
    assert "round_robin" in detect("what algo rights we have", tmp_path, [])["reply"]
    found = detect("can u able to deploy the code", tmp_path, [], provider="onprem", stage="dev")
    assert found["cards"][0] == {"kind": "deploy", "provider": "onprem", "stage": "dev", "server": "vm-a", "cluster": "",
                                 "servers": ["vm-a", "vm-b", "vm-c"], "clusters": []}
    assert detect("deploy code to vm-b", tmp_path, [], provider="onprem")["cards"][0]["server"] == "vm-b"
    reply = detect("how do I deploy?", tmp_path, [], provider="onprem", stage="dev")["reply"]
    assert "I don't deploy myself" in reply and "pskit deploy -p onprem -s dev --server vm-a" in reply
    assert "stage (**prod**)" in detect("how do I deploy to prod?", tmp_path, [], provider="aws")["reply"]
    assert "(four)" not in detect("how many servers", tmp_path, [])["reply"]
    assert "(three) saved servers" in detect("how many servers", tmp_path, [])["reply"]


def test_identity_vague_and_project_questions(tmp_path):
    from py_serverless_kit.studio.hana.actions import IDENTITY, VAGUE, detect

    (tmp_path / "pskit.yml").write_text(CONFIG)
    for text in ("tum kon ho gi", "u are name is hana not naseeha", "who are u", "aap kaun ho", "who made you?"):
        assert detect(text, tmp_path, [])["reply"].startswith(IDENTITY), text
    assert "(I answer in English.)" in detect("tum kon ho gi", tmp_path, [])["reply"]
    for text in ("what", "?", "hmm"):
        assert detect(text, tmp_path, [])["reply"] == VAGUE
    assert detect("ok", tmp_path, []) is None  # may answer Hana's question
    reply = detect("what this project is for", tmp_path, [])["reply"]
    assert "**hana-demo**" in reply and "- **hello**: `app.handlers.hello`, http `GET /hello`" in reply
    assert "answer best in English" in detect("kya haal hai bhai", tmp_path, [])["reply"]


def test_stop_can_also_delete_the_image(tmp_path):
    from py_serverless_kit.studio.hana import runtime as rt

    seen: List[List[str]] = []

    class Proc:
        returncode, stdout, stderr = 0, "", ""

    def runner(cmd, timeout):
        seen.append(cmd)
        return Proc()

    runtime = rt.Runtime(tmp_path, runner=runner)
    runtime.save({"target": "local", "url": "http://127.0.0.1:8790", "image": "example/hana:1"})
    out = runtime.stop(remove_data=False)
    assert ["docker", "image", "rm", "example/hana:1"] not in seen and out["removed"] == ["container pskit-hana"]
    runtime.save({"target": "local", "url": "http://127.0.0.1:8790", "image": "example/hana:1"})
    out = runtime.stop(remove_data=True)
    assert ["docker", "image", "rm", "example/hana:1"] in seen and "image example/hana:1" in out["removed"]
    assert runtime.config() == {}


ROUND5_CONFIG = """
service: my-service
provider: {name: onprem, runtime: python3.12}
functions:
  hello: {handler: app.handlers.hello, description: Says hello, events: [{http: GET /hello}]}
  get-item: {handler: app.handlers.get_item, events: [{http: "GET /items/{id}"}]}
  create-item: {handler: app.handlers.create_item, events: [{http: POST /items}]}
"""


def test_lists_service_question_workflow_and_load(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    save_server(tmp_path, "app-1", {"host": "192.0.2.10", "user": "ubuntu"})
    for text in ("list out the funtions", "in this projects funtions list out", "how many functions"):
        reply = detect(text, tmp_path, [], provider="onprem")["reply"]
        assert "**3** (three) functions" in reply and "- **get-item**: `app.handlers.get_item`, http `GET /items/{id}`" in reply
    assert "Which one do you mean?" in detect("create a service for me", tmp_path, [])["reply"]
    assert "**my-service**" in detect("what is this project for", tmp_path, [])["reply"]
    for text in ("create load", "create a load balncer"):
        assert detect(text, tmp_path, [], provider="onprem")["cards"][0]["kind"] == "balancer"
    card = detect("can u creare work flow", tmp_path, [])["cards"][0]
    assert card == {"kind": "workflow", "name": "workflow-1", "steps": [], "functions": ["hello", "get-item", "create-item"],
                    "create": [], "wait": 0}
    card = detect("create a workflow named orders with create-item then get-item", tmp_path, [])["cards"][0]
    assert card["name"] == "orders" and card["steps"] == ["create-item", "get-item"]
    assert "no workflows yet" in detect("run the workflow", tmp_path, [])["reply"]
    assert detect("what is network map", tmp_path, []) is None  # a pskit question: the model answers


def test_create_workflow_writes_a_valid_sequence(tmp_path):
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text(
        "def hello(e, c):\n    return 1\n\n\ndef get_item(e, c):\n    return 2\n\n\ndef create_item(e, c):\n    return 3\n")
    out = edits.create_workflow(tmp_path, "orders", ["create-item", "get-item", "create-item"])
    assert out["states"] == ["CreateItem", "GetItem", "CreateItem2"] and "Configuration is valid." in out["validate"]
    wf = edits.raw_config(tmp_path)["workflows"]["orders"]
    assert wf["start_at"] == "CreateItem" and wf["states"]["GetItem"] == {"type": "task", "function": "get-item",
                                                                          "next": "CreateItem2"}
    assert wf["states"]["CreateItem2"]["end"] is True
    with pytest.raises(Exception, match="already a workflow"):
        edits.create_workflow(tmp_path, "orders", ["hello"])
    with pytest.raises(Exception, match="unknown: nope"):
        edits.create_workflow(tmp_path, "other", ["nope"])
    assert "**orders**: create-item → get-item → create-item" in detect("show workflows", tmp_path, [])["reply"]


def test_folder_paths_are_taken_whole(tmp_path):
    from py_serverless_kit.studio.hana.actions import _folders, detect

    card = detect("create server name test-server-001  ,make root to /home/azureuser/  make data to /home/azureuser/",
                  tmp_path, [])["card"]
    assert sub(card, name="test-server-001", user="azureuser", home="/home/azureuser", data_dir="/home/azureuser")
    assert _folders("home path /srv/pskit/ data folder /mnt/data") == {"home": "/srv/pskit", "data_dir": "/mnt/data"}
    assert _folders("data dir: /var/lib/pskit, root path = /home/azureuser") == {
        "home": "/home/azureuser", "data_dir": "/var/lib/pskit"}
    assert _folders("add server 203.0.113.7 home /home/ubuntu") == {"home": "/home/ubuntu"}


def test_instructions_after_the_blocks_apply_to_every_server(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    text = FOUR_SERVERS.replace("add this for severs", "add this server in all server add home path as /home/azureuser/  "
                                "and data path as /home/azureuser/\nand Listen address  on 0.0.0.0 in all servers")
    found = detect(text, tmp_path, [], provider="onprem")
    assert len(found["cards"]) == 4
    for card in found["cards"]:
        assert sub(card, user="azureuser", home="/home/azureuser", data_dir="/home/azureuser", bind="0.0.0.0", port=22)
    assert [c["identity_file"].rsplit("\\", 1)[1] for c in found["cards"]] == [
        "onprem-4cpu-1.pem", "onprem-demo.pem", "onprem-demo-2.pem", "onprem-demo-4.pem"]
    assert "On every server: home folder `/home/azureuser`, data folder `/home/azureuser`, listen address `0.0.0.0`." \
        in found["reply"]


def test_typos_corrections_and_one_server_questions(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    save_server(tmp_path, "AZ_VM_01_2cpu", {"host": "192.0.2.10", "user": "azureuser", "home": "/home/azureuser",
                                            "data_dir": "/home/azureuser"})
    for text in ("lst all servs", "list out all severs"):
        assert "**1** (one) saved server" in detect(text, tmp_path, [], provider="onprem")["reply"], text
    history = [{"role": "user", "text": "list all"}, {"role": "assistant", "text": "?"}]
    assert "**1** (one) saved server" in detect("i mean servers", tmp_path, history, provider="onprem")["reply"]
    reply = detect("what is root path in AZ_VM_01_2cpu", tmp_path, [])["reply"]
    assert "- home (root) folder: `/home/azureuser`" in reply and "data folder" not in reply.split("To change")[0]
    assert "- SSH user: `azureuser`" in detect("show AZ_VM_01_2cpu details", tmp_path, [])["reply"]


def test_create_functions_and_a_workflow_with_waits(tmp_path):
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    found = detect("forst create step-01 step-02 step-03 funtions and create a work flow attach to this afte every "
                   "funtin make deloy of 10 sec", tmp_path, [])
    card = found["cards"][0]
    assert card["create"] == ["step-01", "step-02", "step-03"] and card["steps"] == ["step-01", "step-02", "step-03"]
    assert card["wait"] == 10
    assert "step-01 → wait 10 s → step-02 → wait 10 s → step-03" in found["reply"]
    assert "Here is what I understood" in found["reply"]
    card = detect("create functions named alpha, beta and then a workflow called pipe with a 2 min wait between them",
                  tmp_path, [])["cards"][0]
    assert (card["name"], card["create"], card["wait"]) == ("pipe", ["alpha", "beta"], 120)

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text(
        "def hello(e, c):\n    return 1\n\n\ndef get_item(e, c):\n    return 2\n\n\ndef create_item(e, c):\n    return 3\n")
    out = edits.create_workflow(tmp_path, "workflow-1", ["step-01", "step-02", "step-03"], wait_seconds=10,
                                create_functions=["step-01", "step-02", "step-03"])
    assert out["states"] == ["Step01", "Wait1", "Step02", "Wait2", "Step03"] and out["functions"] == [
        "step-01", "step-02", "step-03"]
    assert "Configuration is valid." in out["validate"]
    raw = edits.raw_config(tmp_path)
    assert raw["functions"]["step-02"]["handler"] == "app.handlers.step_02"
    assert raw["workflows"]["workflow-1"]["states"]["Wait1"] == {"type": "wait", "seconds": 10, "next": "Step02"}
    assert "def step_03(" in (tmp_path / "app" / "handlers.py").read_text()


ROUND7_CONFIG = """
service: my-service
provider: {name: onprem, runtime: python3.12}
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
  step-api: {handler: app.steps.step01}
  step02: {handler: app.steps.step02}
  step03: {handler: app.steps.step02}
"""


def _round7(tmp_path):
    (tmp_path / "pskit.yml").write_text(ROUND7_CONFIG)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text("def hello(e, c):\n    return 1\n")


def test_function_and_code_requests(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    _round7(tmp_path)
    found = detect("creater a step01 step02 step03 funtions", tmp_path, [], provider="onprem")
    card = found["cards"][0]
    assert card["kind"] == "functions" and card["names"] == ["step01", "step02", "step03"]
    # names already in pskit.yml are asked about (update / another name / skip), never dropped silently
    assert card["existing"] == ["step02", "step03"] and card["suggested"] == {"step02": "step02-2", "step03": "step03-2"}
    assert "**step02, step03** already exist." in found["reply"] and "**step02-2**" in found["reply"]
    assert "Where should the code go?" in found["reply"] and card["placement"] == ""
    card = detect("create functions named mail-sender and report as http endpoints", tmp_path, [])["cards"][0]
    assert (card["names"], card["trigger"]) == (["mail-sender", "report"], "http")
    card = detect("add a send-report function that runs every 10 minutes", tmp_path, [])["cards"][0]
    assert (card["names"], card["trigger"], card["schedule"]) == (["send-report"], "schedule", "10 minutes")
    for text in ("jsut add boilder paldte codes",
                 "all this funtiosn step01 ,step02,step03 just u have added to yml what about code",
                 "i mean i have said u to create the step02 and step03 also write funtiosn"):
        found = detect(text, tmp_path, [])
        assert found["cards"][0]["kind"] == "code", text
        assert {i["function"] for i in found["cards"][0]["items"]} >= {"step02", "step03"}
    assert "uses the same handler" in detect("jsut add boilder paldte codes", tmp_path, [])["reply"]
    assert "already there for **hello**" in detect("write the code for hello", tmp_path, [])["reply"]


def test_create_functions_writes_yml_and_code(tmp_path):
    from py_serverless_kit.studio.hana import edits

    _round7(tmp_path)
    assert {m["function"] for m in edits.missing_code(tmp_path)} == {"step-api", "step02", "step03"}
    out = edits.write_code(tmp_path, ["step-api", "step02", "step03"])
    assert [w["file"] for w in out["written"]] == ["app/steps.py"] * 3
    assert edits.missing_code(tmp_path) == []
    code = (tmp_path / "app" / "steps.py").read_text()
    assert "def step01(" in code and "def step02(" in code
    out = edits.create_functions(tmp_path, ["mail-sender", "report"], "http")
    assert out["created"] == ["mail-sender", "report"] and "Configuration is valid." in out["validate"]
    raw = edits.raw_config(tmp_path)
    assert raw["functions"]["mail-sender"] == {"handler": "app.steps.mail_sender", "events": [{"http": "GET /mail-sender"}]}
    assert "def mail_sender(" in (tmp_path / "app" / "steps.py").read_text()
    with pytest.raises(Exception, match="already in pskit.yml: report"):
        edits.create_functions(tmp_path, ["report"])


def _four_servers(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    for n in ["app-1", "app-2", "app-3", "app-4"]:
        save_server(tmp_path, n, {"host": "192.0.2.10", "user": "ubuntu"})


def test_many_services_clusters_and_load_balancers(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    _four_servers(tmp_path)
    card = detect("create redis", tmp_path, [], provider="aws")["cards"][0]  # named: created directly, any provider
    assert (card["kind"], card["service"], card["role"]) == ("service", "redis", "cache")
    cards = detect("create 2 redis and a postgres", tmp_path, [], provider="onprem")["cards"]
    assert [c["key"] for c in cards] == ["redis-1", "redis-2", "postgres-1"]
    cards = detect("create redis on app-1 and postgres on app-2", tmp_path, [], provider="onprem")["cards"]
    assert [(c["service"], c["server"]) for c in cards] == [("redis", "app-1"), ("postgres", "app-2")]
    cards = detect("create 3 clusters with 1 server each", tmp_path, [], provider="onprem")["cards"]
    assert [(c["name"], c["master"], c["workers"]) for c in cards] == [
        ("cluster-1", "app-1", []), ("cluster-2", "app-2", []), ("cluster-3", "app-3", [])]
    cards = detect("create 2 load balancers", tmp_path, [], provider="onprem")["cards"]
    assert [(c["name"], c["server"]) for c in cards] == [("lb-1", "app-1"), ("lb-2", "app-2")]
    cards = detect("create load balancers on app-3 and app-4", tmp_path, [], provider="onprem")["cards"]
    assert [(c["name"], c["server"]) for c in cards] == [("lb-1", "app-3"), ("lb-2", "app-4")]


def test_many_resources(tmp_path):
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(CONFIG)
    found = detect("add a jobs queue, 2 buckets and a database named orders", tmp_path, [], provider="aws")
    assert [(c["key"], c["type"]) for c in found["cards"]] == [
        ("jobs", "queue"), ("bucket-1", "storage"), ("bucket-2", "storage"), ("orders", "database")]
    assert "an existing database" in found["reply"]
    cards = detect("add a cache and a topic called events", tmp_path, [], provider="aws")["cards"]
    assert [(c["key"], c["type"]) for c in cards] == [("cache-1", "cache"), ("events", "topic")]

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text("def hello(event, ctx):\n    return 'hi'\n")
    out = edits.create_resources(tmp_path, [{"key": "jobs", "type": "queue"}, {"key": "orders", "type": "database"}])
    assert out["created"] == ["jobs", "orders"] and "Configuration is valid." in out["validate"]
    res = edits.raw_config(tmp_path)["resources"]
    assert res["jobs"] == {"type": "queue"}
    assert res["orders"]["external"] is True and res["orders"]["connection"]["password_env"] == "ORDERS_PASSWORD"
    assert "password" not in res["orders"]["connection"]
    with pytest.raises(Exception, match="already a resource 'jobs'"):
        edits.create_resources(tmp_path, [{"key": "jobs", "type": "queue"}])


def test_what_the_request_is_about_comes_first(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect, object_and_place

    assert object_and_place("how i can add a service to a server") == ("service", "server")
    assert object_and_place("add app-1 to cluster-1", servers=["app-1"]) == ("server", "cluster")
    assert object_and_place("remove redis from app-1", servers=["app-1"])[1] == "server"  # app-1 is the place
    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    save_server(tmp_path, "app-1", {"host": "192.0.2.1", "user": "ubuntu"})
    for text in ("how i can add a service to a server", "no i mean how can i add any service to a server"):
        found = detect(text, tmp_path, [], provider="onprem")
        assert found["card"] is None and "**+ Create service**" in found["reply"], text
        assert "pskit resources onprem create redis-1 --service redis --server app-1" in found["reply"]
    reply = detect("how do i add app-1 to a cluster", tmp_path, [], provider="onprem")["reply"]
    assert "**+ Join server**" in reply and "pskit cluster join cluster-1 app-1" in reply
    found = detect("remove redis from app-1", tmp_path, [], provider="onprem")
    assert found["card"] is None and "no redis service on **app-1**" in found["reply"]  # never the server itself
    assert detect("remove app-1", tmp_path, [], provider="onprem")["card"]["kind"] == "server-remove"
    assert detect("add a server for me", tmp_path, [])["card"]["kind"] == "server"


def test_steps_requests_get_steps_not_actions(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    save_server(tmp_path, "app-1", {"host": "192.0.2.1", "user": "ubuntu"})
    cases = {
        "provide steps to create a postgressql": "Steps to create **PostgreSQL**",
        "how do i create redis?": "Steps to create **Redis**",
        "give me the steps to add a server": "Steps to add a server",
        "how can i create a cluster": "Steps to create a scaling cluster",
        "steps for creating a load balancer": "Steps to create a load balancer",
        "how to create a function": "Steps to create a function",
        "guide me to create a workflow": "Steps to create a workflow",
        "how do i add a queue resource": "Steps to add a resource",
    }
    for text, expected in cases.items():
        found = detect(text, tmp_path, [], provider="onprem")
        assert found and found["card"] is None and not found.get("cards"), text
        assert found["reply"].startswith(expected), (text, found["reply"][:60])
    reply = detect("provide steps to create a postgressql", tmp_path, [], provider="onprem")["reply"]
    assert "**+ Create service**" in reply and "--service postgres --server app-1" in reply
    assert "**scaling cluster**" in reply  # where it can run: this machine, a server or a cluster
    assert detect("create postgres on app-1", tmp_path, [], provider="onprem")["cards"][0]["server"] == "app-1"
    found = detect("remove the resoruces", tmp_path, [], provider="onprem")
    assert found is not None and "resource" in found["reply"].lower()  # a typo still reaches the resource removal


def test_passwords_in_notes_and_answers_are_hidden(tmp_path):
    from py_serverless_kit.studio.hana.actions import redact_password

    assert redact_password("make user name as ak2311581 and password as Test@1234") == \
        "make user name as ak2311581 and password as <hidden>"
    assert redact_password("pass Test@1234") == "pass <hidden>"
    assert redact_password("log in with a password") == "log in with a password"
    model = FakeModel([("call", "propose_plan", {"steps": ["x"]}), ("text", "ok")])
    hana = Hana(tmp_path, lambda: model)
    run_turn(hana, "change it", answers=lambda p: ("approve", "password as Test@1234"))
    assert "Test@1234" not in json.dumps(model.sent)


def test_ailogs_print_every_step_when_on(tmp_path, capsys):
    from py_serverless_kit.studio.hana import ailog

    (tmp_path / "pskit.yml").write_text(CONFIG)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text("def hello(event, ctx):\n    return 'hi'\n")
    model = FakeModel([("call", "validate", {}), ("text", "All good.")])
    ailog.enable(False)
    run_turn(Hana(tmp_path, lambda: model), "is it valid?")
    assert capsys.readouterr().err == ""  # off by default
    ailog.enable()
    try:
        run_turn(Hana(tmp_path, lambda: FakeModel([("call", "validate", {}), ("text", "All good.")])),
                 "is it valid? my password is hunter2")
        run_turn(Hana(tmp_path, lambda: FakeModel([])), "create redis")
    finally:
        ailog.enable(False)
    err = capsys.readouterr().err
    for part in ("USER", "MODEL REQUEST", "SYSTEM", "MODEL ANSWER", "TOOL CALL", "TOOL RESULT", "Configuration is valid.",
                 "All good.", "STUDIO ACTION", "CARD", "END"):
        assert part in err, part
    assert "hunter2" not in err


def test_cli_ailogs_flag():
    from click.testing import CliRunner

    from py_serverless_kit.cli.main import cli

    out = CliRunner().invoke(cli, ["studio", "--help"]).output
    assert "--ailogs" in out and "pskit studio --ailogs=true" in out


def test_the_model_answers_first_then_studio(tmp_path):
    """Default order: the model first; studio adds its cards, or its answer when the model had none."""
    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    # 1. the model answers, studio can also do it: the model's text, then studio's cards
    model = FakeModel([("text", "Redis is a cache; I can help you set it up.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "create redis")
    assert types_of(snap) == ["user", "answer", "answer", "action", "end"] and len(model.sent) == 1
    answers = [e["text"] for e in snap["events"] if e["type"] == "answer"]
    assert answers[0].startswith("Redis is a cache") and answers[1].startswith("**Studio can do this directly**")
    # 2. the model has no real answer: studio's answer is added
    model = FakeModel([("text", "Sorry, I can't create servers.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "how to create a database")
    answers = [e["text"] for e in snap["events"] if e["type"] == "answer"]
    assert len(answers) == 2 and answers[1].startswith("**From studio:**") and "PostgreSQL" in answers[1]
    # 3. the model answered: studio's text answer is not added
    model = FakeModel([("text", "Open Resources > On-prem services and pick PostgreSQL.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "how to create a database")
    assert len([e for e in snap["events"] if e["type"] == "answer"]) == 1
    # 4. the model fails: studio answers anyway
    snap = run_turn(Hana(tmp_path, lambda: FakeModel([])), "create redis")
    assert snap["status"] == "done" and "action" in types_of(snap) and "error" in types_of(snap)


def test_database_how_to_and_scaling(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana.actions import detect

    (tmp_path / "pskit.yml").write_text(ROUND5_CONFIG)
    for n in ("app-1", "app-2", "app-3"):
        save_server(tmp_path, n, {"host": "192.0.2.1", "user": "ubuntu"})
    reply = detect("how to create a database", tmp_path, [], provider="onprem")["reply"]
    assert reply.startswith("Steps to create **a database (PostgreSQL, MySQL, MariaDB, MongoDB ...)**")
    assert "**Primary + read replicas**" in reply and "--primary app-1 --replica app-2 --balancer app-1" in reply
    card = detect("create postgres with read replicas on app-1 and app-2", tmp_path, [], provider="onprem")["cards"][0]
    assert (card["scaling"], card["primary"], card["replicas"], card["sync"]) == ("replicated", "app-1", ["app-2"], "async")
    card = detect("create postgresql", tmp_path, [], provider="onprem")["cards"][0]
    assert "scaling" not in card


# --------------------------------------------------------------------------- separate apps, taken names, follow-ups

STEPS_CONFIG = """
service: my-service
provider: {name: onprem, runtime: python3.12}
functions:
  hello: {handler: app.handlers.hello, events: [{http: GET /hello}]}
  step01: {handler: app.steps.step01, environment: {LOG_LEVEL: INFO}}
  step02: {handler: app.steps.step02, environment: {LOG_LEVEL: INFO}}
  step03: {handler: app.steps.step03, environment: {LOG_LEVEL: INFO}}
"""


def _steps(tmp_path):
    """The project of the chat that failed: step01-03 created side by side in one shared app/steps.py."""
    (tmp_path / "pskit.yml").write_text(STEPS_CONFIG)
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "handlers.py").write_text("def hello(event, ctx):\n    return {'ok': True}\n")
    (tmp_path / "app" / "steps.py").write_text(
        "import logging\n\nimport requests\n\nlog = logging.getLogger(__name__)\n\n\n"
        "def step01(event, ctx):\n    return {'step': 1, 'ok': requests is not None}\n\n\n"
        "def step02(event, ctx):\n    log.info('two')\n    return {'step': 2}\n\n\n"
        "def step03(event, ctx):\n    return {'step': 3}\n")


def test_new_functions_as_separate_apps(tmp_path):
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    _steps(tmp_path)
    found = detect("create step04 step05 functions, each a separate app with its own requirements", tmp_path, [])
    card = found["cards"][0]
    assert (card["kind"], card["names"], card["placement"]) == ("functions", ["step04", "step05"], "separate")
    assert "its own app" in found["reply"] and "Where should the code go?" not in found["reply"]
    out = edits.create_functions(tmp_path, ["step04", "step05"], "http", placement="separate")
    assert out["created"] == ["step04", "step05"] and "Configuration is valid." in out["validate"]
    raw = edits.raw_config(tmp_path)
    assert raw["functions"]["step04"] == {"handler": "functions.step04.handler.main", "events": [{"http": "GET /step04"}]}
    for name in ("step04", "step05"):
        folder = tmp_path / "functions" / name
        assert (folder / "requirements.txt").is_file() and "def main(" in (folder / "handler.py").read_text()
    assert "step04" not in (tmp_path / "app" / "steps.py").read_text()  # the shared file is not touched


def test_new_functions_into_an_existing_module_or_ask(tmp_path):
    from py_serverless_kit.studio.hana.actions import detect

    _steps(tmp_path)
    card = detect("add a step04 function in app/handlers", tmp_path, [])["cards"][0]
    assert (card["placement"], card["module"]) == ("module", "app.handlers")
    assert card["modules"] == ["app.steps", "app.handlers"]  # most used first
    found = detect("create step04 function", tmp_path, [])
    assert found["cards"][0]["placement"] == "" and "**its own app**" in found["reply"]
    assert "**added to an existing app**: `app/steps.py` (shared with step01, step02, step03)" in found["reply"]


def test_taken_function_names_update_rename_or_skip(tmp_path):
    from py_serverless_kit.studio.hana import edits

    _steps(tmp_path)
    with pytest.raises(Exception, match="already in pskit.yml: step01 .choose update, rename or skip"):
        edits.create_functions(tmp_path, ["step01", "step09"], placement="module")
    out = edits.create_functions(tmp_path, ["step01", "step02", "step03", "step09"], "schedule", "1 hour",
                                 placement="separate",
                                 existing={"step01": "rename", "step02": "update", "step03": "skip"})
    assert out["created"] == ["step01-2", "step09"] and out["renamed"] == {"step01": "step01-2"}
    assert out["updated"] == ["step02"] and out["skipped"] == ["step03"]
    raw = edits.raw_config(tmp_path)
    # update keeps the function's code and settings, applies the trigger and (separate) moves it into its own app
    assert raw["functions"]["step02"]["handler"] == "functions.step02.handler.step02"
    assert raw["functions"]["step02"]["events"] == [{"schedule": "1 hour"}]
    assert raw["functions"]["step02"]["environment"] == {"LOG_LEVEL": "INFO"}
    assert "log.info('two')" in (tmp_path / "functions" / "step02" / "handler.py").read_text()
    assert raw["functions"]["step03"] == {"handler": "app.steps.step03", "environment": {"LOG_LEVEL": "INFO"}}
    assert raw["functions"]["step01-2"]["handler"] == "functions.step01_2.handler.main"
    assert "Configuration is valid." in out["validate"]


def test_existing_functions_into_separate_apps(tmp_path):
    """The chat that failed: "no app/steps, create separate apps for step01, step02, step03 and requirements also
    separate", then "first remove this app/steps, create a different app for each function"."""
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    _steps(tmp_path)
    for text in ("no aps/steps instead create a seperate apps for step01 ,step02,step03 and requirement also seperate",
                 "fist remove this app/steps create diffrent app for each funtion"):
        found = detect(text, tmp_path, [])
        assert found["cards"][0]["kind"] == "separate", text
        assert found["cards"][0]["functions"] == ["step01", "step02", "step03"], text
        assert "`app/steps.py` → `functions/step01/handler.py`" in found["reply"]
    out = edits.separate_functions(tmp_path, ["step01", "step02", "step03"])
    assert [m["function"] for m in out["moved"]] == ["step01", "step02", "step03"]
    assert out["deleted"] == ["app/steps.py"] and not (tmp_path / "app" / "steps.py").exists()
    assert "requests==2.32.3" in (tmp_path / "functions" / "step01" / "requirements.txt").read_text()
    assert "requests" not in (tmp_path / "functions" / "step03" / "requirements.txt").read_text().replace(
        "# Dependencies", "")
    raw = edits.raw_config(tmp_path)
    assert raw["functions"]["step03"]["handler"] == "functions.step03.handler.step03"
    assert raw["functions"]["hello"]["handler"] == "app.handlers.hello"
    assert "Configuration is valid." in out["validate"]
    again = edits.separate_functions(tmp_path, ["step01"])
    assert again["already"] == ["step01"] and again["moved"] == []


def test_answer_to_studios_question_is_read_with_it(tmp_path):
    """"Which function should I remove?" -> "step01,step02,step03": remove cards, answered by studio."""
    from py_serverless_kit.studio.hana.actions import detect, pending_followup

    _steps(tmp_path)
    asked = detect("remove the function", tmp_path, [])
    assert asked["reply"].startswith("Which function should I remove?")
    history = [{"role": "user", "text": "remove the function"},
               {"role": "assistant", "text": asked["reply"], "followup": asked["followup"]},
               {"role": "user", "text": "step01,step02,step03"}]
    assert pending_followup(history) == asked["followup"]
    found = detect("step01,step02,step03", tmp_path, history)
    assert found["first"] is True
    assert [(c["kind"], c["name"]) for c in found["cards"]] == [("item-remove", "step01"), ("item-remove", "step02"),
                                                                ("item-remove", "step03")]
    # something else happened in between (a card was run): the old question no longer applies
    assert pending_followup(history[:2] + [{"role": "note", "text": "Removed"}, history[2]]) is None
    # a typed answer to the question of the functions card
    asked = detect("create step04 function", tmp_path, [])
    history = [{"role": "user", "text": "create step04 function"},
               {"role": "assistant", "text": asked["reply"], "followup": asked["followup"]},
               {"role": "action", "card": asked["cards"][0]}, {"role": "user", "text": "separate app"}]
    assert detect("separate app", tmp_path, history)["cards"][0]["placement"] == "separate"


def test_taken_names_of_resources_services_clusters_and_balancers(tmp_path):
    from py_serverless_kit.core import onprem_cluster
    from py_serverless_kit.core.onprem_balancers import list_balancers
    from py_serverless_kit.studio.hana import edits
    from py_serverless_kit.studio.hana.actions import detect

    _four_servers(tmp_path)
    edits.create_resources(tmp_path, [{"key": "jobs", "type": "queue"}])
    found = detect("add a queue named jobs", tmp_path, [], provider="onprem")
    card = found["cards"][0]
    assert (card["key"], card["exists"], card["suggested"]) == ("jobs", True, "jobs-2")
    assert "**jobs** already exists (a queue). **Replace** it" in found["reply"]
    with pytest.raises(Exception, match="replace it, or pick another name"):
        edits.create_resources(tmp_path, [{"key": "jobs", "type": "storage"}])
    out = edits.create_resources(tmp_path, [{"key": "jobs", "type": "storage", "replace": True}])
    assert out["replaced"] == ["jobs"] and edits.raw_config(tmp_path)["resources"]["jobs"] == {"type": "storage"}

    card = detect("create a cluster named web with 2 servers", tmp_path, [], provider="onprem")["cards"][0]
    assert card["name"] == "web" and "conflict" not in card
    onprem_cluster._save(tmp_path, {"web": {"orchestrator": "swarm", "master": "app-1",
                                            "nodes": {"app-1": {"role": "master"}}}})
    card = detect("create a cluster named web with 2 servers", tmp_path, [], provider="onprem")["cards"][0]
    assert card["name"] == "cluster-1" and card["conflict"].startswith("web is already a cluster")

    assert list_balancers(tmp_path) == []
    card = detect("create a load balancer called edge on app-2", tmp_path, [], provider="onprem")["cards"][0]
    assert (card["name"], card["server"]) == ("edge", "app-2") and "conflict" not in card


def test_studio_answers_first_with_project_cards_and_flags_empty_claims(tmp_path):
    _steps(tmp_path)
    # a create request studio has a card for: the model is not asked (it would make its own, different change)
    model = FakeModel([])
    snap = run_turn(Hana(tmp_path, lambda: model), "create step04 step05 functions")
    assert model.sent == [] and [e["card"]["kind"] for e in snap["events"] if e["type"] == "action"] == ["functions"]
    # the model says it changed the project but no file was written: studio says so under the answer
    model = FakeModel([("text", "Done. Each function now runs in its own app.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "please update the hello handler to return the time")
    answer = [e["text"] for e in snap["events"] if e["type"] == "answer"][0]
    assert "nothing in the project was changed in this answer" in answer
    model = FakeModel([("text", "Done. validate: valid.")])  # no change asked: no note
    snap = run_turn(Hana(tmp_path, lambda: model), "is my project valid?")
    assert "nothing in the project" not in [e["text"] for e in snap["events"] if e["type"] == "answer"][0]


# --------------------------------------------------------------------------- run_command (the user clicks Run first)


def test_run_command_runs_after_the_click_and_the_model_answers_from_it(tmp_path, monkeypatch):
    from py_serverless_kit.studio.hana import terminal

    _steps(tmp_path)
    seen = []

    def fake_run(argv, cwd, timeout, shell):
        seen.append((argv, cwd, shell))
        return type("P", (), {"returncode": 0, "stdout": "app-1  192.0.2.10  ubuntu\n", "stderr": ""})()

    monkeypatch.setattr(terminal, "_run", fake_run)
    # the chat that failed: the model gave a command to copy instead of running it
    model = FakeModel([("text", "To see them:\n\n```bash\npskit resources onprem servers list --json\n```"),
                       ("text", "You have one saved server: app-1 (192.0.2.10).")])
    snap = run_turn(Hana(tmp_path, lambda: model), "u execute and provide me list", answers=lambda p: ("approve", ""))
    steps = [e for e in snap["events"] if e["type"] == "waiting"]
    assert steps[0]["tool"] == "run_command" and steps[0]["args"] == {"command": "pskit resources onprem servers list --json"}
    assert seen[0][1] == str(tmp_path) and seen[0][2] is True
    assert "-m py_serverless_kit resources onprem servers list --json" in seen[0][0][0]  # studio's own pskit
    assert [e["text"] for e in snap["events"] if e["type"] == "answer"] == ["You have one saved server: app-1 (192.0.2.10)."]
    assert "exit code 0" in model.sent[1][-1]["content"]  # the output went back to the model

    # every command waits for the click, also in Auto-approve; "Don't allow" runs nothing
    seen.clear()
    model = FakeModel([("call", "run_command", {"command": "git status"}), ("text", "OK, not run.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "check git status", mode="auto", answers=lambda p: ("reject", ""))
    assert seen == [] and "rejected: the user did not allow this command" in model.sent[1][-1]["content"]

    # asking how is not asking to run: the command stays an answer
    model = FakeModel([("text", "```bash\npskit validate\n```")])
    snap = run_turn(Hana(tmp_path, lambda: model), "how do i validate the project?")
    assert not [e for e in snap["events"] if e["type"] == "waiting"]


def test_run_command_on_a_server_and_refused_commands(tmp_path, monkeypatch):
    from py_serverless_kit.core.onprem_servers import save_server
    from py_serverless_kit.studio.hana import terminal

    (tmp_path / "pskit.yml").write_text(CONFIG)
    save_server(tmp_path, "app-1", {"host": "192.0.2.10", "user": "ubuntu"})
    calls = []

    def fake_run(argv, cwd, timeout, shell):
        calls.append((argv, shell))
        return type("P", (), {"returncode": 3, "stdout": "", "stderr": "boom"})()

    monkeypatch.setattr(terminal, "_run", fake_run)
    out = terminal.run_command(tmp_path, "docker ps", "app-1")
    assert out == "exit code 3 (server app-1)\nboom"
    argv, shell = calls[0]
    assert shell is False and "ssh" in Path(argv[0]).name  # over SSH, as an argument list (no local shell)
    assert "ubuntu@192.0.2.10" in argv and argv[-1] == "docker ps"
    assert terminal.run_command(tmp_path, "ls", "nope").startswith("error: no saved server 'nope'")
    for bad in ("rm -rf /", "sudo rm -rf / --no-preserve-root", "mkfs.ext4 /dev/sda1", "shutdown -h now",
                "dd if=/dev/zero of=/dev/sda", ":(){ :|:& };:"):
        assert terminal.check(bad).startswith("error: studio does not run this command"), bad
    for ok in ("rm -rf build/", "ls -la", "pskit validate", "docker logs pskit-hana"):
        assert terminal.check(ok) == "", ok


def test_list_servers_is_answered_by_studio_first(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server

    (tmp_path / "pskit.yml").write_text(CONFIG)
    save_server(tmp_path, "app-1", {"host": "192.0.2.10", "user": "ubuntu"})
    model = FakeModel([])
    snap = run_turn(Hana(tmp_path, lambda: model), "from this project list all the servers to me")
    assert model.sent == []
    assert "**app-1**" in [e["text"] for e in snap["events"] if e["type"] == "answer"][0]


def _azure_servers(tmp_path):
    from py_serverless_kit.core.onprem_servers import save_server

    (tmp_path / "pskit.yml").write_text(CONFIG)
    for name, ip in [("AZ_VM_01_2cpu", "20.85.209.10"), ("AZ_VM_01_4cpu", "104.43.223.136"),
                     ("AZ_VM_02_2cpu", "104.211.27.51"), ("AZ_VM_04_2cpu", "20.230.44.117")]:
        save_server(tmp_path, name, {"host": ip, "user": "azureuser"})


def test_studio_proposes_commands_from_the_chat(tmp_path):
    """The chat that failed: "lst ser", "servers", "acess the VM_01_2cpu and install docker to it", "can u execute it"."""
    from py_serverless_kit.studio.hana.actions import detect, match_server

    _azure_servers(tmp_path)
    for text in ("lst ser", "servers", "use termainal and list servers"):
        assert "**4** (four) saved servers" in detect(text, tmp_path, [])["reply"], text
    names = ["AZ_VM_01_2cpu", "AZ_VM_01_4cpu", "AZ_VM_02_2cpu"]
    assert match_server("the VM_01_2cpu", names) == "AZ_VM_01_2cpu" and match_server("vm_01", names) == ""
    run = detect("acess the VM_01_2cpu and install docker to it", tmp_path, [])["run"]
    assert run == {"command": "pskit resources onprem create docker --service docker --server AZ_VM_01_2cpu"}
    asked = detect("install docker", tmp_path, [])
    assert asked["reply"].startswith("On which server should I install **docker**?")
    history = [{"role": "user", "text": "install docker"},
               {"role": "assistant", "text": asked["reply"], "followup": asked["followup"]},
               {"role": "user", "text": "AZ_VM_02_2cpu"}]
    assert detect("AZ_VM_02_2cpu", tmp_path, history)["run"]["command"].endswith("--server AZ_VM_02_2cpu")
    assert detect("run `docker ps` on AZ_VM_02_2cpu", tmp_path, [])["run"] == {"command": "docker ps",
                                                                              "server": "AZ_VM_02_2cpu"}
    assert detect("run docker ps on VM_04_2cpu", tmp_path, [])["run"] == {"command": "docker ps", "server": "AZ_VM_04_2cpu"}
    assert detect("execute pskit validate", tmp_path, [])["run"] == {"command": "pskit validate"}
    history = [{"role": "user", "text": "x"},
               {"role": "assistant", "text": "Run:\n\n```bash\npskit resources onprem servers list\n```"},
               {"role": "user", "text": "can u execute it"}]
    assert detect("can u execute it", tmp_path, history)["run"] == {"command": "pskit resources onprem servers list"}
    assert "run" not in (detect("how do i install docker on a server?", tmp_path, []) or {})


def test_studio_runs_the_command_and_the_model_follows_up(tmp_path, monkeypatch):
    from py_serverless_kit.studio.hana import terminal

    _azure_servers(tmp_path)
    ran = []

    def fake_run(argv, cwd, timeout, shell):
        ran.append(argv[0])
        return type("P", (), {"returncode": 0, "stdout": "docker: Docker version 27.3.1", "stderr": ""})()

    monkeypatch.setattr(terminal, "_run", fake_run)
    model = FakeModel([("text", "Docker 27.3.1 is installed on AZ_VM_01_2cpu.")])
    snap = run_turn(Hana(tmp_path, lambda: model), "acess the VM_01_2cpu and install docker to it",
                    answers=lambda p: ("approve", ""))
    waiting = [e for e in snap["events"] if e["type"] == "waiting"]
    assert waiting[0]["args"]["command"].endswith("create docker --service docker --server AZ_VM_01_2cpu")
    assert "-m py_serverless_kit resources onprem create docker" in ran[0]
    sent = model.sent[0]
    assert "Saved servers: AZ_VM_01_2cpu, AZ_VM_01_4cpu, AZ_VM_02_2cpu, AZ_VM_04_2cpu." in sent[0]["content"]
    assert sent[-1]["role"] == "tool" and "Docker version 27.3.1" in sent[-1]["content"]
    assert [e["text"] for e in snap["events"] if e["type"] == "answer"] == ["Docker 27.3.1 is installed on AZ_VM_01_2cpu."]
