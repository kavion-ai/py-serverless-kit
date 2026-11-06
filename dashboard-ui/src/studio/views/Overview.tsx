import { compatProblems, setEnabledOn, skipTriggersOn } from "../compat";
import { useConfirm, useToast } from "../components/Feedback";
import { ComboInput, EnumSelect, FieldForm, FormRow, KeyValueEditor, Section, Segmented, TextInput } from "../components/Forms";
import { YAML_ONLY_ONPREM_OPTIONS } from "../route";
import { InlineIssues, PageHeader } from "../components/Misc";
import { ProviderCards } from "../components/ProviderCard";
import { absorbShadows, providerShadows } from "../shadow";
import { useStudio } from "../store";
import type { Json, JsonObject } from "../types";
import { asObject, getIn, isObject, languageOf, runtimeLabel, SERVICE_RE, setIn, str } from "../util";

export const MEMORY = [128, 256, 512, 1024, 1536, 2048, 3008, 4096, 8192, 10240];

export function memoryLabel(mb: number): string {
  return mb >= 1024 && mb % 512 === 0 ? `${mb / 1024} GB` : `${mb} MB`;
}

export function timeoutChoices(max?: number): number[] {
  return [3, 10, 30, 60, 120, 300, 600, 900, 1800, 3600].filter((s) => !max || s <= max);
}

export function durationLabel(seconds: number): string {
  if (seconds < 60 || seconds % 60) return `${seconds} s`;
  if (seconds < 3600 || seconds % 3600) return `${seconds / 60} min`;
  return `${seconds / 3600} h`;
}

