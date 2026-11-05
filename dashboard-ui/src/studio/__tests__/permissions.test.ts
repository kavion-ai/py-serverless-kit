import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { projectNeeds } from "../permissions";

const base = { service: "demo", provider: { name: "aws" }, functions: { hello: { handler: "app.hello" } } };

describe("projectNeeds", () => {
  test("nothing changed needs nothing", () => {
    assert.deepEqual(projectNeeds(base, structuredClone(base)), []);
  });
  test("a new function needs create", () => {
    const next = { ...base, functions: { ...base.functions, other: { handler: "app.other" } } };
    assert.deepEqual(projectNeeds(base, next), [["functions", "c"]]);
  });
  test("a removed function needs delete", () => {
    assert.deepEqual(projectNeeds(base, { ...base, functions: {} }), [["functions", "d"]]);
  });
  test("removing the whole section needs delete", () => {
    const { functions: _gone, ...next } = base;
    assert.deepEqual(projectNeeds(base, next), [["functions", "d"]]);
  });
  test("a changed function needs update", () => {
    assert.deepEqual(projectNeeds(base, { ...base, functions: { hello: { handler: "app.new" } } }), [["functions", "u"]]);
  });
  test("a rename needs create and delete", () => {
    const needs = projectNeeds(base, { ...base, functions: { renamed: { handler: "app.hello" } } });
    assert.deepEqual(needs.map((n) => n.join("")).sort(), ["functionsc", "functionsd"]);
  });
  test("anything else needs update on project", () => {
    assert.deepEqual(projectNeeds(base, { ...base, service: "other" }), [["project", "u"]]);
  });
  test("workflows and resources count on their own", () => {
    assert.deepEqual(projectNeeds(base, { ...base, workflows: { flow: {} } }), [["workflows", "c"]]);
    assert.deepEqual(projectNeeds(base, { ...base, resources: { q: {} } }), [["resources", "c"]]);
  });
  test("a section that is not a map cannot slip through", () => {
    assert.deepEqual(projectNeeds(base, { ...base, functions: "x" }), [["functions", "u"]]);
  });
});
