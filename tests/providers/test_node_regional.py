"""Node.js on Alibaba, Tencent, Huawei, Oracle, IBM and DigitalOcean: runtime ids, shims, rendering.

Rendering here skips packaging (npm/tsc are the builder's job) and calls the provider directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from py_serverless_kit.providers.base import Artifact, RenderContext

NODE_CONFIG = """
service: demo
provider:
  name: {provider}
  runtime: {runtime}
  options: {options}
functions:
  hello:
    handler: src.handlers.hello
    events:
      - http: GET /hello
  step:
    handler: src.handlers.step
"""

OPTIONS = {
    "oracle": '{"compartment_id": "ocid1.compartment.oc1..x", "subnet_ids": ["ocid1.subnet.oc1..x"], "image": "img:1"}',
    "digitalocean": '{"namespace": "fn-123"}',
    "huawei": '{"apig_instance_id": "abc"}',
}

CASES = [
    ("alibaba", "nodejs20", "nodejs20", "index.js", "exports.handler"),
    ("alibaba", "nodejs18", "nodejs18", "index.js", "exports.handler"),
    ("tencent", "nodejs18", "Nodejs18.15", "index.js", "exports.main_handler"),
    ("huawei", "nodejs18", "Node.js18.15", "index.js", "exports.handler"),
    ("ibm", "nodejs20", "nodejs-20", "index.js", "exports.main"),
    ("digitalocean", "nodejs18", "nodejs:18", "index.js", "exports.main"),
    ("oracle", "nodejs20", "20", "func.js", "fdk.handle"),
]


def _project(make_project, provider: str, runtime: str):
    return make_project(NODE_CONFIG.format(provider=provider, runtime=runtime, options=OPTIONS.get(provider, "{}")))


def _render(project, tmp_path: Path) -> dict:
    work = project.work_dir
    work.mkdir(parents=True, exist_ok=True)
    (work / "artifact.zip").write_bytes(b"zip")
    build = tmp_path.parent / f"{tmp_path.name}-build"
    build.mkdir(exist_ok=True)
    (build / "index.js").write_text("exports.main = () => 1;\n", "utf-8")
    artifact = Artifact(path=work / "artifact.zip", sha256="0" * 64, sha256_b64="", size=3, build_dir=build)
    ctx = RenderContext(
        config=project.config,
        provider=project.provider,
        root=project.root,
        work_dir=work,
        artifact=artifact,
        region=project.region,
        workflow_engines=dict(project.engines),
    )
    return project.provider.render(ctx).to_dict()


@pytest.mark.parametrize("provider,runtime,native,shim,export", CASES)
def test_node_runtime_id_and_shim(make_project, provider, runtime, native, shim, export):
    project = _project(make_project, provider, runtime)
    assert project.config.language == "node"
    assert project.provider.runtime_id(runtime) == native
    files = project.provider.shim_files(project.config)
    assert shim in files and export in files[shim]
    assert f"pskit_runtime/adapters/{provider}" in files[shim]
    assert not any(name.endswith(".py") for name in files)
    errors = [str(i) for i in project.validate() if i.level == "error"]
    assert not any("runtime" in e.lower() or "node" in e.lower() for e in errors), errors


@pytest.mark.parametrize("provider", ["tencent", "huawei", "digitalocean"])
def test_unsupported_node_version_is_an_error(make_project, provider):
    project = _project(make_project, provider, "nodejs24")
    errors = [str(i) for i in project.validate() if i.level == "error"]
    assert any("does not support nodejs24" in e for e in errors), errors


def _resources(doc: dict, rtype: str) -> dict:
    return doc.get("resource", {}).get(rtype, {})


def test_alibaba_renders_node_runtime(make_project, tmp_path):
    doc = _render(_project(make_project, "alibaba", "nodejs20"), tmp_path)
    fns = _resources(doc, "alicloud_fcv3_function")
    assert {f["runtime"] for f in fns.values()} == {"nodejs20"}
    assert {f["handler"] for f in fns.values()} == {"index.handler"}


def test_tencent_renders_node_runtime(make_project, tmp_path):
    doc = _render(_project(make_project, "tencent", "nodejs18"), tmp_path)
    fns = _resources(doc, "tencentcloud_scf_function")
    assert {f["runtime"] for f in fns.values()} == {"Nodejs18.15"}
    assert {f["handler"] for f in fns.values()} == {"index.main_handler"}


def test_huawei_renders_node_runtime(make_project, tmp_path):
    doc = _render(_project(make_project, "huawei", "nodejs18"), tmp_path)
    fns = _resources(doc, "huaweicloud_fgs_function")
    assert {f["runtime"] for f in fns.values()} == {"Node.js18.15"}


def test_ibm_renders_node_runtime(make_project, tmp_path):
    doc = _render(_project(make_project, "ibm", "nodejs20"), tmp_path)
    fns = _resources(doc, "ibm_code_engine_function")
    assert {f["runtime"] for f in fns.values()} == {"nodejs-20"}
    assert {f["code_main"] for f in fns.values()} == {"main"}


def test_digitalocean_project_spec_uses_node_runtime(make_project, tmp_path):
    project = _project(make_project, "digitalocean", "nodejs18")
    _render(project, tmp_path)
    text = (project.work_dir / "do_project" / "project.yml").read_text("utf-8")
    assert "runtime: nodejs:18" in text and "main: main" in text


def test_oracle_node_image_files(make_project):
    project = _project(make_project, "oracle", "nodejs18")
    files = project.provider.shim_files(project.config)
    assert "FROM fnproject/node:18-dev AS build-stage" in files["Dockerfile"]
    assert "@fnproject/fdk" in files["Dockerfile"] and 'ENTRYPOINT ["node", "func.js"]' in files["Dockerfile"]
    assert "runtime: node" in files["func.yaml"] and "run_image: fnproject/node:18" in files["func.yaml"]
    assert project.provider.node_vendor_dependencies is False


def test_python_shims_unchanged(make_project):
    project = make_project(NODE_CONFIG.format(provider="alibaba", runtime="python3.12", options="{}"))
    assert "index.py" in project.provider.shim_files(project.config)
