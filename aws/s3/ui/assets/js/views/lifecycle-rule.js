// Create / edit lifecycle rule: name, status, scope (all objects or prefix / tags / size filters), actions, review.
// Saved as the whole LifecycleConfiguration XML.

import { h, mount } from "../core/dom.js";
import { errorText } from "../core/api.js";
import { navigate } from "../core/router.js";
import { storageClassLabel } from "../core/format.js";
import { emptyRule, lifecycleFromXml, TRANSITION_CLASSES } from "../core/s3.js";
import { button, busy } from "../components/button.js";
import { container, loading, formActions } from "../components/container.js";
import { pageHeader } from "../components/page-header.js";
import { field, input, radioGroup, checkbox, select, fieldset } from "../components/field.js";
import { alert, errorSlot } from "../components/alert.js";
import { tagEditor } from "../components/tag-editor.js";
import { flash } from "../components/toast.js";
import { setPage } from "./shell.js";
import { bucketCrumbs, bucketHref, bucketPath, loadBucketInfo, showLoadError } from "./common.js";
import { saveLifecycle } from "./management.js";

const SIZE_UNITS = [
  { value: "1", label: "Bytes" },
  { value: "1024", label: "KB" },
  { value: "1048576", label: "MB" },
  { value: "1073741824", label: "GB" },
];

function sizeControl(label, bytes) {
  const on = checkbox({ label, checked: bytes !== null && bytes !== undefined });
  let unit = "1";
  let amount = bytes;
  if (bytes) {
    for (const u of [...SIZE_UNITS].reverse()) {
      if (bytes % Number(u.value) === 0) {
        unit = u.value;
        amount = bytes / Number(u.value);
        break;
      }
    }
  }
  const num = input({ type: "number", min: "0", step: "1", value: amount === null || amount === undefined ? "" : String(amount), "aria-label": label });
  const unitSel = select({ options: SIZE_UNITS, value: unit, ariaLabel: "Unit" });
  const row = h("div", { class: "field-row indent", hidden: !on.input.checked }, h("div", { class: "grow" }, num), unitSel);
  on.input.addEventListener("change", () => {
    row.hidden = !on.input.checked;
  });
  return {
    el: h("div", {}, on, row),
    value() {
      if (!on.input.checked) return null;
      const n = Number(num.value);
      if (num.value === "" || !Number.isInteger(n) || n < 0) throw new Error(`${label}: enter a whole number.`);
      return n * Number(unitSel.value);
    },
  };
}

function daysInput(value, label) {
  return input({ type: "number", min: "1", step: "1", value: value ? String(value) : "", "aria-label": label, placeholder: "Days" });
}

function positive(el, label, optional) {
  if (optional && el.value === "") return null;
  const n = Number(el.value);
  if (el.value === "" || !Number.isInteger(n) || n < 1) throw new Error(`${label}: enter a whole number of days (1 or more).`);
  return n;
}

/** Transition rows (current or noncurrent versions). */
function transitionList(initial, noncurrent) {
  const rows = h("div", { class: "transition-list" });
  const add = (t = {}) => {
    const cls = select({ options: TRANSITION_CLASSES.map((c) => ({ value: c, label: storageClassLabel(c) })), value: t.storageClass || TRANSITION_CLASSES[0], ariaLabel: "Storage class" });
    const days = daysInput(t.days, noncurrent ? "Days after objects become noncurrent" : "Days after object creation");
    const newer = noncurrent ? input({ type: "number", min: "1", step: "1", value: t.newer ? String(t.newer) : "", "aria-label": "Number of newer versions to retain", placeholder: "Optional" }) : null;
    const row = h(
      "div",
      { class: "transition-row" },
      field({ label: "Choose storage class transitions", control: cls }),
      t.date && !noncurrent
        ? field({ label: "Date", control: input({ value: t.date.slice(0, 10), disabled: true }), description: "Set with the API; kept as is." })
        : field({ label: noncurrent ? "Days after objects become noncurrent" : "Days after object creation", control: days }),
      noncurrent ? field({ label: "Number of newer versions to retain", optional: true, control: newer }) : null,
      h("div", { class: "transition-row__remove" }, button({ label: "Remove", onClick: () => row.remove() })),
    );
    row.read = () => {
      const label = `Transition to ${storageClassLabel(cls.value)}`;
      if (t.date && !noncurrent) return { date: t.date, days: null, storageClass: cls.value };
      const out = { days: positive(days, label), storageClass: cls.value };
      if (noncurrent) out.newer = positive(newer, `${label}: newer versions`, true);
      return out;
    };
    rows.append(row);
  };
  initial.forEach(add);
  if (!initial.length) add();
  return {
    el: h("div", { class: "stack-sm" }, rows, h("div", {}, button({ label: "Add transition", onClick: () => add() }))),
    value: () => Array.from(rows.children).map((r) => r.read()),
  };
}

