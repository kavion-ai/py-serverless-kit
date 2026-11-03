"""Hana's chat loop: sessions, turns, approvals.

A turn runs in a background thread: model step -> tool -> model step ... until Hana answers in text (at most
``MAX_STEPS`` tool calls). The UI polls ``Turn.snapshot(since)`` like a studio job.

Approvals (the studio decides, not the model):

* ``propose_plan``: mode ``ask`` waits for the user (Approve / Reject, with an optional note); mode ``auto``
  answers ``{"decision": "auto_approved"}`` at once. These are the exact results Hana was trained on.
* ``ask_user``: waits for the user's answer.
* ``set_config`` / ``write_file`` / ``invoke_local`` change files or run code. In mode ``ask`` they run without a
  question only after the user approved a plan in this turn; otherwise the user approves that single step.
* Deploy, remove and other cloud actions are not tools at all: Hana points to the Deploy page.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..project import StudioError
from . import ailog
from .knowledge import search, words
from .model import Model, ModelError
from .prompt import MODES, PAGES, PROVIDERS, TOOLS, system_message
from .tools import CHANGE_TOOLS, ProjectTools

MAX_STEPS = 14
PRE_SEARCH_CARDS = 3  # docs sections studio puts in front of the model before it answers (~3,300 characters); 0: off
_SHORT_QUERY = 3  # a reply this short ("yes", "do it", "step01, step02") is searched with the previous question
MAX_TURN_EVENTS = 2000
MAX_SESSIONS = 30
# The image runs with an 8,192-token context: the tool schemas take ~1,100 tokens and an answer up to 900.
CONTEXT_CHARS = 18_000  # ~5,600 tokens of messages (system prompt included)
SESSIONS_DIR = Path(".pskit") / "studio" / "hana" / "sessions"


class Stopped(Exception):
    pass


def _size(messages: List[Dict[str, Any]]) -> int:
    return len(json.dumps(messages, ensure_ascii=False))


def docs_query(text: str, history: List[Dict[str, Any]]) -> str:
    """What studio searches the docs for before the model answers: the user's message; a short reply is joined to
    the user's previous message so "yes, do it" still finds the topic. Empty when there is nothing to search."""
    query = " ".join(text.split())[:300]
    if len(words(query)) < _SHORT_QUERY:
        previous = next((str(m.get("content") or "") for m in reversed(history) if m.get("role") == "user"), "")
        query = " ".join((" ".join(previous.split())[:200] + " " + query).split())
    return query if words(query) else ""


def fit(messages: List[Dict[str, Any]], limit: int = CONTEXT_CHARS, keep_from: int = 1) -> List[Dict[str, Any]]:
    """Make the conversation fit the model's context: first shorten old tool results, then drop the oldest
    exchanges (a user message up to the next one). ``messages[0]`` is the system prompt; messages from index
    ``keep_from`` (the current turn) are dropped last."""
    out = [dict(m) for m in messages]
    if _size(out) <= limit:
        return out
    for i, m in enumerate(out):
        if i >= keep_from or _size(out) <= limit:
            break
        if m["role"] == "tool" and len(m.get("content") or "") > 300:
            m["content"] = m["content"][:300] + "\n... (cut to save space)"
    while _size(out) > limit:
        users = [i for i, m in enumerate(out) if m["role"] == "user" and 0 < i]
        if len(users) < 2 or users[1] > keep_from:
            break
        del out[users[0]:users[1]]
        keep_from -= users[1] - users[0]
    if _size(out) > limit:  # the current turn alone is too long: shorten its older tool results
        tools = [i for i, m in enumerate(out) if m["role"] == "tool"][:-2]
        for i in tools:
            if len(out[i].get("content") or "") > 400:
                out[i]["content"] = out[i]["content"][:400] + "\n... (cut to save space)"
            if _size(out) <= limit:
                break
    return out


# The model's answer is no answer: then studio's answer (if it has one) is added after it
_NO_ANSWER = re.compile(
    r"\b(i can'?t|i cannot|i can not|i don'?t (?:know|have|do|write|create|delete|remove)|i'?m not able|not able to|"
    r"unable to|i'?m not sure|no answer|isn'?t possible|that'?s your job|too many tool steps|no answer\))", re.I)
