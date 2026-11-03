import json
import re

from py_serverless_kit.core.describe import build_record
from py_serverless_kit.dashboard.generator import collect_records, render_html, write_dashboard


def test_render_escapes_script_breakout(make_project):
    project = make_project(
        """
        service: dash
        provider: {name: aws}
        functions:
          x:
            handler: app.handlers.hello
            description: "</script><script>alert(1)</script>"
        """
    )
    html = render_html([build_record(project)], title="<b>t</b>")
    assert "<title>&lt;b&gt;t&lt;/b&gt;</title>" in html
    payload = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1)
    assert "</script>" not in payload
    data = json.loads(payload.replace("<\\/", "</"))
    assert data["deployments"][0]["functions"][0]["description"].startswith("</script>")


def test_collect_and_write(make_project, tmp_path):
    project = make_project("service: dash\nprovider: {name: aws}\nfunctions: {a: {handler: app.handlers.hello}}\n")
    work = project.work_dir
    work.mkdir(parents=True)
    (work / "deployment.json").write_text(json.dumps(build_record(project)))
    (project.root / ".pskit" / "broken-dev").mkdir()
    (project.root / ".pskit" / "broken-dev" / "deployment.json").write_text("{not json")
    records = collect_records(project.root)
    assert len(records) == 1 and records[0]["service"] == "dash"
    out = write_dashboard(project.root)
    assert out.name == "index.html" and "dash dashboard" in out.read_text("utf-8")
