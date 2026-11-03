import { describe, test } from "node:test";
import assert from "node:assert/strict";
import {
  applyRunsOn,
  assignFunction,
  deployTargetWhere,
  groupOf,
  groupOfResource,
  hasRunsOnErrors,
  hostResource,
  moveFunction,
  NEW_GROUP,
  portClash,
  readPlacement,
  renameInPlacement,
  runsOnErrors,
  type RunsOnChoice,
} from "../placement";
import type { JsonObject } from "../types";

/** The example from docs/placement.md as the studio sees it. */
function project(): JsonObject {
  return {
    service: "my-service",
    provider: {
      name: "onprem",
      options: {
        placement: {
          default: "test-01",
          groups: {
            "test-01": { server: "VM_01_2cpu", port: 3000, functions: ["hello"] },
            "test-02": { server: "VM_03_2cpu", functions: ["get-item"] },
            "test-03": { server: "VM_01_2cpu", port: 8081, functions: ["create-item"] },
          },
        },
      },
    },
    functions: {
      hello: { handler: "app.handlers.hello" },
      "get-item": { handler: "app.handlers.get_item" },
      "create-item": { handler: "app.handlers.create_item" },
    },
  };
}

function noPlacement(): JsonObject {
  return { service: "s", provider: { name: "onprem", options: { deploy: { server: "VM_01_2cpu" } } }, functions: { hello: { handler: "app.handlers.hello" } } };
}

const groups = (draft: JsonObject) => (readPlacement(draft)?.raw.groups || {}) as Record<string, JsonObject>;

function choice(patch: Partial<RunsOnChoice>): RunsOnChoice {
  return { group: NEW_GROUP, name: "", target: "", port: undefined, defaultName: "main", ...patch };
}

describe("assignFunction", () => {
  test("moves a function out of every group into the chosen one", () => {
    const out = assignFunction(project(), "hello", "test-02");
    assert.deepEqual(groups(out)["test-02"].functions, ["get-item", "hello"]);
    assert.equal(groups(out)["test-01"].functions, undefined, "the empty list is dropped");
    assert.equal(groupOf(readPlacement(out), "hello"), "test-02");
  });

  test("the default group needs no listing", () => {
    const out = assignFunction(project(), "get-item", "test-01");
    assert.deepEqual(groups(out)["test-01"].functions, ["hello"]);
    assert.equal(groups(out)["test-02"].functions, undefined);
    assert.equal(groupOf(readPlacement(out), "get-item"), "test-01");
  });

  test("creates a new group holding the function", () => {
    const out = assignFunction(project(), "create-item", "gpu", { name: "gpu", body: { cluster: "prod" } });
    assert.deepEqual(groups(out).gpu, { cluster: "prod", functions: ["create-item"] });
    assert.equal(groups(out)["test-03"].functions, undefined);
    assert.equal(readPlacement(out)?.default, "test-01");
  });

  test("without placement, creates it: the deploy target becomes the default group", () => {
    const out = assignFunction(noPlacement(), "hello", "edge", { name: "edge", body: { server: "VM_03_2cpu", port: 8081 } });
    const p = readPlacement(out);
    assert.equal(p?.default, "main");
    assert.deepEqual(p?.raw.groups, { main: {}, edge: { server: "VM_03_2cpu", port: 8081, functions: ["hello"] } });
    assert.deepEqual((out.provider as JsonObject).options, {
      deploy: { server: "VM_01_2cpu" },
      placement: { default: "main", groups: { main: {}, edge: { server: "VM_03_2cpu", port: 8081, functions: ["hello"] } } },
    });
  });

  test("without placement and without a new group, nothing changes", () => {
    const draft = noPlacement();
    assert.equal(assignFunction(draft, "hello", ""), draft);
    assert.equal(moveFunction(draft, "hello", "x"), draft);
  });

  test("writes to a providers.onprem override when that holds the placement", () => {
    const draft: JsonObject = {
      provider: { name: "onprem" },
      providers: { onprem: { options: { placement: { default: "a", groups: { a: {}, b: { local: true, functions: "f" } } } } } },
      functions: { f: {}, g: {} },
    };
    const out = assignFunction(draft, "g", "b");
    const placement = ((out.providers as JsonObject).onprem as JsonObject).options as JsonObject;
    assert.deepEqual((placement.placement as JsonObject).groups, { a: {}, b: { local: true, functions: ["f", "g"] } });
    assert.equal((out.provider as JsonObject).options, undefined);
  });
});

describe("rename and delete", () => {
  test("renaming a function renames it in its group", () => {
    const out = renameInPlacement(project(), "get-item", "fetch-item");
    assert.deepEqual(groups(out)["test-02"].functions, ["fetch-item"]);
  });

  test("deleting a function removes it from its group", () => {
    const out = renameInPlacement(project(), "create-item", null);
    assert.equal(groups(out)["test-03"].functions, undefined);
    assert.deepEqual(groups(out)["test-03"], { server: "VM_01_2cpu", port: 8081 });
  });

  test("an unlisted function leaves the draft alone", () => {
    const draft = project();
    assert.equal(renameInPlacement(draft, "nope", "x"), draft);
  });
});

