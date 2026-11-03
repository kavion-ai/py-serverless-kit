"""Client for the server that runs the Hana model: any OpenAI-compatible ``/v1/chat/completions`` endpoint
(the ``hana-pskit`` Docker image is llama.cpp's ``llama-server --jinja``). Standard library only.

Tool calls come back as ``message.tool_calls``; when a server returns the raw ``<tool_call>{...}</tool_call>`` text
instead (no ``--jinja``), it is parsed here, so both work.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


class ModelError(Exception):
    pass


def check_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ModelError("the model URL must look like http://127.0.0.1:8790")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


class Model:
    def __init__(self, url: str, api_key: str = "", timeout: float = 300.0) -> None:
        self.url = check_url(url)
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, path: str, body: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        method = "POST" if body is not None else "GET"
        req = Request(self.url + path, data=data, headers=headers, method=method)  # noqa: S310 - http(s) only
        try:
            with urlopen(req, timeout=timeout or self.timeout) as resp:  # noqa: S310 - http(s) checked in check_url
                return json.loads(resp.read().decode("utf-8") or "null")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ModelError(f"the model server answered {exc.code}: {detail}") from None
        except (URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ModelError(f"can't reach the model at {self.url}: {reason}") from None

    def health(self) -> Dict[str, Any]:
        """``{"ok": bool, "model": str|None, "error": str|None}``; llama-server answers 503 while loading."""
        try:
            data = self._request("/v1/models", timeout=5)
        except ModelError as exc:
            return {"ok": False, "model": None, "error": str(exc)}
        models = [m.get("id") for m in (data or {}).get("data", []) if isinstance(m, dict)]
        return {"ok": True, "model": models[0] if models else None, "error": None}

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int = 900) -> Dict[str, Any]:
        """One assistant step: ``{"content": str, "tool_calls": [{"id", "name", "arguments": dict}]}``."""
        body = {
            "model": "hana",
            "messages": messages,
            "tools": tools,
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = self._request("/v1/chat/completions", body)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise ModelError(f"unexpected answer from the model server: {str(data)[:300]}") from None
        content, calls = parse_message(message)
        return {"content": content, "tool_calls": calls, "usage": data.get("usage") or {}}


def _args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
        except ValueError:
            return {"__invalid__": raw}
        return value if isinstance(value, dict) else {"__invalid__": raw}
    return {}


def parse_message(message: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = json.dumps(content)
    calls: List[Dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        calls.append({"id": call.get("id") or _id(), "name": str(fn.get("name") or "?"),
                      "arguments": _args(fn.get("arguments"))})
    if not calls:
        for match in _TOOL_CALL.finditer(content):
            try:
                call = json.loads(match.group(1))
            except ValueError:
                calls.append({"id": _id(), "name": "?", "arguments": {"__invalid__": match.group(1)}})
                continue
            calls.append({"id": _id(), "name": str(call.get("name") or "?"), "arguments": _args(call.get("arguments"))})
        if calls:
            content = _TOOL_CALL.sub("", content)
    return content.strip(), calls[:1]  # Hana was trained to make one call per step


def _id() -> str:
    return "call_" + uuid.uuid4().hex[:12]


class LocalModel:
    """The GGUF run inside the studio process with ``llama-cpp-python`` (the "Hugging Face" choice: no Docker).

    Same interface as :class:`Model`. One generation at a time (``llama_cpp.Llama`` isn't thread-safe)."""

    def __init__(self, path: str, n_ctx: int = 8192) -> None:
        self.path = path
        self.n_ctx = n_ctx
        self._llm: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        if self._llm is None:
            try:
                from llama_cpp import Llama  # type: ignore[import-not-found]
            except ImportError:
                raise ModelError("llama-cpp-python is not installed: Hana > Set up > Hugging Face installs it") from None
            try:
                self._llm = Llama(model_path=self.path, n_ctx=self.n_ctx, verbose=False)
            except Exception as exc:  # noqa: BLE001 - shown in the chat
                raise ModelError(f"can't load {self.path}: {exc}") from None
        return self._llm

    def health(self) -> Dict[str, Any]:
        import importlib.util
        import os

        if not os.path.isfile(self.path):
            return {"ok": False, "model": None, "error": f"model file missing: {self.path}"}
        if importlib.util.find_spec("llama_cpp") is None:
            return {"ok": False, "model": None, "error": "llama-cpp-python is not installed"}
        return {"ok": True, "model": os.path.basename(self.path), "error": None}

    def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int = 900) -> Dict[str, Any]:
        # The chat template writes tool-call arguments with `tojson`: give it objects, as in training, not strings.
        fixed = []
        for m in messages:
            if m.get("tool_calls"):
                m = {**m, "tool_calls": [{**c, "function": {**c["function"], "arguments": _args(c["function"].get("arguments"))}}
                                         for c in m["tool_calls"]]}
            fixed.append(m)
        with self._lock:
            llm = self._load()
            try:
                data = llm.create_chat_completion(messages=fixed, tools=tools, temperature=0, max_tokens=max_tokens)
            except Exception as exc:  # noqa: BLE001
                raise ModelError(f"the local model failed: {exc}") from None
        content, calls = parse_message(data["choices"][0]["message"])
        return {"content": content, "tool_calls": calls, "usage": data.get("usage") or {}}