RECENT_TURNS = 4  # earlier exchanges are not sent: a small model otherwise keeps returning to an old topic
# Cards that change pskit.yml or the code: when studio has one, studio answers first. Otherwise the model makes its
# own change (one shared file, its own names) and the card then offers a second, different one.
PROJECT_CARDS = ("functions", "separate", "code", "resource", "item-remove", "workflow")
# The user asked for a change ...
_ASKS_CHANGE = re.compile(r"\b(create|add|make|remove|delete|update|change|move|rename|replace|separate|seperate|"
                          r"split|write|fix|set)\b", re.I)
# ... and the model's answer says it was made
_CLAIMS_CHANGE = re.compile(r"^\s*(done\b|ok,? i'?ll\b|i'?ve\b|i have\b)|\b(i (?:added|created|removed|deleted|"
                            r"updated|changed|moved|wrote|renamed)|(?:added|created|removed|deleted|updated|moved) "
                            r"(?:the|three|two|\d+|them|it)\b|now runs in its own|each function now)", re.I)
NOTHING_CHANGED = ("\n\n> **Note from studio:** nothing in the project was changed in this answer (no file was "
                   "written), whatever the text above says.")


# The user wants the result, not instructions ("u execute and provide me list", "list servers", "show the logs")
_WANTS_RESULT = re.compile(r"\b(execute|exec|run|list|show|give|provide|tell|check|status|logs?|how many|get|fetch|"
                           r"display|print|see)\b", re.I)
_HOW_TO = re.compile(r"^\s*(how|steps?|guide|explain|what is the command|which command)\b|\bhow (do|can|to|should) "
                     r"(i|we)\b|\b(the )?command (for|to)\b", re.I)
_BASH_BLOCK = re.compile(r"```(?:bash|sh|shell|console|powershell|cmd)?\s*\n(.*?)```", re.S)


def command_to_run(user_text: str, out: Dict[str, Any], ran: int) -> str:
    """The command in the model's answer that studio should offer to run (``run_command``, the user clicks first):
    the user asked for a result (not how to do it), the answer is a command in a code block, and no command ran in
    this turn yet (after one, the model answers from its output). "" when none."""
    if ran or not _WANTS_RESULT.search(user_text) or _HOW_TO.search(user_text):
        return ""
    block = _BASH_BLOCK.search(str(out.get("content") or ""))
    if not block:
        return ""
    lines = [ln.strip().lstrip("$").strip() for ln in block.group(1).splitlines()]
    command = next((ln for ln in lines if ln and not ln.startswith("#")), "")
    if not command or re.search(r"<[^>]+>|\.\.\.|\bYOUR_|\bNAME\b", command):  # a template, not a command
        return ""
    return command


def studio_first(action: Dict[str, Any], env: Dict[str, Any]) -> bool:
    """Studio answers before the model: the setting says so, the message answers studio's own question, or studio
    has a card that changes the project."""
    cards = action.get("cards") or ([action["card"]] if action.get("card") else [])
    return env.get("first") == "studio" or bool(action.get("first")) or any(
        isinstance(c, dict) and c.get("kind") in PROJECT_CARDS for c in cards)


def recent(messages: List[Dict[str, Any]], start: int, turns: int = RECENT_TURNS) -> Tuple[List[Dict[str, Any]], int]:
    """The last ``turns`` exchanges (from a user message on) and how many earlier messages were left out."""
    users = [i for i, m in enumerate(messages[:start]) if m["role"] == "user"]
    if len(users) < turns:
        return messages, 0
    cut = users[-(turns - 1)] if turns > 1 else start
    return messages[cut:], cut