export async function render(ctx) {
  const bucket = ctx.params.bucket;
  const editing = ctx.path.endsWith("/edit");
  const title = editing ? "Edit lifecycle rule" : "Create lifecycle rule";
  const crumbs = bucketCrumbs(bucket, "", { label: "Lifecycle configuration", href: bucketHref(bucket, { tab: "management" }) }, { label: title });
  setPage({ crumbs, title, content: loading() });
  let info;
  try {
    info = await loadBucketInfo(bucket);
  } catch (e) {
    if (ctx.alive()) showLoadError(e, crumbs);
    return;
  }
  if (!ctx.alive()) return;
  const rules = lifecycleFromXml(info.configs.lifecycle);
  const original = editing ? rules.find((r) => r.id === ctx.query.id) : null;
  if (editing && !original) {
    showLoadError(new Error(`The lifecycle rule "${ctx.query.id || ""}" does not exist.`), crumbs, "Lifecycle rule not found");
    return;
  }
  const r = original ? JSON.parse(JSON.stringify(original)) : emptyRule();
  const back = bucketHref(bucket, { tab: "management" });
  const errors = errorSlot();

  // ---------------------------------------------------------------- configuration
  const name = input({ value: r.id, maxlength: "255" });
  const nameField = field({ label: "Lifecycle rule name", control: name, constraint: "Up to 255 characters." });
  const status = radioGroup({
    ariaLabel: "Status",
    value: r.status,
    items: [
      { value: "Enabled", label: "Enabled" },
      { value: "Disabled", label: "Disabled" },
    ],
  });
  const allAck = checkbox({ label: "I acknowledge that this rule will apply to all objects in the bucket." });
  const allWarn = alert({ type: "warning", title: "This rule will apply to all objects in the bucket" }, "If you want the rule to apply to specific objects, use a filter to identify those objects.", h("div", { class: "alert__ack" }, allAck));
  const prefix = input({ value: r.prefix, placeholder: "Enter prefix" });
  const tags = tagEditor({ tags: r.tags, max: 10, addLabel: "Add tag", emptyText: "No object tags in the filter." });
  const minSize = sizeControl("Specify minimum object size", r.sizeGt);
  const maxSize = sizeControl("Specify maximum object size", r.sizeLt);
  const filters = h(
    "div",
    { class: "stack" },
    fieldset(
      { legend: "Filter type", description: "You can filter objects by prefix, object tags, object size, or whatever combination suits your use case." },
      field({ label: "Prefix", control: prefix, description: "Add filter to limit the scope of this rule to a single prefix.", constraint: "Don't include the bucket name in the prefix." }),
      field({ label: "Object tags", control: tags.el, description: "Only objects with all of these tags are affected." }),
      field({ label: "Object size", control: h("div", { class: "stack-sm" }, minSize.el, maxSize.el), description: "Limit the scope of this rule by object size." }),
    ),
  );
  const scope = radioGroup({
    ariaLabel: "Rule scope",
    value: r.filtered || !editing ? "filtered" : "all",
    onChange: (v) => {
      filters.hidden = v !== "filtered";
      allWarn.hidden = v !== "all";
    },
    items: [
      { value: "filtered", label: "Limit the scope of this rule using one or more filters" },
      { value: "all", label: "Apply to all objects in the bucket" },
    ],
  });
  filters.hidden = scope.value !== "filtered";
  allWarn.hidden = scope.value !== "all";
  if (editing && !r.filtered) allAck.input.checked = true;

  // ---------------------------------------------------------------- actions
  const act = {
    tr: checkbox({ label: "Move current versions of objects between storage classes", checked: r.transitions.length > 0 }),
    nctr: checkbox({ label: "Move noncurrent versions of objects between storage classes", checked: r.ncTransitions.length > 0 }),
    exp: checkbox({ label: "Expire current versions of objects", checked: Boolean(r.expirationDays || r.expirationDate) }),
    ncexp: checkbox({ label: "Permanently delete noncurrent versions of objects", checked: Boolean(r.ncExpirationDays) }),
    cleanup: checkbox({ label: "Delete expired object delete markers or incomplete multipart uploads", checked: r.expiredMarker || Boolean(r.abortDays) }),
  };
  const tr = transitionList(r.transitions, false);
  const nctr = transitionList(r.ncTransitions, true);
  const expDays = daysInput(r.expirationDays, "Days after object creation");
  const ncDays = daysInput(r.ncExpirationDays, "Days after objects become noncurrent");
  const ncNewer = input({ type: "number", min: "1", step: "1", value: r.ncNewer ? String(r.ncNewer) : "", placeholder: "Optional", "aria-label": "Number of newer versions to retain" });
  const markers = checkbox({ label: "Delete expired object delete markers", description: "Removes delete markers that have no noncurrent versions left behind them.", checked: r.expiredMarker });
  const abort = checkbox({ label: "Delete incomplete multipart uploads", checked: Boolean(r.abortDays) });
  const abortDays = daysInput(r.abortDays, "Number of days");
  const abortRow = h("div", { class: "indent", hidden: !abort.input.checked }, field({ label: "Number of days", control: abortDays }));
  abort.input.addEventListener("change", () => {
    abortRow.hidden = !abort.input.checked;
  });

  const sections = {
    tr: container({ title: "Transition current versions of objects between storage classes", headingLevel: 3 }, tr.el),
    nctr: container({ title: "Transition noncurrent versions of objects between storage classes", headingLevel: 3 }, nctr.el),
    exp: container(
      { title: "Expire current versions of objects", headingLevel: 3, description: "For versioned buckets, expiring adds a delete marker and the current version becomes noncurrent. For unversioned buckets, the object is permanently removed." },
      r.expirationDate ? alert({ type: "info" }, `This rule expires objects on ${r.expirationDate.slice(0, 10)} (set with the API). Enter a number of days to replace the date.`) : null,
      field({ label: "Days after object creation", control: expDays }),
    ),
    ncexp: container(
      { title: "Permanently delete noncurrent versions of objects", headingLevel: 3 },
      field({ label: "Days after objects become noncurrent", control: ncDays }),
      field({ label: "Number of newer versions to retain", optional: true, control: ncNewer, description: "Keep this many newer noncurrent versions; older ones are deleted." }),
    ),
    cleanup: container({ title: "Delete expired object delete markers or incomplete multipart uploads", headingLevel: 3 }, markers, abort, abortRow),
  };
  const review = h("div", { class: "review" });

  const syncActions = () => {
    for (const k of Object.keys(act)) sections[k].hidden = !act[k].input.checked;
    const expOn = act.exp.input.checked;
    markers.input.disabled = expOn;
    markers.classList.toggle("is-disabled", expOn);
    if (expOn) markers.input.checked = false;
    drawReview();
  };
  for (const k of Object.keys(act)) act[k].input.addEventListener("change", syncActions);

  function drawReview() {
    const current = [h("li", {}, "Day 0: Objects uploaded")];
    const non = [h("li", {}, "Day 0: Objects become noncurrent")];
    try {
      if (act.tr.input.checked) for (const t of tr.value()) current.push(h("li", {}, t.date ? `On ${t.date.slice(0, 10)}: ` : `Day ${t.days}: `, `Objects move to ${storageClassLabel(t.storageClass)}`));
      if (act.exp.input.checked && expDays.value) current.push(h("li", {}, `Day ${expDays.value}: Objects expire`));
      if (act.nctr.input.checked) for (const t of nctr.value()) non.push(h("li", {}, `Day ${t.days}: Noncurrent versions move to ${storageClassLabel(t.storageClass)}`));
      if (act.ncexp.input.checked && ncDays.value) non.push(h("li", {}, `Day ${ncDays.value}: Noncurrent versions are permanently deleted`));
    } catch {
      /* incomplete input: the review shows what is valid so far */
    }
    mount(
      review,
      h("div", { class: "review__col" }, h("h3", {}, "Current version actions"), h("ol", { class: "timeline" }, current)),
      h("div", { class: "review__col" }, h("h3", {}, "Noncurrent versions actions"), h("ol", { class: "timeline" }, non)),
    );
  }
  const page = h("div", { class: "stack form-page" });
  page.addEventListener("input", () => drawReview());
  syncActions();

  const save = button({ label: editing ? "Save changes" : "Create rule", variant: "primary" });
  save.addEventListener("click", () =>
    busy(save, async () => {
      errors.set(null);
      nameField.setError("");
      try {
        const rule = collect();
        const others = rules.filter((x) => x !== original);
        if (others.some((x) => x.id === rule.id)) {
          nameField.setError("A lifecycle rule with this name already exists.");
          throw new Error("Choose a different lifecycle rule name.");
        }
        await saveLifecycle(bucket, editing ? rules.map((x) => (x === original ? rule : x)) : [...rules, rule]);
        flash("success", "", { title: `Successfully ${editing ? "edited" : "created"} lifecycle rule "${rule.id}"` });
        navigate(bucketPath(bucket), { tab: "management" });
      } catch (e) {
        errors.set(errorText(e));
      }
    }),
  );

  function collect() {
    const out = emptyRule();
    out.id = name.value.trim();
    if (!out.id) {
      nameField.setError("Enter a lifecycle rule name.");
      throw new Error("Enter a lifecycle rule name.");
    }
    out.status = status.value;
    out.filtered = scope.value === "filtered";
    if (out.filtered) {
      if (tags.validate()) throw new Error(tags.validate());
      out.prefix = prefix.value.trim();
      out.tags = tags.getValue();
      out.sizeGt = minSize.value();
      out.sizeLt = maxSize.value();
      if (!out.prefix && !Object.keys(out.tags).length && out.sizeGt === null && out.sizeLt === null) {
        throw new Error("Add at least one filter (prefix, tag or object size), or apply the rule to all objects in the bucket.");
      }
      if (out.sizeGt !== null && out.sizeLt !== null && out.sizeLt <= out.sizeGt) throw new Error("The maximum object size must be larger than the minimum object size.");
    } else if (!allAck.input.checked) {
      throw new Error("Acknowledge that this rule will apply to all objects in the bucket.");
    }
    if (!Object.values(act).some((c) => c.input.checked)) throw new Error("Choose at least one lifecycle rule action.");
    if (act.tr.input.checked) out.transitions = tr.value();
    if (act.nctr.input.checked) out.ncTransitions = nctr.value();
    if (act.exp.input.checked) {
      if (r.expirationDate && expDays.value === "") out.expirationDate = r.expirationDate;
      else out.expirationDays = positive(expDays, "Expire current versions");
    }
    if (act.ncexp.input.checked) {
      out.ncExpirationDays = positive(ncDays, "Permanently delete noncurrent versions");
      out.ncNewer = positive(ncNewer, "Number of newer versions to retain", true);
    }
    if (act.cleanup.input.checked) {
      out.expiredMarker = markers.input.checked;
      out.abortDays = abort.input.checked ? positive(abortDays, "Delete incomplete multipart uploads") : null;
      if (!out.expiredMarker && !out.abortDays) throw new Error("Choose Delete expired object delete markers, Delete incomplete multipart uploads, or both.");
    }
    if (out.abortDays && out.filtered && Object.keys(out.tags).length) {
      throw new Error("Deleting incomplete multipart uploads is not supported with object tag filters.");
    }
    return out;
  }

  mount(
    page,
    pageHeader({ title, description: "Lifecycle rules run automatically on a schedule and apply to the objects that match their scope." }),
    container(
      { title: "Lifecycle rule configuration" },
      h("div", { class: "stack" }, nameField, fieldset({ legend: "Status" }, status), fieldset({ legend: "Choose a rule scope" }, scope), allWarn, filters),
    ),
    container(
      { title: "Lifecycle rule actions", description: "Choose the actions you want this rule to perform." },
      h("div", { class: "stack-sm" }, Object.values(act)),
      !info.versioning ? alert({ type: "info" }, "Bucket Versioning is not enabled: actions on noncurrent versions and delete markers have no effect until it is.") : null,
    ),
    sections.tr,
    sections.nctr,
    sections.exp,
    sections.ncexp,
    sections.cleanup,
    container({ title: "Review transition and expiration actions" }, review),
    errors,
    formActions(button({ label: "Cancel", variant: "link", href: back }), save),
  );
  setPage({ crumbs, title, content: page });
  drawReview();
}
