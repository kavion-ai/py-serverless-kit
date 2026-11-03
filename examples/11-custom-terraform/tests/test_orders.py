from py_serverless_kit.core.project import Project
from py_serverless_kit.local import LocalRunner, http_event


def test_create_then_get():
    runner = LocalRunner(Project.load())
    created = runner.invoke("create-order", http_event("POST", "/orders", {"item": "book"}))
    assert created.status == 201
    order_id = created.render()[2].decode().split('"id":"')[1].split('"')[0]
    fetched = runner.invoke("get-order", http_event("GET", f"/orders/{order_id}"))
    assert fetched.status == 200
