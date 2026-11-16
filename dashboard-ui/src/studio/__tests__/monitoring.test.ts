import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { monitoringOn, setMonitoring } from "../components/LogsMetrics";
import { groupResources } from "../components/DeployResources";
import type { DeployResource } from "../types";

describe("function logs / metrics switches", () => {
  test("on by default, provider default, function wins", () => {
    assert.equal(monitoringOn(undefined, undefined, "logs"), true);
    assert.equal(monitoringOn(undefined, { logs: false }, "logs"), false);
    assert.equal(monitoringOn({ logs: true }, { logs: false }, "logs"), true);
    assert.equal(monitoringOn(false, undefined, "metrics"), false);
  });

  test("only what differs from the inherited value is written", () => {
    assert.deepEqual(setMonitoring(undefined, undefined, "logs", false), { logs: false });
    assert.equal(setMonitoring({ logs: false }, undefined, "logs", true), undefined);
    assert.deepEqual(setMonitoring(undefined, { metrics: false }, "metrics", true), { metrics: true });
    assert.deepEqual(setMonitoring(false, undefined, "logs", true), { metrics: false });
  });
});

test("groupResources keeps the server order", () => {
  const row = (type: string, label: string): DeployResource => ({ type, category: label, category_label: label, description: "", count: 1, names: ["x"], optional: "" });
  const groups = groupResources([row("a", "Functions"), row("b", "Functions"), row("c", "Logs & metrics")]);
  assert.deepEqual(groups.map((g) => [g.label, g.rows.length]), [["Functions", 2], ["Logs & metrics", 1]]);
});

test("notDeployedOf lists the last deploy's failures by name", async () => {
  const { notDeployedOf } = await import("../components/DeployResources");
  assert.deepEqual(notDeployedOf(null), []);
  const data = {
    resources: [],
    last_deploy: { status: "partial", not_deployed: { worker: { step: "terraform apply", reason: "boom" }, api: { step: "configuration", reason: "bad" } } },
  };
  assert.deepEqual(notDeployedOf(data).map((i) => [i.name, i.step]), [["api", "configuration"], ["worker", "terraform apply"]]);
});
