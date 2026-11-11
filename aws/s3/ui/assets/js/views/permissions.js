// The bucket's Permissions tab: overview, Block public access, Bucket policy, Object Ownership, ACL, CORS.

import { h } from "../core/dom.js";
import { api, errorText } from "../core/api.js";
import { reload } from "../core/router.js";
import { BPA_FLAGS, bucketAclGrants, corsFromXml, OWNERSHIP_TEXT } from "../core/s3.js";
import { container, emptyState } from "../components/container.js";
import { kvList } from "../components/kv-list.js";
import { table } from "../components/table.js";
import { button } from "../components/button.js";
import { alert } from "../components/alert.js";
import { copyButton } from "../components/copy-button.js";
import { confirmModal } from "../components/modal.js";
import { prettyJson } from "../components/json-editor.js";
import { flash } from "../components/toast.js";
import { onOff, editButton, editHref, accessBadge } from "./common.js";
import { refreshBuckets } from "./shell.js";

const BPA_SHORT = {
  BlockPublicAcls: "Block public access to buckets and objects granted through new access control lists (ACLs)",
  IgnorePublicAcls: "Block public access to buckets and objects granted through any access control lists (ACLs)",
  BlockPublicPolicy: "Block public access to buckets and objects granted through new public bucket or access point policies",
  RestrictPublicBuckets: "Block public and cross-account access to buckets and objects through any public bucket or access point policies",
};

const OWNERSHIP_DESC = {
  BucketOwnerEnforced: "ACLs are disabled. All objects in this bucket are owned by this account. Access to this bucket and its objects is specified using only policies.",
  BucketOwnerPreferred: "ACLs are enabled. Objects written with the bucket-owner-full-control canned ACL are owned by the bucket owner; others by the object writer.",
  ObjectWriter: "ACLs are enabled. The object writer remains the object owner.",
  "": "ACLs are enabled. The object writer remains the object owner.",
};

function preBlock(text) {
  return h("div", { class: "code-block" }, h("div", { class: "code-block__copy" }, copyButton(text, { title: "Copy" })), h("pre", {}, text));
}

export function renderPermissionsTab({ bucket, info, body }) {
  const b = info.publicBlock;
  const allOn = BPA_FLAGS.every((f) => b[f]);
  const enforced = info.ownership === "BucketOwnerEnforced";
  const cors = corsFromXml(info.configs.cors);
  const grants = bucketAclGrants(info.acl);

  const deletePolicy = button({
    label: "Delete",
    disabled: !info.policy,
    onClick: async () => {
      const ok = await confirmModal({
        title: "Delete bucket policy",
        message: "Deleting the bucket policy removes every permission and restriction it defines. This cannot be undone.",
        confirmLabel: "Delete",
        variant: "danger",
        typed: "delete",
      });
      if (!ok) return;
      try {
        await api("PutBucketSetting", { bucket, setting: "policy", value: "" });
        flash("success", "", { title: "Successfully deleted bucket policy" });
        refreshBuckets().catch(() => undefined);
        reload();
      } catch (e) {
        flash("error", errorText(e), { title: "Could not delete the bucket policy" });
      }
    },
  });

  const aclTbl = table({
    ariaLabel: "Access control list",
    rowKey: (r) => r.grantee,
    pageSize: 0,
    columns: [
      { id: "g", header: "Grantee", cell: (r) => h("div", {}, h("div", {}, r.grantee), r.sub ? h("div", { class: "muted small" }, r.sub) : null) },
      { id: "o", header: "Objects", cell: (r) => r.objects },
      { id: "a", header: "Bucket ACL", cell: (r) => r.acl },
    ],
    rows: [
      { grantee: "Bucket owner (your account)", sub: `Account ${info.account}`, objects: "List, Write", acl: "Read, Write" },
      { grantee: "Everyone (public access)", sub: "Group: http://acs.amazonaws.com/groups/global/AllUsers", objects: [grants.everyone.list ? "List" : "", grants.everyone.write ? "Write" : ""].filter(Boolean).join(", ") || "-", acl: "-" },
      { grantee: "Authenticated users group (anyone with an access key)", sub: "Group: http://acs.amazonaws.com/groups/global/AuthenticatedUsers", objects: grants.authenticated.list ? "List" : "-", acl: "-" },
    ],
  });

  body.replaceChildren(
    h(
      "div",
      { class: "stack" },
      container({ title: "Permissions overview" }, kvList([{ label: "Access", value: accessBadge(info.access) }], { columns: 1 })),
      container(
        {
          title: "Block public access (bucket settings)",
          description: "Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, or both. To ensure that public access to all your buckets and objects is blocked, turn on Block all public access.",
          actions: [editButton(editHref(bucket, "public-access"))],
        },
        h(
          "div",
          { class: "bpa-view" },
          h("div", { class: "bpa-view__row bpa-view__row--master" }, h("span", {}, "Block all public access"), onOff(allOn, "On", "Off")),
          BPA_FLAGS.map((f) => h("div", { class: "bpa-view__row" }, h("span", {}, BPA_SHORT[f]), onOff(b[f], "On", "Off"))),
        ),
      ),
      container(
        {
          title: "Bucket policy",
          description: "The bucket policy, written in JSON, provides access to the objects stored in the bucket. Bucket policies don't apply to objects owned by other accounts.",
          actions: [button({ label: "Edit", href: editHref(bucket, "policy") }), deletePolicy],
        },
        info.policy ? preBlock(prettyJson(info.policy)) : emptyState({ title: "No policy to display.", text: "Add a bucket policy to grant or deny access to this bucket and its objects." }),
      ),
      container(
        {
          title: "Object Ownership",
          description: "Control ownership of objects written to this bucket from other accounts and the use of access control lists (ACLs).",
          actions: [editButton(editHref(bucket, "ownership"))],
        },
        kvList([{ label: "Object Ownership", value: h("div", {}, h("div", { class: "strong" }, OWNERSHIP_TEXT[info.ownership] || info.ownership), h("div", { class: "muted small" }, OWNERSHIP_DESC[info.ownership] || "")) }], { columns: 1 }),
      ),
      container(
        {
          title: "Access control list (ACL)",
          description: "Grant basic read/write permissions to other accounts or to everyone.",
          actions: [enforced ? button({ label: "Edit", disabled: true, title: "ACLs are disabled for this bucket" }) : button({ label: "Edit", href: editHref(bucket, "acl") })],
        },
        enforced
          ? alert({ type: "info", title: "This bucket has the bucket owner enforced setting applied for Object Ownership" }, "When bucket owner enforced is applied, use bucket policies to control access. To use ACLs, edit Object Ownership and enable ACLs.")
          : aclTbl.el,
      ),
      container(
        {
          title: "Cross-origin resource sharing (CORS)",
          description: "The CORS configuration, written in JSON, defines a way for client web applications that are loaded in one domain to interact with resources in a different domain.",
          actions: [editButton(editHref(bucket, "cors"))],
        },
        cors.length ? preBlock(JSON.stringify(cors, null, 2)) : emptyState({ title: "No configurations to display" }),
      ),
    ),
  );
}