class Turn:
    def __init__(self, session: Session, text: str, env: Dict[str, str]) -> None:
        self.id = uuid.uuid4().hex[:16]
        self.session = session
        self.text = text
        self.env = env
        self.status = "running"  # running | waiting | done | error | stopped
        self.events: List[Dict[str, Any]] = []
        self._seq = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.pending: Optional[Dict[str, Any]] = None
        self._answer: Optional[Dict[str, Any]] = None
        self.stopped = False
        self.plan_approved = env.get("mode") == "auto"
        self.changed: List[str] = []
        self.started_at = time.time()

    def emit(self, event: str, **data: Any) -> None:
        with self._lock:
            self._seq += 1
            self.events.append({"seq": self._seq, "type": event, "at": time.time(), **data})
            if len(self.events) > MAX_TURN_EVENTS:
                del self.events[: len(self.events) - MAX_TURN_EVENTS]

    def snapshot(self, since: int = 0) -> Dict[str, Any]:
        with self._lock:
            return {
                "turn_id": self.id,
                "session_id": self.session.id,
                "status": self.status,
                "pending": self.pending,
                "events": [e for e in self.events if e["seq"] > since],
                "next": self._seq,
                "changed": list(self.changed),
            }

    # ------------------------------------------------------------------ waiting for the user
    def wait_for(self, kind: str, **data: Any) -> Dict[str, Any]:
        pid = uuid.uuid4().hex[:10]
        with self._lock:
            self.pending = {"id": pid, "kind": kind, **data}
            self._answer = None
            self._wake.clear()
            self.status = "waiting"
        self.emit("waiting", kind=kind, pending_id=pid, **data)
        ailog.log(self.id, "waiting", {"plan": "plan for the user to approve", "question": "question for the user",
                                       "step": "a change needs the user's OK"}.get(kind, kind), data, "white")
        while not self._wake.wait(1.0):
            if self.stopped:
                break
        with self._lock:
            self.pending = None
            answer, self._answer = self._answer, None
            if self.status == "waiting":
                self.status = "running"
        if self.stopped or answer is None:
            raise Stopped()
        self.emit("answered", kind=kind, pending_id=pid, **answer)
        ailog.log(self.id, "user answer", f"{kind}: {answer.get('decision')}", answer.get("text") or None, "green")
        return answer

    def respond(self, pending_id: str, answer: Dict[str, Any]) -> None:
        from .actions import redact_password

        # a plan note or an answer is sent to the model like a message: a password typed there is hidden too
        answer = {**answer, "text": redact_password(str(answer.get("text") or ""))}
        with self._lock:
            if not self.pending or self.pending["id"] != pending_id:
                raise StudioError(409, "that question was already answered or has expired")
            self._answer = answer
        self._wake.set()

    def stop(self) -> None:
        self.stopped = True
        self._wake.set()


class Session:
    def __init__(self, sid: Optional[str] = None, title: str = "") -> None:
        self.id = sid or uuid.uuid4().hex[:12]
        self.title = title
        self.messages: List[Dict[str, Any]] = []  # without the system prompt
        self.display: List[Dict[str, Any]] = []  # what the chat shows when the session is reopened
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.turn: Optional[Turn] = None

    def summary(self) -> Dict[str, Any]:
        return {"id": self.id, "title": self.title or "New chat", "updated_at": self.updated_at,
                "messages": sum(1 for d in self.display if d["role"] == "user")}

    def to_json(self) -> Dict[str, Any]:
        return {"id": self.id, "title": self.title, "created_at": self.created_at, "updated_at": self.updated_at,
                "messages": self.messages, "display": self.display}

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> Session:
        s = cls(str(data["id"]), str(data.get("title") or ""))
        s.messages = list(data.get("messages") or [])
        s.display = list(data.get("display") or [])
        s.created_at = float(data.get("created_at") or time.time())
        s.updated_at = float(data.get("updated_at") or s.created_at)
        return s


