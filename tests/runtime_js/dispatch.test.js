"use strict";
// Port of tests/runtime/test_dispatch.py: the JS dispatcher must behave like the Python one.

const test = require("node:test");
const assert = require("node:assert/strict");
const { runtime, makeBundle } = require("./helpers");

const { Context, Event, HttpRequest, Response, BatchResult } = runtime();
const dispatch = runtime("dispatch");
const manifest = runtime("manifest");
const { matchPath } = runtime("routing");
const { HandlerNotFound, LookupError } = runtime("errors");

const HANDLERS = `
const { NotFound } = require("pskit_runtime_under_test");
exports.ok = (event, ctx) => ({ params: event.http ? event.http.pathParams : null, fn: ctx.function });
exports.one_arg = (event) => "single";
exports.async_handler = async (event, ctx) => ({ async: true });
exports.boom = () => { throw new Error("secret detail"); };
exports.not_found = () => { throw new NotFound("nope", { details: { id: 1 } }); };
exports.batch = (event) => { const r = new (require("pskit_runtime_under_test").BatchResult)(); r.fail("m2"); return r; };
exports.unicode = () => ({ name: "Zoë" });
exports.binary = () => Buffer.from([0, 1, 2]);
exports.nothing = () => undefined;
exports.nested = { deep: () => "deep" };
`;

function setup() {
  const root = makeBundle({
    "fake_handlers.js": HANDLERS.replace(/pskit_runtime_under_test/g, require("./helpers").RUNTIME.replace(/\\/g, "/")),
    "esm/mod.mjs": "export async function hello(event) { return { esm: true, type: event.type }; }\nexport default { other: () => 'default-export' };\n",
    "pkg/index.js": "exports.handler = () => 'index';",
  });
  dispatch.clearHandlerCache();
  manifest.setManifest({
    functions: {
      ok: {
        handler: "fake_handlers.ok",
        routes: [
          { method: "GET", path: "/users/{id}", cors: { origins: ["https://app.example"] } },
          { method: "DELETE", path: "/users/{id}" },
        ],
      },
      one: { handler: "fake_handlers:one_arg" },
      async: { handler: "fake_handlers.async_handler" },
      boom: { handler: "fake_handlers.boom" },
      nf: { handler: "fake_handlers.not_found" },
      batch: { handler: "fake_handlers.batch" },
      unicode: { handler: "fake_handlers.unicode" },
      binary: { handler: "fake_handlers.binary" },
      nothing: { handler: "fake_handlers.nothing" },
      nested: { handler: "fake_handlers:nested.deep" },
      esm: { handler: "esm.mod.hello" },
      esmdefault: { handler: "esm.mod.other" },
      index: { handler: "pkg.handler" },
      star: { handler: "fake_handlers.ok", routes: [{ method: "ANY", path: "/any", cors: true }] },
    },
  });
  return root;
}

function http(method = "GET", path = "/", init = {}) {
  return new Event({ type: "http", http: new HttpRequest(Object.assign({ method, path }, init)) });
}

test.beforeEach(setup);

test("route params and context", async () => {
  const resp = await dispatch.execute(http("GET", "/users/42"), new Context(), "ok");
  assert.ok(resp instanceof Response);
  assert.equal(resp.status, 200);
  assert.equal(resp.body, '{"params":{"id":"42"},"fn":"ok"}');
});

test("method not allowed", async () => {
  const resp = await dispatch.execute(http("POST", "/users/42"), new Context(), "ok");
  assert.equal(resp.status, 405);
  assert.equal(resp.headers.allow, "DELETE, GET");
  assert.equal(resp.body, '{"error":"Method Not Allowed","status":405}');
});

test("CORS preflight and headers", async () => {
  const pre = await dispatch.execute(http("OPTIONS", "/users/1", { headers: { Origin: "https://app.example" } }), new Context(), "ok");
  assert.equal(pre.status, 204);
  assert.equal(pre.headers["access-control-allow-origin"], "https://app.example");
  assert.equal(pre.headers.vary, "Origin");
  assert.equal(pre.headers["access-control-allow-methods"], "GET, POST, PUT, PATCH, DELETE, OPTIONS");
  assert.equal(pre.headers["access-control-allow-headers"], "Content-Type, Authorization, X-Requested-With");
  assert.equal(pre.headers["access-control-max-age"], "600");
  const resp = await dispatch.execute(http("GET", "/users/1", { headers: { Origin: "https://evil.example" } }), new Context(), "ok");
  assert.ok(!("access-control-allow-origin" in resp.headers));
  const star = await dispatch.execute(http("GET", "/any"), new Context(), "star");
  assert.equal(star.headers["access-control-allow-origin"], "*");
});

