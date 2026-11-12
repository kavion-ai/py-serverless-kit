// Bucket Edit pages: versioning, tags, object-lock, website, public-access, ownership, acl, cors.
// Each saves with PutBucketSetting and returns to the tab it came from.

import { h } from "../core/dom.js";
import { api, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import {

  bucketAclGrants,
  cannedFromGrants,
  corsFromXml,
  corsToXml,
  objectLockOf,
  objectLockXml,
  ownershipXml,
  publicAccessBlockXml,
  websiteFromXml,
  websiteToXml,
} from "../core/s3.js";
import { button, busy, link } from "../components/button.js";
import { container, loading, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { field, input, radioGroup, checkbox, select, fieldset } from "../components/field.js";
import { alert, errorSlot } from "../components/alert.js";
import { tagEditor } from "../components/tag-editor.js";
import { jsonEditor } from "../components/json-editor.js";
import { kvList } from "../components/kv-list.js";
import { confirmModal } from "../components/modal.js";
import { flash } from "../components/toast.js";
import { CORS_EXAMPLES } from "../examples/cors-examples.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, editHref, loadBucketInfo, showLoadError } from "./common.js";
import { bpaForm, ownershipForm } from "./forms.js";
import { websiteEndpoints } from "./properties.js";

const PAGES = {
  versioning: { title: "Edit Bucket Versioning", tab: "properties", build: versioningPage },
  tags: { title: "Edit bucket tags", tab: "properties", build: tagsPage },
  "object-lock": { title: "Edit Object Lock", tab: "properties", build: objectLockPage },
  website: { title: "Edit static website hosting", tab: "properties", build: websitePage },
  "public-access": { title: "Edit Block public access (bucket settings)", tab: "permissions", build: publicAccessPage },
  ownership: { title: "Edit Object Ownership", tab: "permissions", build: ownershipPage },
  acl: { title: "Edit access control list (ACL)", tab: "permissions", build: aclPage },
  cors: { title: "Edit cross-origin resource sharing (CORS)", tab: "permissions", build: corsPage },
};

const put = (bucket, setting, value) => api("PutBucketSetting", { bucket, setting, value });

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const page = PAGES[ctx.params.setting];
  if (!page) {
    navigate(bucketPath(bucket), {}, { replace: true });
    return;
  }
  const back = bucketHref(bucket, { tab: page.tab });
  const crumbs = bucketCrumbs(bucket, "", { label: page.tab === "properties" ? "Properties" : "Permissions", href: back }, { label: page.title });
  setPage({ crumbs, title: page.title, content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs);
    return;
  }
  if (!ctx.alive()) return;

  const errors = errorSlot();
  const spec = page.build({ bucket, info, query: ctx.query });
  const save = button({ label: "Save changes", variant: "primary", disabled: Boolean(spec.readOnly) });
  save.addEventListener("click", () =>
    busy(save, async () => {
      errors.set(null);
      try {
        const done = await spec.submit();
        if (done === false) return;
        refreshBuckets().catch(() => undefined);
        flash("success", "", { title: spec.success || `Successfully edited ${page.title.replace(/^Edit /, "")}` });
        navigate(bucketPath(bucket), { tab: page.tab });
      } catch (e) {
        errors.set(errorText(e));
      }
    }),
  );
  setPage({
    crumbs,
    title: page.title,
    content: h(
      "div",
      { class: "stack form-page" },
      pageHeader({ title: page.title, description: spec.description }),
      spec.content,
      errors,
      formActions(button({ label: "Cancel", variant: "link", href: back }), save),
    ),
  });
}

// ----------------------------------------------------------------------------- versioning

function versioningPage({ bucket, info }) {
  const value = info.versioning === "Enabled" ? "Enabled" : "Suspended";
  const warn = alert(
    { type: "warning", title: "Suspending versioning" },
    "When you suspend versioning, existing objects keep their versions, but new uploads and deletes no longer create versions (they overwrite the null version). To keep protecting your data, keep versioning enabled.",
  );
  const choice = radioGroup({
    ariaLabel: "Bucket Versioning",
    value,
    onChange: (v) => {
      warn.hidden = v !== "Suspended" || info.versioning !== "Enabled";
    },
    items: [
      { value: "Suspended", label: "Suspend", description: "This suspends the creation of object versions for all operations but preserves any existing object versions.", disabled: info.objectLock },
      { value: "Enabled", label: "Enable" },
    ],
  });
  warn.hidden = true;
  return {
    description: "Versioning is a means of keeping multiple variants of an object in the same bucket.",
    success: "Successfully edited Bucket Versioning",
    content: container(
      { title: "Bucket Versioning", description: "With versioning, you can recover from both unintended user actions and application failures." },
      info.objectLock ? alert({ type: "info" }, "Object Lock is enabled for this bucket, so Bucket Versioning cannot be suspended.") : null,
      !info.versioning ? alert({ type: "info" }, "Bucket Versioning has never been enabled for this bucket. Once enabled, it can be suspended but not turned off.") : null,
      choice,
      warn,
    ),
    async submit() {
      if (!info.versioning && choice.value === "Suspended") return undefined;
      await put(bucket, "versioning", choice.value);
      return undefined;
    },
  };
}

// ----------------------------------------------------------------------------- tags

function tagsPage({ bucket, info }) {
  const tags = tagEditor({ tags: info.tags, max: 50 });
  return {
    description: "You can use bucket tags to track storage cost or other criteria.",
    success: "Successfully edited bucket tags",
    content: container({ title: "Tags", description: "Up to 50 tags. Keys up to 128 characters, values up to 256." }, tags.el),
    async submit() {
      const problem = tags.validate();
      if (problem) throw new Error(problem);
      await put(bucket, "tags", tags.getValue());
    },
  };
}

// ----------------------------------------------------------------------------- object lock

function objectLockPage({ bucket, info }) {
  const lock = objectLockOf(info);
  if (!lock.enabled) {
    const canEnable = info.versioning === "Enabled";
    const ack = checkbox({ label: "I acknowledge that enabling Object Lock will permanently allow objects in this bucket to be locked." });
    const choice = radioGroup({
      ariaLabel: "Object Lock",
      value: "disabled",
      items: [
        { value: "disabled", label: "Disable" },
        { value: "enabled", label: "Enable", description: "Permanently allows objects in this bucket to be locked.", disabled: !canEnable },
      ],
    });
    return {
      description: "Store objects using a write-once-read-many (WORM) model.",
      success: "Successfully enabled Object Lock",
      content: container(
        { title: "Object Lock" },
        canEnable
          ? alert({ type: "warning", title: "Object Lock cannot be disabled" }, "Once Object Lock is enabled for a bucket, it cannot be disabled and Bucket Versioning cannot be suspended.")
          : alert({ type: "info", title: "Bucket Versioning is required" }, "Object Lock works only in versioned buckets. ", link("Enable Bucket Versioning", editHref(bucket, "versioning")), " first."),
        choice,
        canEnable ? ack : null,
      ),
      async submit() {
        if (choice.value !== "enabled") return undefined;
        if (!ack.input.checked) throw new Error("Acknowledge that enabling Object Lock is permanent.");
        await put(bucket, "object-lock", objectLockXml({}));
        return undefined;
      },
    };
  }
  const retention = radioGroup({
    ariaLabel: "Default retention",
    value: lock.mode ? "enabled" : "disabled",
    onChange: (v) => {
      details.hidden = v !== "enabled";
    },
    items: [
      { value: "disabled", label: "Disable" },
      { value: "enabled", label: "Enable", description: "New objects placed in this bucket get this retention automatically." },
    ],
  });
  const mode = radioGroup({
    ariaLabel: "Default retention mode",
    value: lock.mode || "GOVERNANCE",
    items: [
      { value: "GOVERNANCE", label: "Governance", description: "Users with the bypass permission can overwrite or delete protected object versions during the retention period." },
      { value: "COMPLIANCE", label: "Compliance", description: "No user can overwrite or delete protected object versions during the retention period." },
    ],
  });
  const amount = input({ type: "number", min: "1", step: "1", value: String(lock.years || lock.days || 30), "aria-label": "Default retention period" });
  const unit = select({ options: ["Days", "Years"], value: lock.years ? "Years" : "Days", ariaLabel: "Unit" });
  const details = h(
    "div",
    { class: "stack indent", hidden: !lock.mode },
    fieldset({ legend: "Default retention mode" }, mode),
    field({ label: "Default retention period", control: h("div", { class: "field-row" }, h("div", { class: "grow" }, amount), unit) }),
  );
  return {
    description: "Store objects using a write-once-read-many (WORM) model to help you prevent objects from being deleted or overwritten.",
    success: "Successfully edited Object Lock",
    content: container(
      { title: "Object Lock", description: "Object Lock is enabled for this bucket and cannot be disabled." },
      kvList([{ label: "Object Lock", value: "Enabled" }], { columns: 1 }),
      fieldset({ legend: "Default retention", description: "Automatically protect new objects put into this bucket from being deleted or overwritten." }, retention),
      details,
    ),
    async submit() {
      if (retention.value !== "enabled") {
        await put(bucket, "object-lock", objectLockXml({}));
        return;
      }
      const n = Number(amount.value);
      if (!Number.isInteger(n) || n < 1) throw new Error("Enter a whole number of days or years (1 or more).");
      await put(bucket, "object-lock", objectLockXml({ mode: mode.value, days: unit.value === "Days" ? n : null, years: unit.value === "Years" ? n : null }));
    },
  };
}

// ----------------------------------------------------------------------------- website

function websitePage({ bucket, info }) {
  const site = websiteFromXml(info.configs.website);
  const index = input({ value: site.index || "index.html" });
  const indexField = field({ label: "Index document", control: index, description: "Specify the home or default page of the website.", constraint: "For example index.html. It is also served for every folder (key ending with /)." });
  const error = input({ value: site.error, placeholder: "error.html" });
  const rules = jsonEditor({
    value: site.routingRules.length ? JSON.stringify(site.routingRules, null, 2) : "",
    rows: 10,
    allowEmpty: true,
    ariaLabel: "Redirection rules",
    validate: (v) => (Array.isArray(v) ? "" : "Redirection rules must be a JSON array."),
  });
  const host = input({ value: site.host, placeholder: "www.example.com" });
  const protocol = radioGroup({
    ariaLabel: "Protocol",
    value: site.protocol || "",
    items: [
      { value: "", label: "none" },
      { value: "http", label: "http" },
      { value: "https", label: "https" },
    ],
  });
  const hosting = h(
    "div",
    { class: "stack" },
    indexField,
    field({ label: "Error document", optional: true, control: error, description: "This is returned when an error occurs." }),
    field({
      label: "Redirection rules",
      optional: true,
      control: rules.el,
      description: "Redirection rules, written in JSON, automatically redirect webpage requests for specific content.",
      constraint: 'Example: [{"Condition": {"KeyPrefixEquals": "docs/"}, "Redirect": {"ReplaceKeyPrefixWith": "documents/"}}]',
    }),
  );
  const redirect = h(
    "div",
    { class: "stack" },
    field({ label: "Host name", control: host, description: "Every request to the website endpoint is redirected to this host." }),
    fieldset({ legend: "Protocol - optional" }, protocol),
  );
  const type = radioGroup({
    ariaLabel: "Hosting type",
    value: site.mode,
    onChange: (v) => {
      hosting.hidden = v !== "website";
      redirect.hidden = v !== "redirect";
    },
    items: [
      { value: "website", label: "Host a static website", description: "Use the bucket endpoint as the web address." },
      { value: "redirect", label: "Redirect requests for an object", description: "Redirect requests to another bucket or domain." },
    ],
  });
  hosting.hidden = site.mode !== "website";
  redirect.hidden = site.mode !== "redirect";
  const { main, hosts } = websiteEndpoints(info);
  const publicNote = alert(
    { type: "info", title: "Make your objects public" },
    "For your customers to access content at the website endpoint, you must make all your content publicly readable: turn off Block public access for bucket policies and add a bucket policy that grants public read access. ",
    h("div", { class: "btn-row" }, button({ label: "Add a public-read bucket policy", href: editHref(bucket, "policy", { example: "public-read" }) }), button({ label: "Edit Block public access", href: editHref(bucket, "public-access") })),
  );
  const options = h(
    "div",
    { class: "stack" },
    fieldset({ legend: "Hosting type" }, type),
    hosting,
    redirect,
    publicNote,
    kvList([{ label: "Bucket website endpoint", value: h("div", { class: "stack-xs" }, h("div", { class: "mono" }, main), hosts.map((u) => h("div", { class: "mono small" }, u))) }], { columns: 1 }),
  );
  const enabled = radioGroup({
    ariaLabel: "Static website hosting",
    value: site.enabled ? "enabled" : "disabled",
    onChange: (v) => {
      options.hidden = v !== "enabled";
    },
    items: [
      { value: "disabled", label: "Disable" },
      { value: "enabled", label: "Enable" },
    ],
  });
  options.hidden = !site.enabled;
  return {
    description: "Use this bucket to host a website or redirect requests.",
    success: "Successfully edited static website hosting",
    content: container({ title: "Static website hosting" }, h("div", { class: "stack" }, enabled, options)),
    async submit() {
      if (enabled.value !== "enabled") {
        if (site.enabled) await put(bucket, "website", "");
        return;
      }
      if (type.value === "website") {
        indexField.setError(index.value.trim() ? "" : "Enter an index document.");
        if (!rules.isValid()) throw new Error("The redirection rules are not valid JSON.");
      }
      const xml = websiteToXml({
        mode: type.value,
        index: index.value.trim(),
        error: error.value.trim(),
        routingRules: rules.getValue().trim() ? JSON.parse(rules.getValue()) : [],
        host: host.value.trim(),
        protocol: protocol.value,
      });
      await put(bucket, "website", xml);
    },
  };
}

// ----------------------------------------------------------------------------- block public access

function publicAccessPage({ bucket, info }) {
  const form = bpaForm(info.publicBlock);
  return {
    description: "Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, or both.",
    success: "Successfully edited Block Public Access settings for this bucket",
    content: container(
      { title: "Block public access (bucket settings)", description: "To ensure that public access to this bucket and its objects is blocked, turn on Block all public access. These settings apply only to this bucket." },
      form.el,
    ),
    async submit() {
      const problem = form.validate();
      if (problem) throw new Error(problem);
      const ok = await confirmModal({
        title: "Edit Block public access (bucket settings)?",
        message: "Updating the Block Public Access settings for this bucket affects this bucket and all objects within. This may result in some objects becoming public.",
        confirmLabel: "Confirm",
        typed: "confirm",
      });
      if (!ok) return false;
      await put(bucket, "publicAccessBlock", publicAccessBlockXml(form.value()));
      return undefined;
    },
  };
}

// ----------------------------------------------------------------------------- ownership

function ownershipPage({ bucket, info }) {
  const form = ownershipForm(info.ownership || "ObjectWriter");
  const aclWarn = info.acl && info.acl !== "private" && info.acl !== "bucket-owner-full-control";
  return {
    description: "Control ownership of objects written to this bucket from other accounts and the use of access control lists (ACLs).",
    success: "Successfully edited Object Ownership",
    content: container(
      { title: "Object Ownership" },
      aclWarn ? alert({ type: "warning", title: "The bucket ACL grants access" }, `The bucket ACL is ${info.acl}. Disabling ACLs makes the server ignore it; grant the same access with a bucket policy first.`) : null,
      form.el,
    ),
    async submit() {
      await put(bucket, "ownershipControls", ownershipXml(form.value()));
    },
  };
}

// ----------------------------------------------------------------------------- ACL

function aclPage({ bucket, info }) {
  if (info.ownership === "BucketOwnerEnforced") {
    return {
      readOnly: true,
      content: alert(
        { type: "info", title: "ACLs are disabled" },
        "This bucket has the bucket owner enforced setting applied for Object Ownership. ",
        link("Edit Object Ownership", editHref(bucket, "ownership")),
        " to enable ACLs.",
      ),
      async submit() {},
    };
  }
  const g = bucketAclGrants(info.acl);
  const box = (checked, label, disabled) => {
    const el = h("input", { type: "checkbox", checked, disabled: Boolean(disabled), "aria-label": label });
    return el;
  };
  const ev = { list: box(g.everyone.list, "Everyone: Objects List"), write: box(g.everyone.write, "Everyone: Objects Write") };
  const au = { list: box(g.authenticated.list, "Authenticated users: Objects List") };
  const ack = checkbox({ label: "I understand the effects of these changes on my objects and buckets." });
  const warn = alert({ type: "warning", title: "Granting public access" }, "Everyone (public access) will be able to list this bucket's objects without keys" , ", and with Write, upload and delete objects.", h("div", { class: "alert__ack" }, ack));
  const blocked = info.publicBlock.BlockPublicAcls;
  const sync = () => {
    if (ev.write.checked) ev.list.checked = true;
    au.list.disabled = ev.list.checked;
    if (ev.list.checked) au.list.checked = false;
    warn.hidden = !ev.list.checked;
  };
  [ev.list, ev.write, au.list].forEach((el) => el.addEventListener("change", sync));
  sync();
  const otherCanned = !["private", "public-read", "public-read-write", "authenticated-read"].includes(info.acl);
  const tableEl = h(
    "table",
    { class: "tbl tbl--grid" },
    h("thead", {}, h("tr", {}, h("th", {}, "Grantee"), h("th", {}, "Objects"), h("th", {}, "Bucket ACL"))),
    h(
      "tbody",
      {},
      h("tr", {}, h("td", {}, "Bucket owner (your account)", h("div", { class: "muted small" }, `Account ${info.account}`)), h("td", {}, h("label", { class: "check-inline" }, box(true, "", true), "List"), h("label", { class: "check-inline" }, box(true, "", true), "Write")), h("td", {}, h("label", { class: "check-inline" }, box(true, "", true), "Read"), h("label", { class: "check-inline" }, box(true, "", true), "Write"))),
      h("tr", {}, h("td", {}, "Everyone (public access)", h("div", { class: "muted small" }, "Group: http://acs.amazonaws.com/groups/global/AllUsers")), h("td", {}, h("label", { class: "check-inline" }, ev.list, "List"), h("label", { class: "check-inline" }, ev.write, "Write")), h("td", {}, "-")),
      h("tr", {}, h("td", {}, "Authenticated users group (anyone with an access key)", h("div", { class: "muted small" }, "Group: http://acs.amazonaws.com/groups/global/AuthenticatedUsers")), h("td", {}, h("label", { class: "check-inline" }, au.list, "List")), h("td", {}, "-")),
    ),
  );
  return {
    description: "Grant basic read/write permissions to other accounts or to everyone. The choices map to canned ACLs (private, public-read, public-read-write, authenticated-read).",
    success: "Successfully edited the bucket ACL",
    content: container(
      { title: "Access control list (ACL)" },
      blocked ? alert({ type: "warning" }, "Block public access (BlockPublicAcls) is on for this bucket: public ACLs are refused. ", link("Edit Block public access", editHref(bucket, "public-access"))) : null,
      otherCanned ? alert({ type: "info" }, `The current canned ACL is ${info.acl}. Saving replaces it.`) : null,
      h("div", { class: "tbl__scroll" }, tableEl),
      warn,
    ),
    async submit() {
      if (ev.list.checked && !ack.input.checked) throw new Error("Acknowledge the effects of granting public access.");
      const canned = cannedFromGrants({ everyone: { list: ev.list.checked, write: ev.write.checked }, authenticated: { list: au.list.checked, write: false } });
      await put(bucket, "acl", canned);
    },
  };
}

// ----------------------------------------------------------------------------- CORS

function corsPage({ bucket, info }) {
  const current = corsFromXml(info.configs.cors);
  const editor = jsonEditor({
    value: current.length ? JSON.stringify(current, null, 2) : "",
    rows: 18,
    allowEmpty: true,
    ariaLabel: "CORS configuration",
    validate: (v) => {
      try {
        corsToXml(v);
        return "";
      } catch (e) {
        return e.message;
      }
    },
  });
  const examples = h(
    "div",
    { class: "examples" },
    CORS_EXAMPLES.map((ex) =>
      h(
        "div",
        { class: "examples__item" },
        h("div", { class: "examples__text" }, h("div", { class: "strong" }, ex.title), h("div", { class: "muted small" }, ex.description)),
        button({ label: "Use", onClick: () => editor.setValue(JSON.stringify(ex.rules, null, 2)) }),
      ),
    ),
  );
  return {
    description: "The CORS configuration, written in JSON, defines a way for client web applications that are loaded in one domain to interact with resources in a different domain.",
    success: "Successfully edited the CORS configuration",
    content: h(
      "div",
      { class: "editor-layout" },
      container({ title: "Cross-origin resource sharing (CORS)", description: "Leave the editor empty (or use []) to delete the configuration." }, editor.el),
      container({ title: "CORS examples", description: "Choose an example to replace the editor's content." }, examples),
    ),
    async submit() {
      if (!editor.isValid()) throw new Error("Fix the CORS configuration first.");
      const text = editor.getValue().trim();
      const xml = text ? corsToXml(JSON.parse(text)) : "";
      if (!xml && !current.length) return undefined;
      await put(bucket, "cors", xml);
      return undefined;
    },
  };
}

