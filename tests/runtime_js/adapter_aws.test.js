"use strict";
// node --test tests/runtime_js/adapter_aws.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RT = path.join(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");

function bundle(functions, source) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pskit-aws-"));
  fs.writeFileSync(path.join(root, "handlers.js"), source);
  fs.writeFileSync(path.join(root, "pskit_manifest.json"), JSON.stringify({ service: "svc", stage: "dev", provider: "aws", functions }));
  process.env.PSKIT_BUNDLE_ROOT = root;
  require(path.join(RT, "manifest")).setManifest(null);
  require(path.join(RT, "dispatch")).clearHandlerCache();
  return root;
}

const HANDLERS = `
const { Response, BatchResult } = require(${JSON.stringify(path.join(RT, "index"))});
exports.hello = async (event, ctx) => ({ name: event.http.query.name || "world", id: event.http.pathParams.id || null, fn: ctx.function });
exports.cookie = () => Response.json({ ok: true }).setCookie("a", "1").setCookie("b", "2");
exports.worker = (event) => BatchResult.of(event.records.filter((r) => r.text() === "bad"));
exports.echo = (event) => ({ type: event.type, data: event.data });
exports.files = (event) => event.records.map((r) => [r.bucket, r.key, r.action]);
`;

const FUNCTIONS = {
  hello: { handler: "handlers.hello", routes: [{ method: "GET", path: "/users/{id}" }] },
  cookie: { handler: "handlers.cookie", routes: [{ method: "GET", path: "/c" }] },
  worker: { handler: "handlers.worker", routes: [] },
  echo: { handler: "handlers.echo", routes: [] },
  files: { handler: "handlers.files", routes: [] },
};

test("API Gateway v2 HTTP event with path params and query", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "hello";
  const aws = require(path.join(RT, "adapters", "aws"));
  const out = await aws.handler({
    version: "2.0",
    routeKey: "GET /users/{id}",
    rawPath: "/users/7",
    queryStringParameters: { name: "Ada" },
    pathParameters: { id: "7" },
    headers: {},
    requestContext: { http: { method: "GET", path: "/users/7", sourceIp: "1.2.3.4" } },
    isBase64Encoded: false,
  }, { awsRequestId: "r1", getRemainingTimeInMillis: () => 1000, memoryLimitInMB: "128" });
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { name: "Ada", id: "7", fn: "hello" });
});

test("cookies: v2 uses cookies, v1 multiValueHeaders", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "cookie";
  const aws = require(path.join(RT, "adapters", "aws"));
  const v2 = await aws.handler({ version: "2.0", rawPath: "/c", headers: {}, requestContext: { http: { method: "GET", path: "/c" } } });
  assert.deepStrictEqual(v2.cookies.length, 2);
  const v1 = await aws.handler({ httpMethod: "GET", path: "/c", headers: {} });
  assert.strictEqual(v1.multiValueHeaders["set-cookie"].length, 2);
});

test("SQS batch reports failed message ids", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "worker";
  const aws = require(path.join(RT, "adapters", "aws"));
  const out = await aws.handler({
    Records: [
      { eventSource: "aws:sqs", messageId: "m1", body: "ok", eventSourceARN: "arn:q" },
      { eventSource: "aws:sqs", messageId: "m2", body: "bad", eventSourceARN: "arn:q" },
    ],
  });
  assert.deepStrictEqual(out, { batchItemFailures: [{ itemIdentifier: "m2" }] });
});

test("S3 keys are url-decoded and actions mapped", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "files";
  const aws = require(path.join(RT, "adapters", "aws"));
  const out = await aws.handler({
    Records: [{ eventSource: "aws:s3", eventName: "ObjectRemoved:Delete", s3: { bucket: { name: "b" }, object: { key: "a+b%2Fc.txt" } } }],
  });
  assert.deepStrictEqual(out, [["b", "a b/c.txt", "deleted"]]);
});

test("pskit envelope and EventBridge schedule", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "echo";
  const aws = require(path.join(RT, "adapters", "aws"));
  assert.deepStrictEqual(await aws.handler({ __pskit: "workflow", data: { x: 1 } }), { type: "workflow", data: { x: 1 } });
  assert.deepStrictEqual(await aws.handler({ source: "aws.events", detail: { y: 2 } }), { type: "schedule", data: { y: 2 } });
  assert.deepStrictEqual(await aws.handler({ any: "thing" }), { type: "invoke", data: { any: "thing" } });
});
