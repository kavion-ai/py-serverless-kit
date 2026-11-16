import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { formatLimit, packageTypeOf, withPackageType } from "../components/Packaging";

describe("package.type in the draft", () => {
  test("defaults to zip", () => {
    assert.equal(packageTypeOf({}), "zip");
    assert.equal(packageTypeOf({ package: { type: "tar" } }), "zip");
    assert.equal(packageTypeOf({ package: { type: "image" } }), "image");
  });

  test("setting image keeps the other package settings", () => {
    const next = withPackageType({ service: "s", package: { exclude: ["docs/**"] } }, "image");
    assert.deepEqual(next, { service: "s", package: { exclude: ["docs/**"], type: "image" } });
  });

  test("zip removes the key, and an empty package block", () => {
    assert.deepEqual(withPackageType({ service: "s", package: { type: "auto" } }, "zip"), { service: "s" });
    assert.deepEqual(withPackageType({ package: { type: "image", source: "src" } }, "zip"), { package: { source: "src" } });
  });
});

test("formatLimit", () => {
  assert.equal(formatLimit(250 * 1024 ** 2), "250 MB");
  assert.equal(formatLimit(10 * 1024 ** 3), "10 GB");
  assert.equal(formatLimit(null), "");
});
