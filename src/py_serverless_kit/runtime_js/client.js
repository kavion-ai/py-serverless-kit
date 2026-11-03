"use strict";
/**
 * Use an on-premises pskit host from any Node.js (18+) program. No dependencies.
 *
 *   const { PskitClient } = require("pskit");
 *   const client = new PskitClient("http://10.0.0.5:8080", { token: "..." }); // or PSKIT_HOST / PSKIT_ADMIN_TOKEN
 *
 *   const jobs = client.queue("jobs");                 // a resource key or a native queue name
 *   await jobs.send({ orderId: 1 }, { kind: "new" });
 *   const page = await jobs.peek({ limit: 20 });       // look without consuming
 *   for (const msg of await jobs.receive({ batch: 10, visibility: 60 })) { console.log(msg.body); await msg.ack(); }
 *
 *   const files = client.bucket("uploads");
 *   await files.put("in/a.csv", "a,b\n"); await files.get("in/a.csv"); await files.list({ prefix: "in/" });
 *   await client.topic("events").publish({ id: 1 }, { type: "paid" });
 *   await client.invoke("report", { day: "2026-10-22" });
 *
 * Everything goes through the host's /__pskit HTTP API, so only the host port must be reachable;
 * the queue or bucket may use any driver. Get the package outside a pskit project with
 * `pskit client install-node` (copies it to ./node_modules/pskit).
 */

class PskitClientError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "PskitClientError";
    this.status = status;
  }
}

const seg = (s) => encodeURIComponent(String(s));
const keyPath = (k) => String(k).split("/").filter(Boolean).map(seg).join("/");

class PskitClient {
  constructor(endpoint, options = {}) {
    let base = endpoint || process.env.PSKIT_HOST || process.env.PSKIT_ENDPOINT || "";
    if (!base) throw new PskitClientError("no host: new PskitClient('http://host:8080') or set PSKIT_HOST");
    if (!/^https?:\/\//.test(base)) base = "http://" + base;
    this.endpoint = base.replace(/\/+$/, "");
    this.token = options.token !== undefined ? options.token : process.env.PSKIT_ADMIN_TOKEN || "";
    this.timeout = options.timeout || 10000;
    this._names = null;
  }

  async request(method, path, { body, raw, query, binary } = {}) {
    let url = this.endpoint + path;
    const params = Object.entries(query || {}).filter(([, v]) => v !== undefined && v !== null && v !== "");
    if (params.length) url += "?" + new URLSearchParams(params.map(([k, v]) => [k, String(v)])).toString();
    const headers = {};
    if (this.token) headers["x-pskit-token"] = this.token;
    let data;
    if (raw !== undefined) data = raw;
    else if (body !== undefined) {
      headers["content-type"] = "application/json";
      data = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await fetch(url, { method, headers, body: data, signal: AbortSignal.timeout(this.timeout) });
    } catch (err) {
      throw new PskitClientError(
        `the pskit host at ${this.endpoint} is not reachable (${err.cause ? err.cause.code || err.cause.message : err.message}). ` +
          "Check that it runs (pskit info), that its port is open from this machine (cloud firewall / security group), " +
          "or reach it through an SSH tunnel: ssh -N -L 8080:127.0.0.1:<port> user@server",
      );
    }
    if (!resp.ok) {
      let text = await resp.text();
      try {
        const parsed = JSON.parse(text);
        text = parsed.error || parsed.cause || text;
      } catch (_) {
        /* not JSON */
      }
      const hint = resp.status === 401 ? " (set { token } or PSKIT_ADMIN_TOKEN to the host's admin_token)" : "";
      throw new PskitClientError(`${method} ${path}: HTTP ${resp.status}: ${text}${hint}`, resp.status);
    }
    if (binary) return Buffer.from(await resp.arrayBuffer());
    const text = await resp.text();
    return text ? JSON.parse(text) : null;
  }

  health() {
    return this.request("GET", "/__pskit/health");
  }

  async resources() {
    return (await this.request("GET", "/__pskit/resources")).items;
  }

  async _resolve(name, kind) {
    if (this._names === null) {
      try {
        this._names = Object.fromEntries((await this.resources()).map((r) => [r.key, r]));
      } catch (_) {
        this._names = {};
      }
    }
    return this._names[name] || Object.values(this._names).find((r) => r.name === name && r.type === kind) || { key: null, name, type: kind };
  }

  queue(name) {
    return new Queue(this, name, "queue");
  }

  bucket(name) {
    return new Bucket(this, name, "storage");
  }

  topic(name) {
    return new Topic(this, name, "topic");
  }

  check(key) {
    return this.request("POST", `/__pskit/resources/${seg(key)}/check`, { body: {} });
  }

  async invoke(fn, data) {
    const out = await this.request("POST", `/__pskit/invoke/${seg(fn)}`, { body: data === undefined ? null : data });
    return out && Object.prototype.hasOwnProperty.call(out, "result") ? out.result : out;
  }

  startWorkflow(workflow, data, { wait = false } = {}) {
    return this.request("POST", `/__pskit/workflows/${seg(workflow)}`, { body: data === undefined ? null : data, query: { wait: wait ? "true" : undefined } });
  }

  execution(id) {
    return this.request("GET", `/__pskit/executions/${seg(id)}`);
  }
}

class Resource {
  constructor(client, name, kind) {
    this.client = client;
    this.requested = name;
    this.kind = kind;
    this._info = null;
  }

