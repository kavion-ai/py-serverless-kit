import pytest

from py_serverless_kit import resource, resources

ENV = {
    "PSKIT_RESOURCES": "db,db_main,uploads",
    "PSKIT_RESOURCE_DB_TYPE": "database",
    "PSKIT_RESOURCE_DB_NAME": "db",
    "PSKIT_RESOURCE_DB_EXTERNAL": "true",
    "PSKIT_RESOURCE_DB_HOST": "pg.local",
    "PSKIT_RESOURCE_DB_MAIN_TYPE": "database",
    "PSKIT_RESOURCE_DB_MAIN_NAME": "main",
    "PSKIT_RESOURCE_DB_MAIN_EXTERNAL": "true",
    "PSKIT_RESOURCE_DB_MAIN_PORT": "5432",
    "PSKIT_RESOURCE_UPLOADS_TYPE": "storage",
    "PSKIT_RESOURCE_UPLOADS_NAME": "acme-uploads",
    "PSKIT_RESOURCE_UPLOADS_EXTERNAL": "false",
    "PSKIT_RESOURCE_UPLOADS_ARN": "arn:aws:s3:::acme-uploads",
}


def test_resource_from_env():
    up = resource("uploads", ENV)
    assert (up.type, up.native_name, up.external, up.arn) == (
        "storage",
        "acme-uploads",
        False,
        "arn:aws:s3:::acme-uploads",
    )
    assert up.url is None
    db = resource("db", ENV)
    assert db.connection == {"host": "pg.local"}  # db_main's PORT is not mixed in
    assert db["HOST"] == "pg.local" and db.external
    assert resource("db-main", ENV).get("port") == "5432"  # sanitized lookup
    assert set(resources(ENV)) == {"db", "db_main", "uploads"}


def test_unknown_resource_and_key():
    with pytest.raises(KeyError, match="bound: db, db_main, uploads"):
        resource("cache", ENV)
    with pytest.raises(KeyError, match="has no 'password'"):
        resource("db", ENV)["password"]
    assert resources({}) == {}


def test_reads_os_environ(monkeypatch):
    monkeypatch.setenv("PSKIT_RESOURCES", "q")
    monkeypatch.setenv("PSKIT_RESOURCE_Q_TYPE", "queue")
    assert resource("q").type == "queue"
