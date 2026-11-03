import sys
import types

import pytest

from py_serverless_kit import Context, Event, HttpRequest, NotFound, Response
from py_serverless_kit.runtime import dispatch
from py_serverless_kit.runtime.errors import HandlerNotFound
from py_serverless_kit.runtime.manifest import BundleManifest, set_manifest
from py_serverless_kit.runtime.routing import match_path


@pytest.fixture
def handlers(monkeypatch):
    mod = types.ModuleType("fake_handlers")

    def ok(event, ctx):
        return {"params": event.http.path_params if event.http else None, "fn": ctx.function}

    def one_arg(event):
        return "single"

    async def async_handler(event, ctx):
        return {"async": True}

    def boom(event, ctx):
        raise RuntimeError("secret detail")

    def not_found(event, ctx):
        raise NotFound("nope", details={"id": 1})

    for f in (ok, one_arg, async_handler, boom, not_found):
        setattr(mod, f.__name__, f)
    monkeypatch.setitem(sys.modules, "fake_handlers", mod)
    dispatch._HANDLERS.clear()
    set_manifest(
        BundleManifest.from_dict(
            {
                "functions": {
                    "ok": {
                        "handler": "fake_handlers.ok",
                        "routes": [
                            {"method": "GET", "path": "/users/{id}", "cors": {"origins": ["https://app.example"]}},
                            {"method": "DELETE", "path": "/users/{id}"},
                        ],
                    },
                    "one": {"handler": "fake_handlers:one_arg"},
                    "async": {"handler": "fake_handlers.async_handler"},
                    "boom": {"handler": "fake_handlers.boom"},
                    "nf": {"handler": "fake_handlers.not_found"},
                }
            }
        )
    )
    yield
    dispatch._HANDLERS.clear()


def http(method="GET", path="/", **kw):
    return Event(type="http", http=HttpRequest(method=method, path=path, **kw))


def test_route_params_and_context(handlers):
    resp = dispatch.execute(http(path="/users/42"), Context(), "ok")
    assert isinstance(resp, Response)
    assert resp.status == 200
    assert '"id":"42"' in resp.body and '"fn":"ok"' in resp.body


def test_method_not_allowed(handlers):
    resp = dispatch.execute(http("POST", "/users/42"), Context(), "ok")
    assert resp.status == 405
    assert resp.headers["allow"] == "DELETE, GET"


def test_cors_preflight_and_headers(handlers):
    pre = dispatch.execute(http("OPTIONS", "/users/1", headers={"Origin": "https://app.example"}), Context(), "ok")
    assert pre.status == 204
    assert pre.headers["access-control-allow-origin"] == "https://app.example"
    assert "GET" in pre.headers["access-control-allow-methods"]
    resp = dispatch.execute(http("GET", "/users/1", headers={"Origin": "https://evil.example"}), Context(), "ok")
    assert "access-control-allow-origin" not in resp.headers


def test_single_arg_and_colon_handler(handlers):
    assert dispatch.execute(Event(type="invoke"), Context(), "one") == "single"


def test_async_handler(handlers):
    assert dispatch.execute(Event(type="invoke"), Context(), "async") == {"async": True}


@pytest.mark.parametrize("debug,expect_detail", [("", False), ("1", True)])
def test_http_500_hides_details(handlers, monkeypatch, debug, expect_detail):
    monkeypatch.setenv("PSKIT_DEBUG", debug)
    resp = dispatch.execute(http(path="/x"), Context(request_id="req-1"), "boom")
    assert resp.status == 500
    assert "req-1" in resp.body
    assert ("secret detail" in resp.body) is expect_detail


def test_http_error_mapping(handlers):
    resp = dispatch.execute(http(path="/x"), Context(), "nf")
    assert resp.status == 404 and '"details":{"id":1}' in resp.body


def test_non_http_errors_propagate(handlers):
    with pytest.raises(RuntimeError):
        dispatch.execute(Event(type="queue"), Context(), "boom")


def test_unknown_function(handlers):
    with pytest.raises(LookupError):
        dispatch.execute(Event(type="invoke"), Context(), "missing")


def test_env_handler_fallback(monkeypatch, handlers):
    set_manifest(BundleManifest())
    monkeypatch.setenv("PSKIT_HANDLER", "fake_handlers.one_arg")
    assert dispatch.execute(Event(type="invoke"), Context(), None) == "single"


@pytest.mark.parametrize("path", ["nomodule", "fake_handlers.missing", "does_not_exist.fn"])
def test_bad_handlers(handlers, path):
    with pytest.raises(HandlerNotFound):
        dispatch.resolve_handler(path)


@pytest.mark.parametrize(
    "pattern,path,expected",
    [
        ("/users/{id}", "/users/7", {"id": "7"}),
        ("/users/{id}", "/users/7/x", None),
        ("/files/{path+}", "/files/a/b/c.txt", {"path": "a/b/c.txt"}),
        ("/users/{id}", "/7", {"id": "7"}),  # GCP style: static prefix stripped
        ("/users/{id}", "/api/users/7", {"id": "7"}),  # Azure style: extra prefix
        ("/hello", "/hello", {}),
        ("/hello", "/other", None),
    ],
)
def test_match_path(pattern, path, expected):
    assert match_path(pattern, path) == expected


def test_match_path_strict():
    assert match_path("/users/{id}", "/7", tolerant=False) is None
