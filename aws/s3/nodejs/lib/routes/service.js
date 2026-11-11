"use strict";
// The service: ListBuckets.

const { cmpStr, pyInt } = require("../py");
const { denied } = require("../errors");
const { REGION } = require("../config");
const { iso, ownerXml, x } = require("../util");
const { getStore } = require("../store");
const { tokenDecode, tokenEncode } = require("../versions");
const { xmlResponse } = require("../http");

function listBuckets(req) {
  if (req.who === null) throw denied();
  const prefix = req.q.prefix || "";
  const region = req.q["bucket-region"] || "";
  const limit = pyInt(req.q["max-buckets"] || "10000");
  const after = req.q["continuation-token"] ? tokenDecode(req.q["continuation-token"]) : "";
  const names = [...getStore().buckets.keys()].sort(cmpStr).filter((n) => n.startsWith(prefix) && cmpStr(n, after) > 0 &&
    (!region || getStore().buckets.get(n).meta.region === region));
  const page = names.slice(0, Math.max(0, limit < 0 ? names.length + limit : limit));
  const more = names.length > limit;
  const items = page.map((n) => {
    const meta = getStore().buckets.get(n).meta;
    return `<Bucket>${x("Name", n)}${x("CreationDate", iso(meta.created))}${x("BucketRegion", meta.region || REGION)}</Bucket>`;
  }).join("");
  let inner = `${ownerXml()}<Buckets>${items}</Buckets>`;
  if (more) inner += x("ContinuationToken", tokenEncode(page[page.length - 1]));
  if (prefix) inner += x("Prefix", prefix);
  return xmlResponse("ListAllMyBucketsResult", inner);
}

module.exports = { listBuckets };