  async info() {
    if (!this._info) this._info = await this.client._resolve(this.requested, this.kind);
    return this._info;
  }

  async _page(path, query) {
    const out = await this.client.request("GET", path, { query });
    return { items: out.items || [], total: out.total ?? null, offset: query.offset || 0, limit: query.limit || 0, supported: out.supported !== false, note: out.note || "" };
  }
}

class Queue extends Resource {
  async send(message, attributes = {}) {
    const { name } = await this.info();
    const out = await this.client.request("POST", `/__pskit/queues/${seg(name)}`, { body: { message, attributes } });
    return (out.queued || [""])[0];
  }

  async sendBatch(messages) {
    const { name } = await this.info();
    return (await this.client.request("POST", `/__pskit/queues/${seg(name)}`, { body: { messages } })).queued || [];
  }

  async depth() {
    const { name } = await this.info();
    const d = (await this.client.request("GET", `/__pskit/queues/${seg(name)}`)).depth;
    return typeof d === "number" && d >= 0 ? d : null;
  }

  /** Waiting messages, oldest first, without consuming them. */
  async peek({ offset = 0, limit = 20 } = {}) {
    const { key, name } = await this.info();
    return key ? this._page(`/__pskit/resources/${seg(key)}/data`, { offset, limit }) : this._page(`/__pskit/queues/${seg(name)}/peek`, { offset, limit });
  }

  /** Lease messages (built-in queues). Don't receive from a queue a pskit trigger consumes. */
  async receive({ batch = 10, visibility = 60 } = {}) {
    const { name } = await this.info();
    const out = await this.client.request("POST", `/__pskit/queues/${seg(name)}/lease`, { body: { batch, visibility } });
    return (out.messages || []).map((m) => ({
      ...m,
      json() {
        try {
          return JSON.parse(m.body);
        } catch (_) {
          return m.body;
        }
      },
      ack: () => this.ack([m]),
      nack: () => this.nack([m]),
    }));
  }

  async ack(messages) {
    const { name } = await this.info();
    return (await this.client.request("POST", `/__pskit/queues/${seg(name)}/ack`, { body: { receipts: messages.map((m) => m.receipt) } })).acked;
  }

  async nack(messages) {
    const { name } = await this.info();
    return (await this.client.request("POST", `/__pskit/queues/${seg(name)}/nack`, { body: { receipts: messages.map((m) => m.receipt) } })).released;
  }
}

class Topic extends Resource {
  async publish(message, attributes = {}) {
    const { name } = await this.info();
    return ((await this.client.request("POST", `/__pskit/topics/${seg(name)}`, { body: { message, attributes } })).published || [""])[0];
  }

  async peek({ offset = 0, limit = 20 } = {}) {
    const { key, name } = await this.info();
    if (!key) throw new PskitClientError(`topic ${name} is not a resource of this host`);
    return this._page(`/__pskit/resources/${seg(key)}/data`, { offset, limit });
  }
}

class Bucket extends Resource {
  async put(key, data) {
    const { name } = await this.info();
    await this.client.request("PUT", `/__pskit/storage/${seg(name)}/${keyPath(key)}`, { raw: typeof data === "string" ? data : Buffer.from(data) });
  }

  async get(key) {
    const { name } = await this.info();
    return this.client.request("GET", `/__pskit/storage/${seg(name)}/${keyPath(key)}`, { binary: true });
  }

  async delete(key) {
    const { name } = await this.info();
    return Boolean((await this.client.request("DELETE", `/__pskit/storage/${seg(name)}/${keyPath(key)}`)).deleted);
  }

  async list({ prefix = "", offset = 0, limit = 100 } = {}) {
    const { name } = await this.info();
    return this._page(`/__pskit/storage/${seg(name)}`, { prefix, offset, limit });
  }

  /** Every key below `prefix`, page by page. */
  async *keys({ prefix = "", pageSize = 500 } = {}) {
    let offset = 0;
    for (;;) {
      const page = await this.list({ prefix, offset, limit: pageSize });
      for (const item of page.items) yield item.key;
      if (page.total === null || offset + page.items.length >= page.total || !page.items.length) return;
      offset += page.items.length;
    }
  }
}

module.exports = { PskitClient, PskitClientError };
