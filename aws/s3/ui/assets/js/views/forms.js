// Form sections used both by Create bucket and by the bucket's Edit pages.

import { h } from "../core/dom.js";
import { BPA_FLAGS } from "../core/s3.js";
import { checkbox, radioGroup, fieldset } from "../components/field.js";
import { alert } from "../components/alert.js";

const BPA_TEXT = {
  BlockPublicAcls: [
    ["Block public access to buckets and objects granted through ", h("em", {}, "new"), " access control lists (ACLs)"],
    "S3 will block public access permissions applied to newly added buckets or objects, and prevent the creation of new public access ACLs for existing buckets and objects. This setting doesn't change any existing permissions that allow public access to S3 resources using ACLs.",
  ],
  IgnorePublicAcls: [
    ["Block public access to buckets and objects granted through ", h("em", {}, "any"), " access control lists (ACLs)"],
    "S3 will ignore all ACLs that grant public access to buckets and objects.",
  ],
  BlockPublicPolicy: [
    ["Block public access to buckets and objects granted through ", h("em", {}, "new"), " public bucket or access point policies"],
    "S3 will block new bucket and access point policies that grant public access to buckets and objects. This setting doesn't change any existing policies that allow public access to S3 resources.",
  ],
  RestrictPublicBuckets: [
    ["Block public and cross-account access to buckets and objects through ", h("em", {}, "any"), " public bucket or access point policies"],
    "S3 will ignore public and cross-account access for buckets or access points with policies that grant public access to buckets and objects.",
  ],
};

/** The "Block all public access" master checkbox, its four options and the acknowledgement when any is off. */
export function bpaForm(initial) {
  const subs = {};
  const ack = checkbox({ label: "I acknowledge that the current settings might result in this bucket and the objects within becoming public." });
  const warning = alert(
    { type: "warning", title: "Turning off block all public access might result in this bucket and the objects within becoming public" },
    "We recommend that you turn on block all public access, unless public access is required for specific and verified use cases such as static website hosting.",
    h("div", { class: "alert__ack" }, ack),
  );
  const sync = () => {
    const all = BPA_FLAGS.every((f) => subs[f].input.checked);
    master.input.checked = all;
    master.input.indeterminate = !all && BPA_FLAGS.some((f) => subs[f].input.checked);
    warning.hidden = all;
  };
  const master = checkbox({
    label: ["Block ", h("em", {}, "all"), " public access"],
    description: "Turning this setting on is the same as turning on all four settings below. Each of the following settings are independent of one another.",
    className: "check--master",
    checked: BPA_FLAGS.every((f) => initial[f]),
    onChange: (on) => {
      BPA_FLAGS.forEach((f) => {
        subs[f].input.checked = on;
      });
      sync();
    },
  });
  for (const f of BPA_FLAGS) {
    subs[f] = checkbox({ label: BPA_TEXT[f][0], description: BPA_TEXT[f][1], checked: Boolean(initial[f]), onChange: sync, className: "check--sub" });
  }
  const el = h("div", { class: "bpa" }, master, h("div", { class: "bpa__subs" }, BPA_FLAGS.map((f) => subs[f])), warning);
  sync();
  return {
    el,
    value: () => Object.fromEntries(BPA_FLAGS.map((f) => [f, subs[f].input.checked])),
    validate: () => (warning.hidden || ack.input.checked ? "" : "Acknowledge that the bucket and its objects might become public, or block all public access."),
  };
}

/** Object Ownership: ACLs disabled (BucketOwnerEnforced) or enabled (BucketOwnerPreferred / ObjectWriter). */
export function ownershipForm(initial) {
  const enabled = initial !== "BucketOwnerEnforced";
  const sub = radioGroup({
    ariaLabel: "Object Ownership",
    value: initial === "BucketOwnerPreferred" ? "BucketOwnerPreferred" : "ObjectWriter",
    items: [
      { value: "BucketOwnerPreferred", label: "Bucket owner preferred", description: "If new objects written to this bucket specify the bucket-owner-full-control canned ACL, they are owned by the bucket owner. Otherwise, they are owned by the object writer." },
      { value: "ObjectWriter", label: "Object writer", description: "The object writer remains the object owner." },
    ],
  });
  const aclInfo = alert(
    { type: "info", title: "We recommend disabling ACLs" },
    "Disable ACLs unless you need to control access for each object individually or to have the object writer own the data they upload. Using a bucket policy instead of ACLs to share data simplifies permissions management and auditing.",
  );
  const details = h("div", { class: "stack-sm", hidden: !enabled }, aclInfo, fieldset({ legend: "Object Ownership" }, sub));
  const main = radioGroup({
    tiles: true,
    ariaLabel: "ACLs",
    value: enabled ? "enabled" : "disabled",
    onChange: (v) => {
      details.hidden = v !== "enabled";
    },
    items: [
      { value: "disabled", label: "ACLs disabled (recommended)", description: "All objects in this bucket are owned by this account. Access to this bucket and its objects is specified using only policies." },
      { value: "enabled", label: "ACLs enabled", description: "Objects in this bucket can be owned by other accounts. Access to this bucket and its objects can be specified using ACLs." },
    ],
  });
  return {
    el: h("div", { class: "stack-sm" }, main, details),
    value: () => (main.value === "disabled" ? "BucketOwnerEnforced" : sub.value),
  };
}
