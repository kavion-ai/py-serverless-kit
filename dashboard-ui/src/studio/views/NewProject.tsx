import { useState } from "react";
import { ErrorBanner } from "../../components/Feedback";
import { api, ApiError, errorMessage } from "../api";
import { FormRow, Segmented, TextInput } from "../components/Forms";
import { useConfirm } from "../components/Feedback";
import { ProviderCards } from "../components/ProviderCard";
import type { Meta, ProjectState } from "../types";
import { SERVICE_RE } from "../util";

const TEMPLATES = [
  { value: "http", label: "HTTP API", hint: "One HTTP function. The smallest start." },
  { value: "events", label: "Events", hint: "HTTP plus schedule, queue, storage and topic examples." },
  { value: "workflow", label: "Workflow", hint: "HTTP plus a small step-function workflow." },
  { value: "full", label: "Everything", hint: "All of the above." },
] as const;

type Template = (typeof TEMPLATES)[number]["value"];

export function NewProject({ meta, onCreated }: { meta: Meta; onCreated: (p: ProjectState) => void }) {
  const [service, setService] = useState("my-service");
  const [provider, setProvider] = useState(meta.providers[0]?.name || "aws");
  const [template, setTemplate] = useState<Template>("http");
  const [language, setLanguage] = useState<"python" | "javascript" | "typescript">("python");
  const nodeOk = (meta.providers.find((p) => p.name === provider)?.node_runtimes || []).length > 0;
  const lang = nodeOk ? language : "python";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();
  const valid = SERVICE_RE.test(service);

  const create = async (force = false) => {
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.init(service, provider, template, force, lang));
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 409) {
        const ok = await confirm({
          title: "Files already exist",
          body: `${exc.message}. Overwrite the scaffold files (pskit.yml, app/handlers.py, …)?`,
          confirmLabel: "Overwrite",
          danger: true,
        });
        if (ok) return create(true);
      } else {
        setError(errorMessage(exc));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wizard-page">
      <div className="wizard card">
        <header className="wizard-head">
          <span className="logo logo-lg" aria-hidden="true">
            λ
          </span>
          <div>
            <h1>Create a pskit project</h1>
            <p className="muted">No pskit.yml in this folder yet. Pick a name, a cloud and a starting point. You can change everything later.</p>
          </div>
        </header>
        <div className="stack">
          <FormRow
            label="Service name"
            required
            htmlFor="svc"
            help="2–32 characters: lowercase letters, digits and dashes. Used to name every cloud resource."
            error={valid ? null : "use 2–32 lowercase letters, digits or dashes, starting with a letter"}
          >
            <TextInput id="svc" value={service} autoFocus mono onChange={(v) => setService(v.toLowerCase())} invalid={!valid} />
          </FormRow>
          <div>
            <div className="form-label">Provider</div>
            <ProviderCards providers={meta.providers} value={provider} onSelect={setProvider} />
          </div>
          <FormRow label="Language" help={lang === "python" ? "Handlers in app/*.py." : lang === "typescript" ? "Handlers in src/*.ts, compiled with tsc when packaging (needs Node.js)." : "Handlers in src/*.js (needs Node.js)."}>
            <Segmented
              label="Language"
              value={lang}
              onChange={setLanguage}
              options={[
                { value: "python", label: "Python" },
                { value: "javascript", label: "JavaScript", disabled: !nodeOk, title: nodeOk ? undefined : "This provider runs Python only in pskit" },
                { value: "typescript", label: "TypeScript", disabled: !nodeOk, title: nodeOk ? undefined : "This provider runs Python only in pskit" },
              ]}
            />
          </FormRow>
          <FormRow label="Template" help={TEMPLATES.find((t) => t.value === template)?.hint}>
            <Segmented label="Template" value={template} onChange={setTemplate} options={TEMPLATES.map((t) => ({ value: t.value, label: t.label }))} />
          </FormRow>
          {error && <ErrorBanner message={error} />}
        </div>
        <footer className="wizard-foot">
          <button type="button" className="btn btn-primary" disabled={!valid || busy} onClick={() => void create()}>
            {busy ? "Creating…" : "Create project"}
          </button>
        </footer>
      </div>
    </div>
  );
}
