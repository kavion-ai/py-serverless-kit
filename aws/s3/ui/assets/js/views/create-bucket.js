// Create bucket: a full-page form like the AWS console. CreateBucket, then PutBucketSetting for ownership controls,
// block public access and tags.

import { h, mount } from "../core/dom.js";
import { state } from "../core/state.js";
import { api, errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { ownershipXml, publicAccessBlockXml, BPA_FLAGS } from "../core/s3.js";
import { button, busy } from "../components/button.js";
import { container, expandable, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { field, input, radioGroup, select, checkbox } from "../components/field.js";
import { alert, errorSlot } from "../components/alert.js";
import { tagEditor } from "../components/tag-editor.js";
import { flash } from "../components/toast.js";
import { setPage, refreshBuckets } from "./shell.js";
import { bucketHref, loadBucketInfo, rootCrumbs } from "./common.js";
import { bpaForm, ownershipForm } from "./forms.js";

/** Problems with a bucket name (empty list when valid). */
export function bucketNameProblems(name) {
  const out = [];
  if (name.length < 3 || name.length > 63) out.push("Bucket name must be between 3 and 63 characters long.");
  if (/[^a-z0-9.-]/.test(name)) out.push("Bucket name can contain only lowercase letters, numbers, periods (.) and hyphens (-).");
  if (name && !/^[a-z0-9].*[a-z0-9]$|^[a-z0-9]$/.test(name)) out.push("Bucket name must begin and end with a letter or number.");
  if (name.includes("..")) out.push("Bucket name must not contain two adjacent periods.");
  if (/^\d+\.\d+\.\d+\.\d+$/.test(name)) out.push("Bucket name must not be formatted as an IP address.");
  if (/^(xn--|sthree-|amzn-s3-demo-)/.test(name)) out.push("Bucket name must not start with xn--, sthree- or amzn-s3-demo-.");
  if (/(-s3alias|--ol-s3|\.mrap|--x-s3)$/.test(name)) out.push("Bucket name must not end with -s3alias, --ol-s3, .mrap or --x-s3.");
  if (state.buckets && state.buckets.some((b) => b.name === name)) out.push("A bucket with the same name already exists.");
  return out;
}

const DEFAULTS = {
  ownership: "BucketOwnerEnforced",
  publicBlock: Object.fromEntries(BPA_FLAGS.map((f) => [f, true])),
  versioning: "disabled",
  tags: {},
  objectLock: false,
};

export async function render(ctx) {
  if (!state.buckets) await refreshBuckets().catch(() => undefined);
  if (!ctx.alive()) return;
  const errors = errorSlot();
  const nameInput = input({ placeholder: "my-bucket-name", "aria-required": "true" });
  const nameField = field({
    label: "Bucket name",
    control: nameInput,
    constraint: "Bucket names must be 3 to 63 characters and unique on this server. Valid characters are a-z, 0-9, periods (.), and hyphens (-). Names must begin and end with a letter or number.",
  });
  let touched = false;
  const checkName = () => {
    const problems = bucketNameProblems(nameInput.value.trim());
    nameField.setError(touched && problems.length ? problems[0] : "");
    return problems;
  };
  nameInput.addEventListener("input", checkName);
  nameInput.addEventListener("blur", () => {
    if (nameInput.value) touched = true;
    checkName();
  });

  const copySlot = h("div", { class: "copy-from__status" });
  const copySelect = select({
    ariaLabel: "Copy settings from an existing bucket",
    options: [{ value: "", label: "Choose bucket" }, ...(state.buckets || []).map((b) => ({ value: b.name, label: b.name }))],
    value: "",
    onChange: async (name) => {
      if (!name) return;
      mount(copySlot, h("span", { class: "muted" }, "Copying settings"));
      try {
        const info = await loadBucketInfo(name);
        sections = buildSections({
          ownership: info.ownership || "ObjectWriter",
          publicBlock: info.publicBlock,
          versioning: info.versioning === "Enabled" ? "enabled" : "disabled",
          tags: info.tags,
          objectLock: info.objectLock,
        });
        mount(sectionsSlot, sections.el);
        mount(copySlot, alert({ type: "success" }, `Settings copied from ${name}. Bucket policy, website, CORS and lifecycle settings are not copied.`));
      } catch (e) {
        mount(copySlot, alert({ type: "error" }, errorText(e)));
      }
    },
  });

  let sections = buildSections(DEFAULTS);
  const sectionsSlot = h("div", { class: "stack" }, sections.el);
  const createBtn = button({ label: "Create bucket", variant: "primary" });
  createBtn.addEventListener("click", () => busy(createBtn, submit));

  setPage({
    crumbs: [...rootCrumbs(), { label: "Create bucket" }],
    title: "Create bucket",
    content: h(
      "div",
      { class: "stack form-page" },
      pageHeader({ title: "Create bucket", description: "Buckets are containers for data stored in S3." }),
      container(
        { title: "General configuration" },
        h(
          "div",
          { class: "stack" },
          field({ label: "AWS Region", control: input({ value: state.session.region, readonly: true, disabled: true }), description: "The region of this server." }),
          h("div", { class: "field-row" }, h("div", { class: "grow" }, nameField)),
          field({ label: "Copy settings from existing bucket", optional: true, description: "Only the bucket settings in the following configuration are copied.", control: copySelect }),
          copySlot,
        ),
      ),
      sectionsSlot,
      alert({ type: "info" }, "After creating the bucket, you can upload files and folders to the bucket, and configure additional bucket settings."),
      errors,
      formActions(button({ label: "Cancel", variant: "link", href: "#/buckets" }), createBtn),
    ),
  });
  nameInput.focus();

  async function submit() {
    errors.set(null);
    touched = true;
    const name = nameInput.value.trim();
    const problems = checkName();
    if (problems.length) {
      nameInput.focus();
      return;
    }
    const problem = sections.validate();
    if (problem) {
      errors.set(problem);
      return;
    }
    const v = sections.value();
    try {
      await api("CreateBucket", { bucket: name, region: state.session.region, versioning: v.versioning, objectLock: v.objectLock });
    } catch (e) {
      errors.set(errorText(e), "Failed to create bucket");
      return;
    }
    const followUps = [
      ["ownershipControls", ownershipXml(v.ownership), "Object Ownership"],
      ["publicAccessBlock", publicAccessBlockXml(v.publicBlock), "Block Public Access"],
    ];
    if (Object.keys(v.tags).length) followUps.push(["tags", v.tags, "Tags"]);
    const failed = [];
    for (const [setting, value, label] of followUps) {
      try {
        await api("PutBucketSetting", { bucket: name, setting, value });
      } catch (e) {
        failed.push(`${label}: ${errorText(e)}`);
      }
    }
    await refreshBuckets().catch(() => undefined);
    if (failed.length) {
      flash("warning", h("div", {}, `The bucket "${name}" was created, but some settings could not be applied: `, failed.join("; ")), { title: "Bucket created with errors" });
      navigate(`/buckets/${encodeURIComponent(name)}`, { tab: "properties" });
      return;
    }
    flash(
      "success",
      h("span", {}, "To upload files and folders, or to configure additional bucket settings, choose ", h("a", { href: bucketHref(name) }, "View details"), "."),
      { title: `Successfully created bucket "${name}"` },
    );
    navigate("/buckets");
  }
}

function buildSections(initial) {
  const ownership = ownershipForm(initial.ownership);
  const bpa = bpaForm(initial.publicBlock);
  const versioning = radioGroup({
    ariaLabel: "Bucket Versioning",
    value: initial.versioning,
    items: [
      { value: "disabled", label: "Disable" },
      { value: "enabled", label: "Enable" },
    ],
  });
  const tags = tagEditor({ tags: initial.tags, max: 50 });
  const lockAck = checkbox({ label: "I acknowledge that enabling Object Lock will permanently allow objects in this bucket to be locked." });
  const lockDetails = h(
    "div",
    { class: "stack-sm", hidden: !initial.objectLock },
    alert({ type: "info" }, "Enabling Object Lock permanently allows objects in this bucket to be locked. Additional Object Lock configuration is required in bucket details after bucket creation to protect objects in this bucket from being deleted or overwritten."),
    lockAck,
  );
  const versioningNote = h("div", { class: "field__constraint", hidden: !initial.objectLock }, "Object Lock works only in versioned buckets. Enabling Object Lock automatically enables Bucket Versioning.");
  const lock = radioGroup({
    ariaLabel: "Object Lock",
    value: initial.objectLock ? "enabled" : "disabled",
    onChange: (v) => {
      lockDetails.hidden = v !== "enabled";
      versioningNote.hidden = v !== "enabled";
      if (v === "enabled") versioning.setValue("enabled");
    },
    items: [
      { value: "disabled", label: "Disable" },
      { value: "enabled", label: "Enable", description: "Permanently allows objects in this bucket to be locked." },
    ],
  });
  if (initial.objectLock) lockAck.input.checked = true;

  const el = h(
    "div",
    { class: "stack" },
    container(
      { title: "Object Ownership", description: "Control ownership of objects written to this bucket from other accounts and the use of access control lists (ACLs). Object ownership determines who can specify access to objects." },
      ownership.el,
    ),
    container(
      { title: "Block Public Access settings for this bucket", description: "Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, or both. To ensure that public access to this bucket and its objects is blocked, turn on Block all public access. These settings apply only to this bucket." },
      bpa.el,
    ),
    container(
      { title: "Bucket Versioning", description: "Versioning is a means of keeping multiple variants of an object in the same bucket. You can use versioning to preserve, retrieve, and restore every version of every object stored in your bucket. With versioning, you can recover from both unintended user actions and application failures." },
      versioning,
      versioningNote,
    ),
    container({ title: "Tags - optional", counter: undefined, description: "You can use bucket tags to track storage cost or other criteria. Up to 50 tags." }, tags.el),
    container(
      { title: "Advanced settings" },
      expandable(
        { title: "Object Lock", description: "Store objects using a write-once-read-many (WORM) model to help you prevent objects from being deleted or overwritten for a fixed amount of time or indefinitely. Object Lock works only in versioned buckets.", open: initial.objectLock },
        lock,
        lockDetails,
      ),
    ),
  );
  return {
    el,
    validate() {
      const problem = bpa.validate() || tags.validate();
      if (problem) return problem;
      if (lock.value === "enabled" && !lockAck.input.checked) return "Acknowledge that enabling Object Lock permanently allows objects in this bucket to be locked.";
      return "";
    },
    value: () => ({
      ownership: ownership.value(),
      publicBlock: bpa.value(),
      versioning: versioning.value === "enabled" || lock.value === "enabled",
      tags: tags.getValue(),
      objectLock: lock.value === "enabled",
    }),
  };
}