describe("ports", () => {
  test("a group on a server with the same port clashes and gets the next free port", () => {
    assert.deepEqual(portClash(project(), "server:VM_01_2cpu", 3000), { group: "test-01", port: 3000, suggestion: 3001 });
    assert.deepEqual(portClash(project(), "server:VM_01_2cpu", 8081), { group: "test-03", port: 8081, suggestion: 8082 });
    assert.equal(portClash(project(), "server:VM_01_2cpu", undefined), null, "8080 is free there");
    assert.deepEqual(portClash(project(), "server:VM_03_2cpu", undefined), { group: "test-02", port: 8080, suggestion: 8081 });
    assert.equal(portClash(project(), "server:VM_03_2cpu", 9000), null);
    assert.equal(portClash(project(), "cluster:prod", 3000), null, "clusters are not checked");
  });

  test("the suggestion skips ports other groups use", () => {
    const draft = project();
    const g = groups(draft);
    g["test-03"].port = 3001;
    assert.deepEqual(portClash(draft, "server:VM_01_2cpu", 3000), { group: "test-01", port: 3000, suggestion: 3002 });
  });

  test("the default group without a target counts on the deploy target", () => {
    const draft = noPlacement();
    const where = deployTargetWhere(draft);
    assert.equal(where, "server:VM_01_2cpu");
    assert.deepEqual(portClash(draft, "server:VM_01_2cpu", undefined, where), { group: "main", port: 8080, suggestion: 8081 });
    assert.equal(portClash(draft, "server:VM_01_2cpu", 8081, where), null);
    assert.equal(portClash(draft, "local", undefined, where), null);
  });

  test("provider.options.port is every group's default", () => {
    const draft = noPlacement();
    ((draft.provider as JsonObject).options as JsonObject).port = 9000;
    assert.deepEqual(portClash(draft, "server:VM_01_2cpu", undefined, "server:VM_01_2cpu"), { group: "main", port: 9000, suggestion: 9001 });
  });
});

describe("Runs on", () => {
  test("validates the new group", () => {
    const draft = project();
    assert.ok(runsOnErrors(draft, choice({ name: "Bad_Name", target: "local" })).name);
    assert.ok(runsOnErrors(draft, choice({ name: "test-02", target: "local" })).name, "taken");
    assert.ok(runsOnErrors(draft, choice({ name: "gpu", target: "" })).target);
    const clash = runsOnErrors(draft, choice({ name: "gpu", target: "server:VM_01_2cpu", port: 3000 }));
    assert.equal(clash.suggestPort, 3001);
    assert.ok(hasRunsOnErrors(clash));
    assert.equal(hasRunsOnErrors(runsOnErrors(draft, choice({ name: "gpu", target: "server:VM_01_2cpu", port: 3001 }))), false);
    assert.equal(hasRunsOnErrors(runsOnErrors(draft, choice({ group: "test-02" }))), false, "an existing group is always fine");
  });

  test("without placement the default group's name is checked too", () => {
    const draft = noPlacement();
    assert.ok(runsOnErrors(draft, choice({ name: "main", target: "local" })).name);
    assert.ok(runsOnErrors(draft, choice({ name: "gpu", target: "local", defaultName: "" })).defaultName);
    assert.equal(hasRunsOnErrors(runsOnErrors(draft, choice({ name: "gpu", target: "local" }))), false);
  });

  test("applies a new group with its port", () => {
    const out = applyRunsOn(project(), "hello", choice({ name: "test-04", target: "server:VM_01_2cpu", port: 3001 }));
    assert.deepEqual(groups(out)["test-04"], { server: "VM_01_2cpu", port: 3001, functions: ["hello"] });
    assert.equal(groups(out)["test-01"].functions, undefined);
  });

  test("applies an existing group", () => {
    const out = applyRunsOn(project(), "hello", choice({ group: "test-03" }));
    assert.deepEqual(groups(out)["test-03"].functions, ["create-item", "hello"]);
  });

  test("names the default group when it creates the placement", () => {
    const out = applyRunsOn(noPlacement(), "hello", choice({ name: "gpu", target: "local", defaultName: "api" }));
    assert.equal(readPlacement(out)?.default, "api");
    assert.deepEqual(groups(out), { api: {}, gpu: { local: true, functions: ["hello"] } });
  });
});

describe("host resources", () => {
  test("map to placement groups", () => {
    const p = readPlacement(project());
    assert.equal(hostResource("test-01", "test-01"), "host");
    assert.equal(hostResource("test-02", "test-01"), "host_test_02");
    assert.equal(groupOfResource("host", p), "test-01");
    assert.equal(groupOfResource("host_test_02", p), "test-02");
    assert.equal(groupOfResource("host_other_x", p), "other-x");
    assert.equal(groupOfResource("host", null), "host");
  });
});
