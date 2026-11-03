"use strict";
// Event / Response / envelope / resources / logging / invoke: parity with the Python runtime.

const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { runtime, makeBundle, RUNTIME } = require("./helpers");

const { Event, HttpRequest, Record, Headers, Response, BatchResult, BadRequest, resources, resource, eventFromWire, invoke } = runtime();
const base = runtime("adapters/base");
const httpfn = runtime("adapters/httpfn");

test("headers are case-insensitive and join repeated values", () => {
  const h = new Headers([["X-A", "1"], ["x-a", "2"], ["Cookie", ["a=1", "b=2"]], ["Skip", null]]);
  assert.equal(h.get("x-A"), "1, 2");
  assert.equal(h.get("cookie"), "a=1, b=2");
  assert.equal(h.has("skip"), false);
  assert.equal(h.get("missing", "dflt"), "dflt");
});

test("http request helpers", () => {
  const req = new HttpRequest({
    method: "post",
    headers: { "Content-Type": "application/json; charset=utf-8", Cookie: "a=1; b=x=y" },
    body: '{"x": 1}',
    query: { q: "1" },
  });
  assert.equal(req.method, "POST");
  assert.equal(req.contentType, "application/json");
  assert.deepEqual(req.cookies, { a: "1", b: "x=y" });
  assert.deepEqual(req.json(), { x: 1 });
  assert.deepEqual(req.multiQuery, { q: ["1"] });
  const bad = new HttpRequest({ body: "{nope" });
  assert.throws(() => bad.json(), (err) => err instanceof BadRequest && err.message === "Request body is not valid JSON");
  assert.equal(bad.json(null), null);
  assert.throws(() => new HttpRequest().json(), /Request body is empty, expected JSON/);
  assert.deepEqual(new HttpRequest({ body: "a=1&b=two" }).form(), { a: "1", b: "two" });
  assert.equal(HttpRequest.decodeBody("aGk=", true).toString(), "hi");
});

test("records and event.json", () => {
  const rec = new Record({ id: "m1", body: '{"a": 1}' });
  assert.deepEqual(rec.json(), { a: 1 });
  assert.equal(new Record({ body: { a: 1 } }).text(), '{"a":1}');
  assert.throws(() => new Record({ id: "m2", body: "x" }).json(), /Record m2 body is not valid JSON/);
  const ev = new Event({ type: "queue", records: [rec] });
  assert.ok(ev.isBatch);
  assert.deepEqual(ev.json(), { a: 1 });
  assert.deepEqual([...ev].map((r) => r.id), ["m1"]);
  assert.equal(new Event({ type: "invoke", data: 5 }).json(), 5);
});

test("wire format round trip", () => {
  const ev = new Event({
    type: "http",
    provider: "onprem",
    function: "hello",
    time: "2026-01-02T03:04:05+00:00",
    http: new HttpRequest({ method: "PUT", path: "/x", headers: { A: "b" }, body: Buffer.from([0, 255]), pathParams: { id: "7" } }),
    records: [new Record({ id: "r", body: Buffer.from("bin") }), new Record({ id: "j", body: { k: 1 } })],
  });
  const wire = ev.toWire();
  assert.equal(wire.time, "2026-01-02T03:04:05.000000+00:00");
  assert.equal(wire.http.body_b64, "AP8=");
  assert.equal(wire.records[0].body_b64, Buffer.from("bin").toString("base64"));
  const back = eventFromWire(JSON.parse(JSON.stringify(wire)));
  assert.deepEqual([...back.http.body], [0, 255]);
  assert.equal(back.http.headers.get("a"), "b");
  assert.deepEqual(back.http.pathParams, { id: "7" });
  assert.equal(back.records[0].body.toString(), "bin");
  assert.deepEqual(back.records[1].body, { k: 1 });
  assert.equal(back.time.toISOString(), "2026-01-02T03:04:05.000Z");
});

test("response rendering", () => {
  const r = Response.json({ a: 1 }, 201, { "X-Y": "z" }).setCookie("s", "v", { maxAge: 10 });
  const out = r.render();
  assert.equal(out.status, 201);
  assert.deepEqual(out.headers, { "content-type": "application/json", "x-y": "z" });
  assert.equal(out.body.toString(), '{"a":1}');
  assert.deepEqual(r.cookies, ["s=v; Path=/; SameSite=Lax; Max-Age=10; HttpOnly; Secure"]);
  const gw = Response.binary(Buffer.from([1, 2]), "image/png").renderForGateway();
  assert.deepEqual(gw, { status: 200, headers: { "content-type": "image/png" }, body: "AQI=", isBase64: true });
  assert.deepEqual(Response.text("hi").renderForGateway().isBase64, false);
  assert.equal(Response.redirect("/x").render().headers.location, "/x");
  assert.equal(new Response(200, { a: [1] }).render().body.toString(), '{"a":[1]}');
});

test("envelopes", () => {
  assert.deepEqual(base.envelope("invoke", { a: 1 }), { __pskit: "invoke", data: { a: 1 } });
  assert.deepEqual(base.unwrapEnvelope('{"__pskit": "workflow", "data": 3, "source": "s"}'), ["workflow", 3, { source: "s" }]);
  assert.deepEqual(base.unwrapEnvelope({ __pskit: "weird", data: null }), ["invoke", null, {}]);
  assert.equal(base.unwrapEnvelope({ a: 1 }), null);
  assert.equal(base.maybeJson(Buffer.from(" [1] ")).length, 1);
  assert.equal(base.maybeJson("plain"), "plain");
  assert.equal(base.b64Text(Buffer.from("hé").toString("base64")), "hé");
  assert.equal(base.actionFrom("ObjectRemoved:Delete"), "deleted");
  assert.equal(base.actionFrom("OBJECT_FINALIZE"), "created");
});

