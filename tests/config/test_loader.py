import textwrap

import pytest

from py_serverless_kit.config.loader import ConfigError, deep_merge, load_config

BASE = """
service: shop
provider:
  name: aws
  region: ${env:TEST_REGION, eu-west-1}
  stage: dev
  environment:
    TABLE: ${self:service}-${opt:stage}-orders
    COUNT: ${self:custom.count}
custom:
  count: 3
functions:
  api:
    handler: app.handlers.hello
    memory: 128
    events:
      - http: GET /orders/{id}
providers:
  gcp:
    region: europe-west1
    options: {project: my-proj}
  azure:
    region: westeurope
stages:
  prod:
    provider:
      memory: 1024
      state: {backend: s3}
    providers:
      onprem:
        region: local
        memory: 128
        state: {backend: null}
    functions:
      api:
        memory: 512
"""


def write(tmp_path, text, name="pskit.yml"):
    (tmp_path / name).write_text(textwrap.dedent(text), "utf-8")


def test_defaults_and_interpolation(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_REGION", raising=False)
    write(tmp_path, BASE)
    loaded = load_config(cwd=tmp_path)
    cfg = loaded.config
    assert cfg.provider.region == "eu-west-1"
    assert cfg.provider.environment == {"TABLE": "shop-dev-orders", "COUNT": "3"}
    assert cfg.functions["api"].memory == 128
    assert cfg.functions["api"].events[0].config.path == "/orders/{id}"


def test_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_REGION", "ap-south-1")
    write(tmp_path, BASE)
    assert load_config(cwd=tmp_path).config.provider.region == "ap-south-1"


def test_provider_override_switches_cloud(tmp_path):
    write(tmp_path, BASE)
    cfg = load_config(cwd=tmp_path, provider="gcp").config
    assert cfg.provider.name == "gcp"
    assert cfg.provider.region == "europe-west1"
    assert cfg.provider.options == {"project": "my-proj"}
    # functions / handler code are untouched
    assert cfg.functions["api"].handler == "app.handlers.hello"


def test_stage_overrides(tmp_path):
    write(tmp_path, BASE)
    cfg = load_config(cwd=tmp_path, stage="prod").config
    assert cfg.provider.stage == "prod"
    assert cfg.provider.memory == 1024
    assert cfg.functions["api"].memory == 512
    assert cfg.provider.environment["TABLE"] == "shop-prod-orders"


def test_stage_can_override_one_provider(tmp_path):
    write(tmp_path, BASE)
    aws = load_config(cwd=tmp_path, stage="prod").config
    assert aws.provider.memory == 1024
    assert aws.provider.state.backend == "s3"
    onprem = load_config(cwd=tmp_path, provider="onprem", stage="prod").config
    assert onprem.provider.region == "local"
    assert onprem.provider.memory == 128
    assert onprem.provider.state.backend is None
    assert onprem.functions["api"].memory == 512


def test_cli_region(tmp_path):
    write(tmp_path, BASE)
    assert load_config(cwd=tmp_path, region="us-west-2").config.provider.region == "us-west-2"


def test_extends(tmp_path):
    write(tmp_path, BASE, "base.yml")
    write(tmp_path, "extends: base.yml\nprovider:\n  name: azure\n", "pskit.azure.yml")
    cfg = load_config("pskit.azure.yml", cwd=tmp_path).config
    assert cfg.provider.name == "azure" and cfg.provider.region == "westeurope"
    assert "api" in cfg.functions


def test_circular_extends(tmp_path):
    write(tmp_path, "extends: b.yml\n", "a.yml")
    write(tmp_path, "extends: a.yml\n", "b.yml")
    with pytest.raises(ConfigError, match="circular"):
        load_config("a.yml", cwd=tmp_path)


def test_file_variable(tmp_path):
    (tmp_path / "vals.json").write_text('{"mem": 777}', "utf-8")
    (tmp_path / "secret.txt").write_text("s3cr3t\n", "utf-8")
    write(
        tmp_path,
        """
        service: svc
        provider:
          name: aws
          memory: ${self:custom.vals.mem}
          environment:
            SECRET: ${file(secret.txt)}
        custom:
          vals: ${file(vals.json)}
        """,
    )
    cfg = load_config(cwd=tmp_path).config
    assert cfg.provider.memory == 777
    assert cfg.provider.environment["SECRET"] == "s3cr3t"


def test_foreign_variables_kept(tmp_path):
    write(
        tmp_path,
        """
        service: svc
        provider:
          name: aws
          environment:
            TABLE_ARN: ${tf:aws_dynamodb_table.orders.arn}
            USER: ${aws:username}
        """,
    )
    env = load_config(cwd=tmp_path).config.provider.environment
    assert env == {"TABLE_ARN": "${tf:aws_dynamodb_table.orders.arn}", "USER": "${aws:username}"}


@pytest.mark.parametrize(
    "text,match",
    [
        ("service: x\nprovider: {name: aws}\n", "service must be"),
        ("service: svc\nprovider: {name: nope}\n", "unknown provider"),
        ("service: svc\nprovider: {name: aws, region: '${env:PSKIT_DEFINITELY_UNSET}'}\n", "unresolved variables"),
        ("service: svc\nprovider: {name: aws}\nfunctions: {f: {handler: nodots}}\n", "handler"),
        (
            "service: svc\nprovider: {name: aws}\nfunctions: {f: {handler: a.b, events: [{http: {}, queue: x}]}}\n",
            "single-key",
        ),
        (
            "service: svc\nprovider: {name: aws}\nfunctions: {f: {handler: a.b, events: [{bogus: {}}]}}\n",
            "unknown event type",
        ),
        (
            "service: svc\nprovider: {name: aws}\nfunctions: {f: {handler: a.b, events: [{schedule: {rate: often}}]}}\n",
            "rate must",
        ),
        ("service: svc\nprovider: {name: aws, runtime: python2.7}\n", "runtime"),
        ("service: svc\nprovider: {name: aws}\nfunctions: {f: {handler: a.b, unknown_key: 1}}\n", "Extra inputs"),
        ("- just\n- a list\n", "mapping"),
        ("service: svc\nprovider: {name: aws}\nhooks: {whenever: [ls]}\n", "unknown hooks"),
    ],
)
def test_errors(tmp_path, text, match):
    write(tmp_path, text)
    with pytest.raises(ConfigError, match=match):
        load_config(cwd=tmp_path)


def test_duplicate_routes(tmp_path):
    write(
        tmp_path,
        """
        service: svc
        provider: {name: aws}
        functions:
          a: {handler: m.a, events: [{http: GET /x}]}
          b: {handler: m.b, events: [{http: GET /x/}]}
        """,
    )
    with pytest.raises(ConfigError, match="used by both"):
        load_config(cwd=tmp_path)


def test_missing_config(tmp_path):
    with pytest.raises(ConfigError, match="no config found"):
        load_config(cwd=tmp_path)


def test_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": [1]}}, {"a": {"c": [2], "d": 3}}) == {"a": {"b": 1, "c": [2], "d": 3}}


def test_child_file_beats_parent_provider_override(tmp_path):
    write(tmp_path, BASE, "base.yml")
    write(tmp_path, "extends: base.yml\nprovider:\n  name: gcp\n  region: asia-south1\n", "pskit.gcp.yml")
    cfg = load_config("pskit.gcp.yml", cwd=tmp_path).config
    assert cfg.provider.region == "asia-south1"  # child's explicit value wins
    assert cfg.provider.options == {"project": "my-proj"}  # parent's gcp override still applies


def test_provider_shorthand_string(tmp_path):
    write(tmp_path, "service: svc\nprovider: aws\n")
    assert load_config(cwd=tmp_path).config.provider.name == "aws"


def test_entry_point_provider_accepted(tmp_path, monkeypatch):
    from py_serverless_kit.providers import registry

    monkeypatch.setattr(registry, "_entry_points", lambda: {"mycloud": "pkg:Provider"})
    write(tmp_path, "service: svc\nprovider: {name: mycloud}\nproviders: {mycloud: {region: x1}}\n")
    cfg = load_config(cwd=tmp_path).config
    assert cfg.provider.name == "mycloud" and cfg.provider.region == "x1"


def test_provider_override_disables_items_on_one_cloud(tmp_path):
    from py_serverless_kit.config.loader import load_config

    (tmp_path / "pskit.yml").write_text(
        """
service: demo
provider: {name: aws}
functions:
  api: {handler: app.api, events: [{http: GET /x}, {queue: jobs}]}
  worker: {handler: app.worker}
workflows:
  flow: {start_at: s, states: {s: {type: task, function: worker}}}
providers:
  cloudflare:
    functions:
      api: {events: [{http: GET /x}]}
      worker: {enabled: false}
    workflows:
      flow: {enabled: false}
""",
        "utf-8",
    )
    aws = load_config(cwd=tmp_path).config
    assert sorted(aws.functions) == ["api", "worker"] and len(aws.functions["api"].events) == 2
    cf = load_config(cwd=tmp_path, provider="cloudflare").config
    assert list(cf.functions) == ["api"] and [e.type for e in cf.functions["api"].events] == ["http"]
    assert cf.disabled == {"functions": ["worker"], "workflows": ["flow"]}