export function OverviewView() {
  const studio = useStudio();
  const { draft, meta, edit, replace, provider, providerName, issuesAt } = studio;
  const confirm = useConfirm();
  const toast = useToast();
  const prov = asObject(draft.provider);
  const issues = (p: (string | number)[]) => issuesAt(p).map((i) => i.message);

  const switchProvider = async (name: string) => {
    if (name === providerName) return;
    const next = meta.providers.find((p) => p.name === name);
    if (!next) return;
    const problems = compatProblems(draft, next);
    const lost = problems.map((p) => p.message);
    const answer = await confirm({
      title: `Switch to ${next.display_name}?`,
      body: (
        <div className="stack">
          {lost.length ? (
            <>
              <p>These won't run on {next.display_name}:</p>
              <ul className="bullets">
                {lost.slice(0, 12).map((l) => (
                  <li key={l}>{l}</li>
                ))}
                {lost.length > 12 && <li>…and {lost.length - 12} more</li>}
              </ul>
              <p className="small">
                <b>Switch &amp; disable them on {next.display_name}</b> keeps them for the other clouds: the unsupported triggers
                and workflows are switched off only under <code className="mono">providers.{name}</code>. Turn them back on from
                the Deploy page or the function itself.
              </p>
            </>
          ) : (
            <p>Every function, trigger and workflow is supported on {next.display_name}.</p>
          )}
          <p className="muted small">
            The current provider options move to <code className="mono">providers.{providerName}</code> so switching back
            restores them. Handler code doesn't change.
          </p>
        </div>
      ),
      confirmLabel: lost.length ? `Switch & disable on ${next.display_name}` : "Switch provider",
      extra: lost.length ? [{ label: "Switch only (fix later)", value: "plain" }] : undefined,
    });
    if (answer !== "confirm" && answer !== "plain") return;
    let raw: Json = draft;
    if (answer === "confirm") {
      for (const p of problems) {
        if (p.kind === "trigger" && p.fn && p.types) raw = skipTriggersOn(raw as JsonObject, name, p.fn, p.types);
        else if (p.wf) raw = setEnabledOn(raw as JsonObject, name, "workflows", p.wf, false);
      }
    }
    const oldOptions = prov.options;
    const oldRegion = prov.region;
    if (isObject(oldOptions) && Object.keys(oldOptions).length) raw = setIn(raw, ["providers", providerName, "options"], oldOptions);
    if (oldRegion) raw = setIn(raw, ["providers", providerName, "region"], oldRegion);
    const parked = asObject(getIn(draft, ["providers", name]));
    raw = setIn(raw, ["provider", "name"], name);
    raw = setIn(raw, ["provider", "options"], isObject(parked.options) ? parked.options : undefined);
    raw = setIn(raw, ["provider", "region"], str(parked.region) || next.default_region || undefined);
    // The parked settings are back under provider:, so the parked copy must not shadow later edits.
    raw = absorbShadows(raw as JsonObject);
    const runtime = str(prov.runtime);
    if (runtime && next.runtimes.length && !next.runtimes.includes(runtime)) raw = setIn(raw, ["provider", "runtime"], undefined);
    replace(raw as JsonObject);
    studio.setTarget(name);
    toast(`Provider is now ${next.display_name}`, "ok");
  };

  const options = asObject(prov.options);
  const changeRuntime = async (next: string) => {
    const from = languageOf(str(prov.runtime, provider?.default_runtime || "python3.12"));
    const to = languageOf(next || provider?.default_runtime || "python3.12");
    if (from !== to && Object.keys(asObject(draft.functions)).length) {
      const answer = await confirm({
        title: to === "node" ? "Switch the service to Node.js?" : "Switch the service to Python?",
        body: (
          <p>
            A service is either Python or Node.js. Existing handlers stay as they are: point each function at a{" "}
            {to === "node" ? ".js / .ts" : ".py"} handler (new functions get a stub in the right language).
          </p>
        ),
        confirmLabel: "Switch runtime",
      });
      if (answer !== "confirm") return;
    }
    edit(["provider", "runtime"], next || undefined);
  };
  const optionFields = (provider?.options || []).filter((f) => providerName !== "onprem" || !YAML_ONLY_ONPREM_OPTIONS.has(f.key));
  const serviceName = str(draft.service);
  const shadows = providerShadows(draft);

  return (
    <div className="page">
      <PageHeader title="Overview & provider" subtitle="Service-wide settings. Every function inherits these unless it overrides them." />

      <Section title="Service">
        <FormRow
          label="Service name"
          required
          htmlFor="svc"
          error={[...(SERVICE_RE.test(serviceName) ? [] : ["2–32 lowercase letters, digits or dashes"]), ...issues(["service"])]}
        >
          <TextInput id="svc" mono value={serviceName} onChange={(v) => edit(["service"], v.toLowerCase())} />
        </FormRow>
      </Section>

      {shadows.length > 0 && (
        <div className="hint-box warn">
          <b>providers.{providerName}</b> in pskit.yml overrides {shadows.length === 1 ? "a setting" : `${shadows.length} settings`} shown below, and
          those values win when deploying: <code className="mono">{shadows.slice(0, 8).join(", ")}{shadows.length > 8 ? ", …" : ""}</code>.{" "}
          <button type="button" className="btn btn-sm" onClick={() => replace(absorbShadows(draft))}>
            Use the values shown here
          </button>{" "}
          <span className="muted small">(moves them under provider:, keeping settings only the override has; then Save)</span>
        </div>
      )}
      <Section title="Provider" hint={provider ? `${provider.display_name} · ${provider.tier}` : undefined}>
        <ProviderCards providers={meta.providers} value={providerName} onSelect={(n) => void switchProvider(n)} />
        {provider?.notes && <p className="muted small provider-notes">{provider.notes}</p>}
      </Section>

      <Section title="Defaults for every function">
        <div className="form-grid">
          <FormRow label="Region" htmlFor="region" help={provider ? `default: ${provider.default_region || "none"}` : undefined} error={issues(["provider", "region"])}>
            {provider?.regions && provider.regions.length ? (
              <ComboInput
                id="region"
                value={str(prov.region)}
                options={provider.regions.map((r) => ({ value: r.id, label: r.label }))}
                emptyLabel={`default (${provider.default_region || "provider default"})`}
                placeholder={provider.default_region}
                onChange={(v) => edit(["provider", "region"], v || undefined)}
              />
            ) : (
              <TextInput id="region" mono value={str(prov.region)} placeholder={provider?.default_region || "not used"} onChange={(v) => edit(["provider", "region"], v || undefined)} />
            )}
          </FormRow>
          <FormRow label="Stage" htmlFor="stage" help="dev, staging, prod… (lowercase, ≤ 16)" error={issues(["provider", "stage"])}>
            <ComboInput
              id="stage"
              value={str(prov.stage)}
              options={["dev", "test", "staging", "prod"]}
              emptyLabel="default (dev)"
              placeholder="dev"
              onChange={(v) => edit(["provider", "stage"], v.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 16) || undefined)}
            />
          </FormRow>
          <FormRow label="Runtime" htmlFor="runtime" error={issues(["provider", "runtime"])}>
            <EnumSelect
              id="runtime"
              value={str(prov.runtime)}
              allowEmpty
              emptyLabel={`default (${provider?.default_runtime || "python3.12"})`}
              options={[
                ...(provider?.runtimes.length ? provider.runtimes : ["python3.9", "python3.10", "python3.11", "python3.12", "python3.13"]),
                ...(provider?.node_runtimes || []),
              ].map((r) => ({ value: r, label: runtimeLabel(r) }))}
              onChange={(v) => void changeRuntime(v)}
            />
          </FormRow>
          <FormRow label="Memory (MB)" htmlFor="mem" help="64–32768" error={issues(["provider", "memory"])}>
            <ComboInput
              id="mem"
              numeric
              value={typeof prov.memory === "number" ? String(prov.memory) : ""}
              options={MEMORY.map((m) => ({ value: String(m), label: memoryLabel(m) }))}
              emptyLabel="default (256 MB)"
              onChange={(v) => edit(["provider", "memory"], v === "" ? undefined : Number(v))}
            />
          </FormRow>
          <FormRow label="Timeout (s)" htmlFor="timeout" help={provider ? `max ${provider.max_timeout}s on ${provider.display_name}` : undefined} error={issues(["provider", "timeout"])}>
            <ComboInput
              id="timeout"
              numeric
              value={typeof prov.timeout === "number" ? String(prov.timeout) : ""}
              options={timeoutChoices(provider?.max_timeout).map((s) => ({ value: String(s), label: durationLabel(s) }))}
              emptyLabel="default (30 s)"
              onChange={(v) => edit(["provider", "timeout"], v === "" ? undefined : Number(v))}
            />
          </FormRow>
          <FormRow label="Architecture">
            <Segmented
              label="Architecture"
              value={str(prov.architecture, "x86_64")}
              onChange={(v) => edit(["provider", "architecture"], v === "x86_64" ? undefined : v)}
              options={[
                { value: "x86_64", label: "x86_64" },
                { value: "arm64", label: "arm64" },
              ]}
            />
          </FormRow>
          <FormRow label="Log retention (days)" htmlFor="logret">
            <ComboInput
              id="logret"
              numeric
              value={typeof prov.log_retention_days === "number" ? String(prov.log_retention_days) : ""}
              options={[1, 3, 7, 14, 30, 60, 90, 180, 365].map((d) => ({ value: String(d), label: `${d} day${d === 1 ? "" : "s"}` }))}
              emptyLabel="default (14 days)"
              onChange={(v) => edit(["provider", "log_retention_days"], v === "" ? undefined : Number(v))}
            />
          </FormRow>
        </div>
      </Section>

      <Section title="Environment variables" hint="available to every function" defaultOpen={Object.keys(asObject(prov.environment)).length > 0}>
        <KeyValueEditor value={asObject(prov.environment)} keyPattern={/^[A-Za-z_][A-Za-z0-9_]*$/} onChange={(v) => edit(["provider", "environment"], v, { coalesce: true })} />
        <InlineIssues issues={issuesAt(["provider", "environment"])} />
      </Section>

      <Section title="Tags" defaultOpen={Object.keys(asObject(prov.tags)).length > 0}>
        <KeyValueEditor value={asObject(prov.tags)} secrets={false} keyPlaceholder="tag" addLabel="Add tag" onChange={(v) => edit(["provider", "tags"], v)} />
      </Section>

      {optionFields.length > 0 && (
        <Section title={`${provider?.display_name || providerName} options`} hint="provider.options">
          <FieldForm
            fields={optionFields}
            value={options}
            idPrefix="popt"
            errorsFor={(k) => issues(["provider", "options", k])}
            onChange={(k, v) => edit(["provider", "options", k], v)}
          />
        </Section>
      )}
    </div>
  );
}