test("http-only adapters: envelope requests become non-HTTP events", async () => {
  makeBundle({ "h.js": "exports.echo = (e) => ({ type: e.type, data: e.data });\nexports.fail = () => { throw new RangeError('out'); };\n" });
  const manifest = runtime("manifest");
  runtime("dispatch").clearHandlerCache();
  manifest.setManifest({ functions: { echo: { handler: "h.echo" }, fail: { handler: "h.fail" } } });
  const { Context } = runtime();
  const req = new HttpRequest({ method: "POST", body: JSON.stringify(base.envelope("workflow", { x: 1 })) });
  const ev = httpfn.eventFromRequest(req, "ibm", "echo");
  assert.equal(ev.type, "workflow");
  const ok = await httpfn.run(ev, new Context());
  assert.deepEqual(ok, { status: 200, headers: { "content-type": "application/json" }, body: '{"type":"workflow","data":{"x":1}}', isBase64: false });
  const bad = await httpfn.run(httpfn.eventFromRequest(new HttpRequest({ method: "POST", body: '{"__pskit":"invoke"}' }), "ibm", "fail"), new Context());
  assert.equal(bad.status, 500);
  assert.equal(bad.body, '{"errorType":"RangeError","cause":"out"}');
});

test("resources from the environment", () => {
  const env = {
    PSKIT_RESOURCES: "uploads,uploads_b",
    PSKIT_RESOURCE_UPLOADS_TYPE: "storage",
    PSKIT_RESOURCE_UPLOADS_NAME: "acme-uploads",
    PSKIT_RESOURCE_UPLOADS_EXTERNAL: "true",
    PSKIT_RESOURCE_UPLOADS_ENDPOINT: "https://s3",
    PSKIT_RESOURCE_UPLOADS_B_TYPE: "queue",
    PSKIT_RESOURCE_UPLOADS_B_URL: "https://q",
  };
  const all = resources(env);
  assert.deepEqual(Object.keys(all), ["uploads", "uploads_b"]);
  assert.equal(all.uploads.nativeName, "acme-uploads");
  assert.equal(all.uploads.external, true);
  assert.deepEqual(all.uploads.connection, { endpoint: "https://s3" }); // uploads_b vars not mixed in
  assert.equal(resource("UPLOADS-B", env).url, "https://q");
  assert.throws(() => resource("nope", env), /not bound to this function; bound: uploads, uploads_b/);
  assert.throws(() => all.uploads.require("missing"), /has no 'missing'; known: endpoint/);
});

test("batch result", () => {
  const r = BatchResult.of([new Record({ id: "a" }), "b", new Record({})]);
  assert.deepEqual(r.failed, ["a", "b"]);
  assert.equal(r.ok, false);
  assert.throws(() => r.raiseIfFailed(), /2 record\(s\) failed: a, b/);
});

test("invoke runs in-process locally and posts envelopes to PSKIT_ENDPOINT_*", async () => {
  makeBundle({ "t.js": "exports.add = (e) => e.data.a + 1;\n" });
  runtime("dispatch").clearHandlerCache();
  runtime("manifest").setManifest({ functions: { "add-one": { handler: "t.add" } } });
  delete process.env.PSKIT_PROVIDER;
  assert.equal(await invoke("add-one", { a: 1 }), 2);

  const http = require("node:http");
  let seen;
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen = JSON.parse(body);
      res.setHeader("content-type", "application/json");
      res.end('{"ok":true}');
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  process.env.PSKIT_ENDPOINT_ADD_ONE = `http://127.0.0.1:${server.address().port}/`;
  try {
    assert.deepEqual(await invoke("add-one", { a: 5 }), { ok: true });
    assert.deepEqual(seen, { __pskit: "invoke", data: { a: 5 } });
  } finally {
    delete process.env.PSKIT_ENDPOINT_ADD_ONE;
    server.close();
  }
  process.env.PSKIT_PROVIDER = "tencent";
  try {
    await assert.rejects(invoke("add-one"), /needs the target URL in \$PSKIT_ENDPOINT_ADD_ONE/);
  } finally {
    delete process.env.PSKIT_PROVIDER;
  }
});

test("logger writes Python-shaped JSON lines and honours the level", () => {
  const script = `
    const { Context } = require(${JSON.stringify(RUNTIME)});
    const ctx = new Context({ requestId: "r1", function: "fn", provider: "aws" });
    ctx.logger.debug("hidden");
    ctx.logger.info("hello é", { name: "x", count: 2 });
    ctx.logger.error("bad", { a: 1 }, new Error("boom"));
  `;
  const out = spawnSync(process.execPath, ["-e", script], { env: Object.assign({}, process.env, { PSKIT_LOG_LEVEL: "INFO", PSKIT_LOG_FORMAT: "json" }), encoding: "utf8" });
  const lines = out.stdout.trim().split("\n");
  assert.equal(lines.length, 2, out.stdout + out.stderr);
  assert.ok(lines[0].includes("\\u00e9"), "non-ASCII escaped like Python");
  const info = JSON.parse(lines[0]);
  assert.deepEqual(Object.keys(info), ["ts", "level", "logger", "message", "function", "request_id", "provider", "name_", "count"]);
  assert.equal(info.logger, "pskit.function");
  assert.equal(info.name_, "x"); // reserved LogRecord key gets a trailing "_"
  const err = JSON.parse(lines[1]);
  assert.equal(err.level, "ERROR");
  assert.match(err.exception, /Error: boom/);
});