class Hana:
    """One per studio: the sessions of this project and the turn threads."""

    def __init__(self, root: Path, model_factory: Callable[[], Model], tools: Optional[ProjectTools] = None) -> None:
        self.root = Path(root).resolve()
        self.model_factory = model_factory
        self.tools = tools or ProjectTools(self.root)
        self.sessions: OrderedDict[str, Session] = OrderedDict()
        self.turns: OrderedDict[str, Turn] = OrderedDict()
        self._lock = threading.Lock()
        self._tool_lock = threading.Lock()  # one project-changing tool at a time
        self._load()

    # ------------------------------------------------------------------ persistence
    @property
    def _dir(self) -> Path:
        return self.root / SESSIONS_DIR

    def _load(self) -> None:
        if not self._dir.is_dir():
            return
        found = []
        for path in self._dir.glob("*.json"):
            try:
                found.append(Session.from_json(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for s in sorted(found, key=lambda x: x.updated_at)[-MAX_SESSIONS:]:
            self.sessions[s.id] = s

    def _save(self, session: Session) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{session.id}.json"
            path.write_bytes(json.dumps(session.to_json(), ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass

    # ------------------------------------------------------------------ sessions
    def list(self) -> List[Dict[str, Any]]:
        return [s.summary() for s in sorted(self.sessions.values(), key=lambda x: -x.updated_at)]

    def get(self, sid: str) -> Session:
        session = self.sessions.get(sid)
        if session is None:
            raise StudioError(404, "no such chat")
        return session

    def delete(self, sid: str) -> Dict[str, Any]:
        session = self.get(sid)
        if session.turn and session.turn.status in ("running", "waiting"):
            session.turn.stop()
        with self._lock:
            self.sessions.pop(sid, None)
        try:
            (self._dir / f"{sid}.json").unlink()
        except OSError:
            pass
        return {"deleted": sid}

    def edit(self, sid: str, index: int, text: str, env: Dict[str, Any]) -> Turn:
        """Change the user message at ``display[index]``: everything from it on is dropped (what Hana said and did
        after it stays in the project, but not in the chat), then the new text is sent."""
        session = self.get(sid)
        if session.turn and session.turn.status in ("running", "waiting"):
            raise StudioError(409, "Hana is still working on the last message (stop it first)", code="busy")
        if not 0 <= index < len(session.display) or session.display[index].get("role") != "user":
            raise StudioError(400, "that is not one of your messages")
        entry = session.display[index]
        cut = entry.get("m")
        if not isinstance(cut, int):  # chats saved before "m" was recorded: the n-th user message
            nth = sum(1 for d in session.display[:index] if d.get("role") == "user")
            users = [i for i, m in enumerate(session.messages) if m["role"] == "user"]
            cut = users[nth] if nth < len(users) else len(session.messages)
        with self._lock:
            del session.messages[cut:]
            del session.display[index:]
        return self.send(sid, text, env)

    def delete_all(self) -> Dict[str, Any]:
        """Every chat of this project: stops running turns, deletes the saved files."""
        ids = list(self.sessions)
        for sid in ids:
            self.delete(sid)
        if self._dir.is_dir():
            for path in self._dir.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
        return {"deleted": len(ids)}

    def turn(self, tid: str) -> Turn:
        t = self.turns.get(tid)
        if t is None:
            raise StudioError(404, "no such turn")
        return t

    # ------------------------------------------------------------------ sending
    def send(self, sid: Optional[str], text: str, env: Dict[str, Any]) -> Turn:
        text = (text or "").strip()
        if not text:
            raise StudioError(400, "message is empty")
        from .actions import redact_password

        text = redact_password(text)  # a password typed in the chat is never stored or sent to the model
        if len(text) > 8000:
            raise StudioError(400, "message is too long (8,000 characters at most)")
        clean = {
            "provider": str(env.get("provider") or "none"),
            "stage": str(env.get("stage") or "dev"),
            "mode": str(env.get("mode") or "ask"),
            "page": str(env.get("page") or "none"),
            # who answers first: the model (default), then studio actions; or studio first, then the model
            "first": "studio" if env.get("first") == "studio" else "model",
        }
        if clean["mode"] not in MODES:
            raise StudioError(400, "mode must be ask or auto")
        if clean["page"] not in PAGES:
            clean["page"] = "none"
        if clean["provider"] not in PROVIDERS:
            clean["provider"] = "none"
        model = self.model_factory()  # raises 409 hana-setup when no model is configured
        with self._lock:
            session = self.sessions.get(sid or "") if sid else None
            if session is None:
                session = Session(title=text.splitlines()[0][:60])
                self.sessions[session.id] = session
                while len(self.sessions) > MAX_SESSIONS:
                    self.sessions.popitem(last=False)
            if session.turn and session.turn.status in ("running", "waiting"):
                raise StudioError(409, "Hana is still working on the last message (stop it first)", code="busy")
            turn = Turn(session, text, clean)
            session.turn = turn
            self.turns[turn.id] = turn
            while len(self.turns) > 50:
                self.turns.popitem(last=False)
        threading.Thread(target=self._run, args=(turn, model), name=f"hana-{turn.id}", daemon=True).start()
        return turn

    def _run(self, turn: Turn, model: Model) -> None:
        session = turn.session
        env = turn.env
        start = len(session.messages)
        final = "error"
        session.messages.append({"role": "user", "content": turn.text})
        session.display.append({"role": "user", "text": turn.text, "m": start})
        turn.emit("user", text=turn.text)
        system = {"role": "system", "content": system_message(env["provider"], env["stage"], env["mode"], env["page"],
                                                              servers=self._server_names())}
        tid = turn.id
        clock = ailog.Timer()
        ailog.log(tid, "user", f"chat {session.id} · provider={env['provider']} stage={env['stage']} "
                               f"mode={env['mode']} page={env['page']}", turn.text, "green")
        action = None
        try:
            action = self._action(turn)
            ran = 0  # run_command calls in this turn
            if action is not None and isinstance(action.get("run"), dict):
                # "install docker on AZ_VM_01_2cpu": studio proposes the command (the user clicks Run), then the
                # model answers from its output
                ailog.log(tid, "studio action", "studio runs a command (asks first)", action["run"], "magenta")
                self._tool_step(turn, "run_command", action["run"], "call_00", action["reply"])
                ran, action = 1, None
            if action is not None and studio_first(action, env):
                self._studio_answer(turn, action, "answered by studio (studio first)" if env.get("first") == "studio"
                                    else "answered by studio (its question, or a card that changes the project)")
                final = "done"
                return
            ailog.log(tid, "model", "the model answers first" + (
                "; studio has an action ready for after it" if action is not None else ""), None, "yellow")
            query = docs_query(turn.text, session.messages[:start])
            if PRE_SEARCH_CARDS and not ran and query:  # docs first: the model answers from them (DOCS_LINE)
                ailog.log(tid, "studio", "searches the docs before the model answers", query, "magenta")
                self._tool_step(turn, "search_docs", {"query": query}, "call_00",
                                result=search()(query, k=PRE_SEARCH_CARDS)[0])
            for step in range(MAX_STEPS):
                if turn.stopped:
                    raise Stopped()
                turn.emit("thinking")
                history, offset = recent(session.messages, start)
                request = fit([system, *history], keep_from=start + 1 - offset)
                ailog.log(tid, "model request", f"step {step + 1}: {len(request)} messages, "
                                                f"~{len(json.dumps(request, ensure_ascii=False)) // 4} tokens, "
                                                f"{len(TOOLS)} tools", None, "yellow")
                if step == 0:  # later requests only add the tool call + result already printed above
                    ailog.show_messages(tid, request, first=True)
                timer = ailog.Timer()
                out = model.chat(request, TOOLS)
                ailog.log(tid, "model answer", f"{timer.ms()} ms · {ailog.usage_text(out.get('usage'))}",
                          {"content": out["content"], "tool_calls": [{"name": c["name"], "arguments": c["arguments"]}
                                                                      for c in out["tool_calls"]]}, "yellow")
                if turn.stopped:
                    raise Stopped()
                command = command_to_run(turn.text, out, ran) if not out["tool_calls"] else ""
                if command:  # "u execute and provide me list" -> the command it wrote, run after the user's click
                    ailog.log(tid, "studio", "the model wrote a command for something the user asked to see: "
                                             "run_command (asks first)", command, "magenta")
                    out = {**out, "content": "", "tool_calls": [{"id": "x", "name": "run_command",
                                                                 "arguments": {"command": command}}]}
                if any(c["name"] == "run_command" for c in out["tool_calls"]):
                    ran += 1
                if not out["tool_calls"]:
                    text = out["content"] or "(no answer)"
                    if not turn.changed and _ASKS_CHANGE.search(turn.text) and _CLAIMS_CHANGE.search(text):
                        # "Done. Each function now runs in its own app" with no file written: say so
                        text += NOTHING_CHANGED
                        ailog.log(tid, "studio", "the model says it changed the project, but no file changed", None,
                                  "red")
                    session.messages.append({"role": "assistant", "content": text})
                    session.display.append({"role": "assistant", "text": text})
                    turn.emit("answer", text=text)
                    final = "done"
                    break
                call = out["tool_calls"][0]
                self._tool_step(turn, call["name"], call["arguments"], f"call_{step + 1:02d}", out["content"])
            else:
                turn.emit("answer", text="I stopped after too many steps. Tell me how to continue.")
                session.messages.append({"role": "assistant", "content": "(stopped: too many tool steps)"})
                session.display.append({"role": "assistant", "text": "(stopped: too many tool steps)"})
                ailog.log(tid, "stopped", f"after {MAX_STEPS} tool steps", None, "red")
                final = "done"
            if action is not None:  # the model answered first; now what studio can add (cards, or a missing answer)
                last = session.display[-1] if session.display else {}
                self._studio_after(turn, action, str(last.get("text") or "") if last.get("role") == "assistant" else "")
        except Stopped:
            final = "stopped"
            turn.emit("stopped")
            ailog.log(tid, "stopped", "by the user", None, "red")
            last = session.messages[-1]
            if last.get("tool_calls"):  # a call without its result would break the next prompt
                call = last["tool_calls"][0]
                session.messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["function"]["name"],
                                         "content": "error: stopped by the user"})
            session.messages.append({"role": "assistant", "content": "(stopped by the user)"})
        except ModelError as exc:
            final = "error"
            turn.emit("error", text=str(exc))
            ailog.log(tid, "error", "model", str(exc), "red")
            del session.messages[start + 1:]  # keep the user message, drop the half-done steps
            if action is not None:  # the model is down or failed: studio's answer is still useful
                self._studio_answer(turn, action, "the model failed: studio answers")
                final = "done"
        except Exception as exc:  # noqa: BLE001 - shown in the chat
            final = "error"
            turn.emit("error", text=f"{type(exc).__name__}: {exc}")
            ailog.log(tid, "error", type(exc).__name__, str(exc), "red")
            if action is not None:
                self._studio_answer(turn, action, "the model failed: studio answers")
                final = "done"
        finally:
            session.updated_at = time.time()
            self._save(session)
            if final == "done" and session.display and session.display[-1].get("role") == "assistant":
                ailog.log(tid, "hana", "final answer", session.display[-1].get("text"), "green")
            ailog.log(tid, "end", f"{final} · {clock.ms()} ms"
                      + (f" · changed: {', '.join(turn.changed)}" if turn.changed else ""), None,
                      "green" if final == "done" else "red")
            turn.emit("end", status=final, changed=list(turn.changed))
            turn.status = final  # last: a finished snapshot always holds every event and the saved chat

    def _server_names(self) -> List[str]:
        """The saved servers, named in the system message so the model knows run_command's ``server`` values."""
        try:
            from ...core.onprem_servers import list_servers

            return [str(s["name"]) for s in list_servers(self.root)]
        except Exception:  # noqa: BLE001 - a broken servers file must not break the chat
            return []

    def _tool_step(self, turn: Turn, name: str, args: Dict[str, Any], cid: str, content: str = "",
                   result: Optional[str] = None) -> str:
        """One tool call: recorded for the model and the chat, run (approvals included), its result recorded.
        With ``result`` studio already has the answer (its own docs search) and nothing is run."""
        session = turn.session
        session.messages.append({"role": "assistant", "content": content, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]})
        if content:
            session.display.append({"role": "assistant", "text": content})
        turn.emit("tool_call", name=name, args=args, text=content)
        ailog.log(turn.id, "tool call", name, args, "cyan")
        timer = ailog.Timer()
        if result is None:
            result = self._execute(turn, name, args)
        ailog.log(turn.id, "tool result", f"{name} · {timer.ms()} ms · {len(result)} characters", result, "cyan")
        session.messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": result})
        session.display.append({"role": "tool", "name": name, "args": args, "result": result[:4000]})
        turn.emit("tool_result", name=name, result=result)
        return result

    def _studio_answer(self, turn: Turn, action: Dict[str, Any], why: str) -> None:
        """Studio's own reply and cards (servers, services, clusters, deploy ...) added to the chat."""
        session = turn.session
        cards = action.get("cards") or ([action["card"]] if action.get("card") else [])
        ailog.log(turn.id, "studio action", why + (f" · {len(cards)} card(s): " + ", ".join(
            str(c.get("kind")) for c in cards) if cards else ""), action["reply"], "magenta")
        for card in cards:
            ailog.log(turn.id, "card", str(card.get("kind")), card, "magenta")
        session.messages.append({"role": "assistant", "content": action["reply"]})
        entry: Dict[str, Any] = {"role": "assistant", "text": action["reply"]}
        if isinstance(action.get("followup"), dict):  # studio asked something: the next message may answer it
            entry["followup"] = action["followup"]
        session.display.append(entry)
        turn.emit("answer", text=action["reply"])
        for card in cards:
            session.display.append({"role": "action", "card": card})
            turn.emit("action", card=card)

    def _studio_after(self, turn: Turn, action: Dict[str, Any], model_text: str) -> None:
        """After the model's answer: studio's cards when it can do the thing, its answer when the model had none."""
        cards = action.get("cards") or ([action["card"]] if action.get("card") else [])
        if cards:
            self._studio_answer(turn, {**action, "reply": "**Studio can do this directly** (nothing runs until you "
                                                         "click):\n\n" + action["reply"]},
                                "after the model: studio actions for this request")
        elif not model_text.strip() or _NO_ANSWER.search(model_text):
            self._studio_answer(turn, {**action, "reply": "**From studio:**\n\n" + action["reply"]},
                                "the model had no real answer: studio answers")
        else:
            ailog.log(turn.id, "studio", "the model answered; studio's text answer was not needed", action["reply"],
                      "white")

    def _action(self, turn: Turn) -> Optional[Dict[str, Any]]:
        from .actions import detect

        try:
            found = detect(turn.text, self.root, turn.session.display, turn.env["provider"], turn.env["stage"])
        except Exception:  # noqa: BLE001 - the model answers instead
            return None
        return found if found and found.get("direct") else None

    def note(self, sid: str, text: str) -> Dict[str, Any]:
        """The outcome of a card the user ran (``Saved server app-1 ...``): shown in the chat, and part of what the
        model reads next, so a follow-up ("now create redis on it") has the context."""
        session = self.get(sid)
        text = str(text or "").strip()[:2000]
        if not text:
            raise StudioError(400, "text is required")
        session.messages.append({"role": "assistant", "content": text})
        session.display.append({"role": "note", "text": text})
        ailog.log(session.id, "card result", "the user ran a card", text, "magenta")
        session.updated_at = time.time()
        self._save(session)
        return {"ok": True}

    def _execute(self, turn: Turn, name: str, args: Dict[str, Any]) -> str:
        env = turn.env
        if "__invalid__" in args:
            return "error: the arguments are not valid JSON"
        if name == "propose_plan":
            steps = [str(s) for s in args.get("steps") or []] if isinstance(args.get("steps"), list) else []
            if not steps:
                return "error: propose_plan needs steps (a list of short strings)"
            if env["mode"] == "auto":
                turn.plan_approved = True
                turn.emit("plan", steps=steps, decision="auto_approved")
                return json.dumps({"decision": "auto_approved"})
            answer = turn.wait_for("plan", steps=steps)
            approved = answer.get("decision") == "approve"
            turn.plan_approved = turn.plan_approved or approved
            return json.dumps({"decision": "approved" if approved else "rejected", "note": str(answer.get("text") or "")})
        if name == "ask_user":
            options = [str(o) for o in args.get("options") or []] if isinstance(args.get("options"), list) else []
            answer = turn.wait_for("question", question=str(args.get("question") or ""), options=options)
            return str(answer.get("text") or "")
        if name == "run_command":  # every command waits for the user's click, in every mode
            from .terminal import check, run_command

            command, server = str(args.get("command") or "").strip(), str(args.get("server") or "").strip()
            refused = check(command)
            if refused:
                return refused
            answer = turn.wait_for("step", tool=name, args={"command": command, **({"server": server} if server
                                                                                    else {})})
            if answer.get("decision") != "approve":
                note = str(answer.get("text") or "")
                return "rejected: the user did not allow this command" + (f" ({note})" if note else "")
            return run_command(self.root, command, server)
        if name in CHANGE_TOOLS and not turn.plan_approved:
            answer = turn.wait_for("step", tool=name, args=args)
            if answer.get("decision") != "approve":
                note = str(answer.get("text") or "")
                return "rejected: the user did not allow this step" + (f" ({note})" if note else "")
        provider = env["provider"] if env["provider"] != "none" else ""
        if name in CHANGE_TOOLS:
            with self._tool_lock:
                self.tools.changed = []
                result = self.tools.run(name, args, provider, env["stage"])
                for path in self.tools.changed:
                    if path not in turn.changed:
                        turn.changed.append(path)
            if self.tools.changed:
                turn.emit("changed", files=list(self.tools.changed))
                ailog.log(turn.id, "changed files", ", ".join(self.tools.changed), None, "magenta")
            return result
        return self.tools.run(name, args, provider, env["stage"])