test("single arg, colon handler and nested attribute", async () => {
  assert.equal(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "one"), "single");
  assert.equal(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "nested"), "deep");
});

test("async handler", async () => {
  assert.deepEqual(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "async"), { async: true });
});

test("ESM module, default export and folder index", async () => {
  assert.deepEqual(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "esm"), { esm: true, type: "invoke" });
  assert.equal(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "esmdefault"), "default-export");
  assert.equal(await dispatch.execute(new Event({ type: "invoke" }), new Context(), "index"), "index");
});

for (const [debug, expectDetail] of [["", false], ["1", true]]) {
  test(`http 500 hides details (PSKIT_DEBUG=${debug})`, async () => {
    process.env.PSKIT_DEBUG = debug;
    try {
      const resp = await dispatch.execute(http("GET", "/x"), new Context({ requestId: "req-1" }), "boom");
      assert.equal(resp.status, 500);
      const expected = { error: "Internal Server Error", status: 500, request_id: "req-1" };
      if (expectDetail) expected.detail = "Error: secret detail";
      assert.equal(resp.body, JSON.stringify(expected));
    } finally {
      delete process.env.PSKIT_DEBUG;
    }
  });
}

test("http error mapping", async () => {
  const resp = await dispatch.execute(http("GET", "/x"), new Context(), "nf");
  assert.equal(resp.status, 404);
  assert.equal(resp.body, '{"error":"nope","status":404,"details":{"id":1}}');
});

test("non-http errors propagate", async () => {
  await assert.rejects(dispatch.execute(new Event({ type: "queue" }), new Context(), "boom"), /secret detail/);
});

test("unknown function", async () => {
  await assert.rejects(dispatch.execute(new Event({ type: "invoke" }), new Context(), "missing"), LookupError);
});

test("env handler fallback", async () => {
  manifest.setManifest({});
  process.env.PSKIT_HANDLER = "fake_handlers.one_arg";
  try {
    assert.equal(await dispatch.execute(new Event({ type: "invoke" }), new Context()), "single");
  } finally {
    delete process.env.PSKIT_HANDLER;
  }
});

for (const bad of ["nomodule", "fake_handlers.missing", "does_not_exist.fn"]) {
  test(`bad handler ${bad}`, async () => {
    await assert.rejects(dispatch.resolveHandler(bad), HandlerNotFound);
  });
}

test("batch results pass through on aws/local/onprem and fail elsewhere", async () => {
  const local = await dispatch.execute(new Event({ type: "queue", provider: "aws" }), new Context(), "batch");
  assert.ok(local instanceof BatchResult);
  assert.deepEqual(local.failed, ["m2"]);
  await assert.rejects(dispatch.execute(new Event({ type: "queue", provider: "gcp" }), new Context(), "batch"), /1 record\(s\) failed: m2/);
});

test("results become responses like Python to_response", async () => {
  const uni = await dispatch.execute(http("GET", "/x"), new Context(), "unicode");
  assert.equal(uni.body, '{"name":"Zo\\u00eb"}'); // ensure_ascii, like Python json.dumps
  const bin = (await dispatch.execute(http("GET", "/x"), new Context(), "binary")).render();
  assert.equal(bin.headers["content-type"], "application/octet-stream");
  assert.deepEqual([...bin.body], [0, 1, 2]);
  const none = await dispatch.execute(http("GET", "/x"), new Context(), "nothing");
  assert.equal(none.status, 204);
  const text = await dispatch.execute(http("GET", "/x"), new Context(), "one");
  assert.equal(text.render().headers["content-type"], "text/plain; charset=utf-8");
});

const PATHS = [
  ["/users/{id}", "/users/7", { id: "7" }],
  ["/users/{id}", "/users/7/x", null],
  ["/files/{path+}", "/files/a/b/c.txt", { path: "a/b/c.txt" }],
  ["/users/{id}", "/7", { id: "7" }], // GCP style: static prefix stripped
  ["/users/{id}", "/api/users/7", { id: "7" }], // Azure style: extra prefix
  ["/hello", "/hello", {}],
  ["/hello", "/other", null],
];
for (const [pattern, p, expected] of PATHS) {
  test(`matchPath ${pattern} ${p}`, () => {
    assert.deepEqual(matchPath(pattern, p), expected);
  });
}

test("matchPath strict", () => {
  assert.equal(matchPath("/users/{id}", "/7", { tolerant: false }), null);
});
