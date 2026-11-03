import { useMemo, useState, type ReactNode } from "react";
import { Modal } from "../../components/Drawer";
import { EmptyState } from "../../components/Feedback";
import { isEnabled } from "../compat";
import { EnableControl } from "../components/EnableControl";
import { useConfirm, useToast } from "../components/Feedback";
import { EnumSelect, FormRow, JsonInput, NumberInput, Section, Segmented, TextInput } from "../components/Forms";
import { InlineIssues, PageHeader } from "../components/Misc";
import { href, navigate } from "../route";
import { useStudio } from "../store";
import type { Issue, Json, JsonObject } from "../types";
import { asArray, asObject, getIn, NAME_RE, parseWhere, pathKey, setIn, str, uniqueName, type Path } from "../util";
import { deleteState, layout, newState, NODE_H, NODE_W, renameState, ruleLabel } from "./flow";

const TYPE_INFO: Record<string, { icon: string; blurb: string }> = {
  task: { icon: "λ", blurb: "Call a function" },
  choice: { icon: "◇", blurb: "Branch on the data" },
  wait: { icon: "⏱", blurb: "Pause for N seconds" },
  pass: { icon: "→", blurb: "Pass data through / inject a value" },
  parallel: { icon: "⫴", blurb: "Run branches at the same time" },
  map: { icon: "⟳", blurb: "Run steps for every item in a list" },
  succeed: { icon: "✓", blurb: "Stop successfully" },
  fail: { icon: "✕", blurb: "Stop with an error" },
};

export function WorkflowsView({ rest }: { rest: string[] }) {
  if (rest[0]) return <WorkflowEditor name={rest[0]} />;
  return <WorkflowList />;
}

function WorkflowList() {
  const { draft, edit, replace, providerName, provider, state } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const workflows = Object.entries(asObject(draft.workflows));
  const native = (provider?.capabilities || []).includes("workflow_native");
  const nameError = !NAME_RE.test(newName) ? "letters, digits, - and _; start with a letter" : newName in asObject(draft.workflows) ? "already exists" : null;

  const create = () => {
    edit(["workflows", newName], { start_at: "Start", states: { Start: { type: "pass", end: true } } }, { coalesce: false });
    setCreating(false);
    navigate("workflows", newName);
  };

  return (
    <div className="page">
      <PageHeader
        title="Workflows"
        subtitle={
          native
            ? providerName === "azure"
              ? "On Azure Functions workflows run on the embedded engine by default; pick engine native to compile them to Azure Logic Apps."
              : `On ${provider?.display_name} workflows compile to the native engine (Step Functions / Cloud Workflows) unless you pick embedded.`
            : `On ${provider?.display_name || providerName} workflows run on pskit's embedded engine inside a generated orchestrator function.`
        }
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setNewName(uniqueName("my-workflow", Object.keys(asObject(draft.workflows))));
              setCreating(true);
            }}
          >
            + Create workflow
          </button>
        }
      />
      {!workflows.length ? (
        <div className="card">
          <EmptyState title="No workflows yet" icon="⇉">
            Chain functions into a state machine with branches, retries, waits, parallel branches and maps.
          </EmptyState>
        </div>
      ) : (
        <div className="wf-cards">
          {workflows.map(([name, raw]) => {
            const wf = asObject(raw);
            const states = Object.entries(asObject(wf.states));
            const engine = state.validation?.engines?.[name] || str(wf.engine, "auto");
            return (
              <div key={name} className={`card wf-card${isEnabled(draft, providerName, "workflows", name) ? "" : " row-disabled"}`}>
                <a href={href("workflows", name)} className="wf-card-main">
                  <b>{name}</b>
                  <span className="muted small">{str(wf.description) || `${states.length} states, starts at ${str(wf.start_at)}`}</span>
                  <span className="chips">
                    {states.slice(0, 8).map(([s, st]) => (
                      <span key={s} className="chip">
                        {TYPE_INFO[str(asObject(st).type)]?.icon || "?"} {s}
                      </span>
                    ))}
                    {states.length > 8 && <span className="chip">+{states.length - 8}</span>}
                  </span>
                </a>
                <div className="row-gap">
                  <span className="badge badge-info">{engine}</span>
                  <EnableControl section="workflows" name={name} compact />
                  <span className="grow" />
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    onClick={async () => {
                      const ok = await confirm({ title: `Delete workflow ${name}?`, confirmLabel: "Delete", danger: true });
                      if (ok !== "confirm") return;
                      replace(setIn(draft, ["workflows", name], undefined) as JsonObject);
                      toast(`Deleted ${name} (not saved yet)`, "info");
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <Modal
        open={creating}
        title="New workflow"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" disabled={!!nameError} onClick={create}>
              Create
            </button>
          </>
        }
      >
        <FormRow label="Name" required error={nameError}>
          <TextInput
            mono
            autoFocus
            value={newName}
            onChange={setNewName}
            invalid={!!nameError}
          />
        </FormRow>
      </Modal>
    </div>
  );
}

// --------------------------------------------------------------------- editor

function WorkflowEditor({ name }: { name: string }) {
  const studio = useStudio();
  const { draft, edit, meta, provider, issuesAt } = studio;
  const toast = useToast();
  const confirm = useConfirm();
  // Path from the workflow root to the definition being edited (for parallel branches / map iterators).
  const [nested, setNested] = useState<Path>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const root: Path = ["workflows", name];
  const wf = asObject(getIn(draft, root));
  if (!getIn(draft, root)) {
    return (
      <div className="page">
        <PageHeader title="Workflow not found" />
        <a className="btn" href={href("workflows")}>
          ← Back
        </a>
      </div>
    );
  }
  const defPath: Path = [...root, ...nested];
  const def = asObject(getIn(draft, defPath));
  const states = asObject(def.states);
  const functions = Object.keys(asObject(draft.functions)).filter((f) => !f.endsWith("-orchestrator"));
  const stateTypes = meta.workflow.state_types.length ? meta.workflow.state_types : Object.keys(TYPE_INFO);
  const setDef = (next: JsonObject) => edit(defPath, next, { coalesce: false });
  const allIssues = issuesAt(root);
  const stateIssues = (state: string): Issue[] => {
    const want = pathKey([...defPath, "states", state]);
    return allIssues.filter((i) => i.where && pathKey(parseWhere(i.where)).startsWith(want));
  };

  const addState = (type: string) => {
    const base = type === "task" ? "Call" : type[0].toUpperCase() + type.slice(1);
    const stateName = uniqueName(base, Object.keys(states));
    const next: JsonObject = { ...def, states: { ...states, [stateName]: newState(type, functions) } };
    // Chain it after the selected state when that state simply ends.
    if (selected && selected in states) {
      const sel = asObject(states[selected]);
      if (sel.end === true && ["task", "pass", "wait", "parallel", "map"].includes(str(sel.type))) {
        const { end: _end, ...rest } = sel;
        void _end;
        next.states = { ...asObject(next.states), [selected]: { ...rest, next: stateName } };
      }
    }
    if (!def.start_at || !(str(def.start_at) in states)) next.start_at = stateName;
    setDef(next);
    setSelected(stateName);
  };

  const crumbs = (() => {
    const out: { label: string; path: Path }[] = [{ label: name, path: [] }];
    for (let i = 0; i < nested.length; i++) {
      const seg = nested[i];
      if (seg === "branches" && typeof nested[i + 1] === "number") {
        out.push({ label: `${String(nested[i - 1])} › branch ${(nested[i + 1] as number) + 1}`, path: nested.slice(0, i + 2) });
      } else if (seg === "iterator") {
        out.push({ label: `${String(nested[i - 1])} › each item`, path: nested.slice(0, i + 1) });
      }
    }
    return out;
  })();

  const engineOptions = meta.workflow.engines.length ? meta.workflow.engines : ["auto", "native", "embedded"];
  const nativeOk = (provider?.capabilities || []).includes("workflow_native");

  return (
    <div className="page page-wide">
      <PageHeader
        title={
          <span className="row-gap">
            <a href={href("workflows")} className="muted">
              Workflows
            </a>
            <span className="muted">/</span>
            {name}
          </span>
        }
        subtitle={str(wf.description) || undefined}
      />
      {nested.length === 0 && (
        <Section title="Settings" defaultOpen={false} hint={`engine ${str(wf.engine, "auto")}${wf.timeout ? ` · timeout ${str(wf.timeout)}s` : ""}`}>
          <div className="form-grid">
            <FormRow label="Description">
              <TextInput value={str(wf.description)} onChange={(v) => edit([...root, "description"], v || undefined)} />
            </FormRow>
            <FormRow
              label="Engine"
              help={
                nativeOk
                  ? "auto/native → the provider's workflow service; embedded → a generated orchestrator function."
                  : `${provider?.display_name} has no native workflow service in pskit; it always runs embedded.`
              }
              error={issuesAt([...root, "engine"]).map((i) => i.message)}
            >
              <Segmented
                label="Engine"
                value={str(wf.engine, "auto")}
                onChange={(v) => edit([...root, "engine"], v === "auto" ? undefined : v)}
                options={engineOptions.map((e) => ({ value: e, label: e, disabled: e === "native" && !nativeOk, title: e === "native" && !nativeOk ? "Not available on this provider" : undefined }))}
              />
            </FormRow>
            <FormRow label="Timeout (s)" help="Whole-run limit; TIMED_OUT when exceeded.">
              <NumberInput integer min={1} value={typeof wf.timeout === "number" ? wf.timeout : undefined} onChange={(v) => edit([...root, "timeout"], v)} />
            </FormRow>
          </div>
        </Section>
      )}

      {crumbs.length > 1 && (
        <nav className="crumbs" aria-label="Nested definition">
          {crumbs.map((c, i) => (
            <span key={i}>
              {i > 0 && <span className="muted"> › </span>}
              <button type="button" className="link-btn" disabled={i === crumbs.length - 1} onClick={() => { setNested(c.path); setSelected(null); }}>
                {c.label}
              </button>
            </span>
          ))}
        </nav>
      )}

      <div className="wf-layout">
        <div className="card wf-canvas-card">
          <div className="wf-palette" role="toolbar" aria-label="Add state">
            {stateTypes.map((t) => (
              <button key={t} type="button" className="palette-btn" title={TYPE_INFO[t]?.blurb} onClick={() => addState(t)}>
                <span aria-hidden="true">{TYPE_INFO[t]?.icon || "+"}</span> {t}
              </button>
            ))}
          </div>
          <div className="wf-start row-gap">
            <span className="muted small">Starts at</span>
            <EnumSelect value={str(def.start_at)} options={Object.keys(states)} onChange={(s) => setDef({ ...def, start_at: s })} />
          </div>
          <FlowDiagram def={def} selected={selected} onSelect={setSelected} issuesFor={stateIssues} />
          <InlineIssues issues={allIssues.filter((i) => i.where && !Object.keys(states).some((s) => pathKey(parseWhere(i.where || "")).startsWith(pathKey([...defPath, "states", s]))))} />
        </div>
        <div className="card wf-inspector">
          {selected && selected in states ? (
            <StateInspector
              key={`${pathKey(defPath)}:${selected}`}
              name={selected}
              def={def}
              functions={functions}
              issues={stateIssues(selected)}
              onChange={setDef}
              onRename={(to) => {
                setDef(renameState(def, selected, to));
                setSelected(to);
              }}
              onDelete={async () => {
                const ok = await confirm({ title: `Delete state ${selected}?`, body: "Transitions into it are removed; those states will end instead.", confirmLabel: "Delete", danger: true });
                if (ok !== "confirm") return;
                setDef(deleteState(def, selected));
                setSelected(null);
              }}
              onOpenNested={(p) => {
                setNested([...nested, "states", selected, ...p]);
                setSelected(null);
              }}
              onCreateFunction={() => {
                toast("Create the function, then come back to this workflow", "info");
                navigate("functions", "new");
              }}
            />
          ) : (
            <EmptyState title="Select a state" icon="⇉">
              Click a state in the diagram to edit it, or add one from the palette. A new state is chained after the selected one.
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}

function FlowDiagram({
  def,
  selected,
  onSelect,
  issuesFor,
}: {
  def: JsonObject;
  selected: string | null;
  onSelect: (name: string) => void;
  issuesFor: (state: string) => Issue[];
}) {
  const { nodes, edges, width, height } = useMemo(() => layout(def), [def]);
  const byName = new Map(nodes.map((n) => [n.name, n]));
  const start = str(def.start_at);
  if (!nodes.length) return <EmptyState title="Empty workflow">Add a state from the palette.</EmptyState>;
  return (
    <div className="flow-scroll">
      <svg className="flow-svg" width={Math.max(width, 320)} height={height + 24} role="img" aria-label="Workflow diagram">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" className="flow-arrowhead" />
          </marker>
        </defs>
        {edges.map((e, i) => {
          const a = byName.get(e.from);
          const b = byName.get(e.to);
          if (!a || !b) return null;
          const x1 = a.x + NODE_W / 2;
          const y1 = a.y + NODE_H;
          const x2 = b.x + NODE_W / 2;
          const y2 = b.y;
          let d: string;
          let lx: number;
          let ly: number;
          if (b.y > a.y) {
            const my = (y1 + y2) / 2;
            d = `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2 - 2}`;
            lx = (x1 + x2) / 2;
            ly = my;
          } else {
            // Back edge: loop around the right side.
            const rx = Math.max(a.x, b.x) + NODE_W + 28 + (i % 3) * 10;
            d = `M ${a.x + NODE_W} ${a.y + NODE_H / 2} C ${rx} ${a.y + NODE_H / 2}, ${rx} ${b.y + NODE_H / 2}, ${b.x + NODE_W + 2} ${b.y + NODE_H / 2}`;
            lx = rx;
            ly = (a.y + b.y) / 2 + NODE_H / 2;
          }
          return (
            <g key={i} className={`flow-edge flow-edge-${e.kind}`}>
              <path d={d} markerEnd="url(#arrow)" />
              {e.label && (
                <text x={lx} y={ly - 4} textAnchor="middle" className="flow-edge-label">
                  {e.label.length > 30 ? e.label.slice(0, 29) + "…" : e.label}
                </text>
              )}
            </g>
          );
        })}
        {nodes.map((n) => {
          const bad = issuesFor(n.name);
          const errs = bad.filter((i) => i.level === "error").length;
          return (
            <g
              key={n.name}
              className={`flow-n flow-n-${n.type}${n.name === selected ? " selected" : ""}${n.unreachable ? " unreachable" : ""}${errs ? " has-error" : ""}`}
              transform={`translate(${n.x},${n.y})`}
              tabIndex={0}
              role="button"
              aria-label={`${n.type} state ${n.name}${errs ? `, ${errs} error(s)` : ""}`}
              onClick={() => onSelect(n.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(n.name);
                }
              }}
            >
              <rect width={NODE_W} height={NODE_H} rx={n.type === "choice" ? 22 : 10} />
              <text x={14} y={21} className="flow-n-title">
                {(TYPE_INFO[n.type]?.icon || "?") + "  " + (n.name.length > 18 ? n.name.slice(0, 17) + "…" : n.name)}
              </text>
              <text x={14} y={39} className="flow-n-sub">
                {n.type}
                {n.name === start ? " · start" : ""}
                {n.terminal && n.type !== "succeed" && n.type !== "fail" ? " · end" : ""}
                {n.unreachable ? " · unreachable" : ""}
              </text>
              {errs > 0 && (
                <g transform={`translate(${NODE_W - 22},8)`}>
                  <circle r="8" cx="8" cy="8" className="flow-err-dot" />
                  <text x="8" y="12" textAnchor="middle" className="flow-err-text">
                    {errs}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// --------------------------------------------------------------------- inspector

function StateInspector({
  name,
  def,
  functions,
  issues,
  onChange,
  onRename,
  onDelete,
  onOpenNested,
  onCreateFunction,
}: {
  name: string;
  def: JsonObject;
  functions: string[];
  issues: Issue[];
  onChange: (def: JsonObject) => void;
  onRename: (to: string) => void;
  onDelete: () => void;
  onOpenNested: (path: Path) => void;
  onCreateFunction: () => void;
}) {
  const states = asObject(def.states);
  const st = asObject(states[name]);
  const type = str(st.type);
  const others = Object.keys(states).filter((s) => s !== name);
  const [rename, setRename] = useState(name);
  const renameError = rename !== name && (rename in states ? "name in use" : !/^[A-Za-z0-9_ .-]{1,80}$/.test(rename) ? "letters, digits, space, . _ -" : null);
  const set = (key: string, value: Json | undefined) => {
    const next = { ...st };
    if (value === undefined || value === "") delete next[key];
    else next[key] = value;
    onChange({ ...def, states: { ...states, [name]: next } });
  };
  const setMany = (patch: Record<string, Json | undefined>) => {
    const next = { ...st };
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === "") delete next[k];
      else next[k] = v;
    }
    onChange({ ...def, states: { ...states, [name]: next } });
  };
  const flows = ["task", "pass", "wait", "parallel", "map"].includes(type);
  return (
    <div className="inspector">
      <header className="inspector-head">
        <span className="badge badge-accent">
          {TYPE_INFO[type]?.icon} {type}
        </span>
        <span className="grow" />
        <button type="button" className="btn btn-sm btn-danger" onClick={onDelete}>
          Delete
        </button>
      </header>
      <InlineIssues issues={issues} />
      <div className="form">
        <FormRow label="State name" error={renameError || null}>
          <div className="row-gap">
            <TextInput mono value={rename} onChange={setRename} invalid={!!renameError} />
            <button type="button" className="btn btn-sm" disabled={rename === name || !!renameError || !rename} onClick={() => onRename(rename)}>
              Rename
            </button>
          </div>
        </FormRow>
        <FormRow label="Comment">
          <TextInput value={str(st.comment)} onChange={(v) => set("comment", v)} />
        </FormRow>

        {type === "task" && (
          <>
            <FormRow label="Function" required error={st.function && !functions.includes(str(st.function)) ? `no function named ${str(st.function)}` : null}>
              <div className="row-gap">
                <EnumSelect value={str(st.function)} allowEmpty emptyLabel="choose…" options={functions} onChange={(f) => set("function", f)} />
                <button type="button" className="btn btn-sm" onClick={onCreateFunction}>
                  + New
                </button>
              </div>
            </FormRow>
            <FormRow label="Timeout (s)">
              <NumberInput integer min={1} value={typeof st.timeout_seconds === "number" ? st.timeout_seconds : undefined} onChange={(v) => set("timeout_seconds", v)} />
            </FormRow>
          </>
        )}

        {type === "wait" && <WaitFields st={st} setMany={setMany} />}

        {type === "pass" && (
          <FormRow label="Result" help="JSON written at result_path. Leave empty to pass the input through.">
            <JsonInput value={st.result} onChange={(v) => set("result", v)} rows={4} />
          </FormRow>
        )}

        {type === "fail" && (
          <>
            <FormRow label="Error">
              <TextInput mono value={str(st.error)} placeholder="Order.Rejected" onChange={(v) => set("error", v)} />
            </FormRow>
            <FormRow label="Cause">
              <TextInput value={str(st.cause)} onChange={(v) => set("cause", v)} />
            </FormRow>
          </>
        )}

        {type === "map" && (
          <>
            <FormRow label="Items path" help="JSON path of the list, e.g. $.items">
              <TextInput mono value={str(st.items_path)} onChange={(v) => set("items_path", v)} />
            </FormRow>
            <FormRow label="Max concurrency" help="0/empty = unlimited (capped by the engine)">
              <NumberInput integer min={0} value={typeof st.max_concurrency === "number" ? st.max_concurrency : undefined} onChange={(v) => set("max_concurrency", v)} />
            </FormRow>
            <FormRow label="Steps per item">
              <button type="button" className="btn" onClick={() => onOpenNested(["iterator"])}>
                Edit iterator ({Object.keys(asObject(asObject(st.iterator).states)).length} states) →
              </button>
            </FormRow>
          </>
        )}

        {type === "parallel" && (
          <FormRow label="Branches" help="Every branch gets a copy of the input; the result is a list of branch outputs.">
            <div className="stack-xs">
              {asArray(st.branches).map((b, i) => (
                <div key={i} className="row-gap">
                  <button type="button" className="btn btn-sm grow" onClick={() => onOpenNested(["branches", i])}>
                    Branch {i + 1} · {Object.keys(asObject(asObject(b).states)).length} states →
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    aria-label={`Remove branch ${i + 1}`}
                    disabled={asArray(st.branches).length <= 1}
                    onClick={() => set("branches", asArray(st.branches).filter((_, j) => j !== i))}
                  >
                    ✕
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => set("branches", [...asArray(st.branches), { start_at: "Step", states: { Step: { type: "pass", end: true } } }])}
              >
                + Add branch
              </button>
            </div>
          </FormRow>
        )}

        {type === "choice" && <ChoiceRules st={st} others={others} set={set} />}

        {flows && (
          <FormRow label="Then">
            <div className="row-gap wrap">
              <Segmented
                label="Transition"
                value={st.next ? "next" : "end"}
                onChange={(v) => setMany(v === "end" ? { next: undefined, end: true } : { end: undefined, next: others[0] || "" })}
                options={[
                  { value: "next", label: "Go to", disabled: !others.length },
                  { value: "end", label: "End" },
                ]}
              />
              {!!st.next && <EnumSelect value={str(st.next)} options={others} onChange={(n) => setMany({ next: n, end: undefined })} />}
            </div>
          </FormRow>
        )}

        {(flows || type === "choice") && (
          <details className="advanced">
            <summary>Data paths</summary>
            <FormRow label="Input path" help="Select part of the state input, e.g. $.order">
              <TextInput mono value={str(st.input_path)} placeholder="$" onChange={(v) => set("input_path", v)} />
            </FormRow>
            {type !== "choice" && (
              <FormRow label="Result path" help="Where to put the result. $ replaces the data; empty keeps the default ($).">
                <TextInput mono value={st.result_path === null ? "null" : str(st.result_path)} placeholder="$" onChange={(v) => set("result_path", v === "null" ? null : v)} />
              </FormRow>
            )}
          </details>
        )}

        {(type === "task" || type === "parallel" || type === "map") && (
          <>
            <RetryEditor value={asArray(st.retry).map(asObject)} onChange={(v) => set("retry", v.length ? v : undefined)} />
            <CatchEditor value={asArray(st.catch).map(asObject)} others={others} onChange={(v) => set("catch", v.length ? v : undefined)} />
          </>
        )}
      </div>
    </div>
  );
}

function WaitFields({ st, setMany }: { st: JsonObject; setMany: (p: Record<string, Json | undefined>) => void }) {
  const mode = st.seconds_path ? "path" : "seconds";
  return (
    <>
      <FormRow label="Wait">
        <Segmented
          label="Wait mode"
          value={mode}
          onChange={(m) => setMany(m === "path" ? { seconds: undefined, seconds_path: "$.delay" } : { seconds_path: undefined, seconds: 10 })}
          options={[
            { value: "seconds", label: "Fixed seconds" },
            { value: "path", label: "From the data" },
          ]}
        />
      </FormRow>
      {mode === "seconds" ? (
        <FormRow label="Seconds">
          <NumberInput min={0} value={typeof st.seconds === "number" ? st.seconds : undefined} onChange={(v) => setMany({ seconds: v })} />
        </FormRow>
      ) : (
        <FormRow label="Seconds path">
          <TextInput mono value={str(st.seconds_path)} onChange={(v) => setMany({ seconds_path: v })} />
        </FormRow>
      )}
    </>
  );
}

// --------------------------------------------------------------------- choice rules

type ValueKind = "string" | "number" | "boolean" | "null" | "json";

function kindOf(v: Json | undefined): ValueKind {
  if (v === null) return "null";
  if (typeof v === "number") return "number";
  if (typeof v === "boolean") return "boolean";
  if (typeof v === "string" || v === undefined) return "string";
  return "json";
}

function Condition({ rule, onChange, operators }: { rule: JsonObject; onChange: (r: JsonObject) => void; operators: string[] }) {
  const op = Object.keys(rule).find((k) => operators.includes(k)) || operators[0] || "equals";
  const value = rule[op];
  const kind = op === "is_null" || op === "is_present" ? "boolean" : kindOf(value);
  const rebuild = (nextOp: string, nextValue: Json) => {
    const out: JsonObject = { variable: str(rule.variable, "$.") };
    out[nextOp] = nextValue;
    onChange(out);
  };
  return (
    <div className="cond">
      <TextInput mono value={str(rule.variable, "$.")} placeholder="$.status" onChange={(v) => onChange({ ...rule, variable: v })} />
      <EnumSelect value={op} options={operators} onChange={(o) => rebuild(o, o === "is_null" || o === "is_present" ? true : value === undefined ? "" : value)} />
      {op !== "is_null" && op !== "is_present" && (
        <EnumSelect
          value={kind}
          options={["string", "number", "boolean", "null", "json"]}
          onChange={(k) => rebuild(op, k === "number" ? 0 : k === "boolean" ? true : k === "null" ? null : k === "json" ? [] : "")}
        />
      )}
      {kind === "boolean" ? (
        <EnumSelect value={String(value === undefined ? true : value)} options={["true", "false"]} onChange={(b) => rebuild(op, b === "true")} />
      ) : kind === "number" ? (
        <NumberInput value={typeof value === "number" ? value : 0} onChange={(n) => rebuild(op, n ?? 0)} />
      ) : kind === "null" ? (
        <span className="muted mono">null</span>
      ) : kind === "json" ? (
        <JsonInput value={value} onChange={(j) => rebuild(op, j === undefined ? [] : j)} rows={2} />
      ) : (
        <TextInput value={str(value)} onChange={(s) => rebuild(op, s)} placeholder={op === "matches" ? "glob, e.g. order-*" : "value"} />
      )}
    </div>
  );
}

function ChoiceRules({ st, others, set }: { st: JsonObject; others: string[]; set: (k: string, v: Json | undefined) => void }) {
  const { meta } = useStudio();
  const operators = meta.workflow.choice_operators.length ? meta.workflow.choice_operators : ["equals", "not_equals", "gt", "gte", "lt", "lte", "in", "contains", "matches", "is_null", "is_present"];
  const rules = asArray(st.choices).map(asObject);
  const update = (i: number, r: JsonObject) => set("choices", rules.map((x, j) => (j === i ? r : x)));
  return (
    <>
      <FormRow label="Rules" help="Checked top to bottom; the first match wins.">
        <div className="stack">
          {rules.map((rule, i) => {
            const group = Array.isArray(rule.and) ? "and" : Array.isArray(rule.or) ? "or" : rule.not ? "not" : "single";
            const next = str(rule.next);
            const conds = group === "and" || group === "or" ? asArray(rule[group]).map(asObject) : [];
            const single = group === "not" ? asObject(rule.not) : rule;
            const strip = (r: JsonObject) => {
              const { next: _n, ...rest } = r;
              void _n;
              return rest;
            };
            return (
              <div key={i} className="rule card card-pad">
                <div className="row-gap wrap">
                  <b>Rule {i + 1}</b>
                  <Segmented
                    label="Rule kind"
                    value={group}
                    onChange={(g) => {
                      const base = strip(group === "and" || group === "or" ? asObject(conds[0]) : single);
                      const c = Object.keys(base).length ? base : { variable: "$.", equals: "" };
                      if (g === "single") update(i, { ...c, next });
                      else if (g === "not") update(i, { not: c, next });
                      else update(i, { [g]: [c, { variable: "$.", equals: "" }], next });
                    }}
                    options={[
                      { value: "single", label: "if" },
                      { value: "not", label: "if not" },
                      { value: "and", label: "all of" },
                      { value: "or", label: "any of" },
                    ]}
                  />
                  <span className="grow" />
                  <button type="button" className="btn btn-sm btn-ghost" disabled={i === 0} onClick={() => { const r = [...rules]; [r[i - 1], r[i]] = [r[i], r[i - 1]]; set("choices", r); }} aria-label="Move up">
                    ↑
                  </button>
                  <button type="button" className="btn btn-sm btn-ghost" aria-label="Remove rule" onClick={() => set("choices", rules.filter((_, j) => j !== i))}>
                    ✕
                  </button>
                </div>
                {group === "single" && <Condition rule={strip(rule)} operators={operators} onChange={(c) => update(i, { ...c, next })} />}
                {group === "not" && <Condition rule={single} operators={operators} onChange={(c) => update(i, { not: c, next })} />}
                {(group === "and" || group === "or") && (
                  <div className="stack-xs">
                    {conds.map((c, j) => (
                      <div key={j} className="row-gap">
                        <Condition rule={c} operators={operators} onChange={(nc) => update(i, { [group]: conds.map((x, k) => (k === j ? nc : x)), next })} />
                        <button type="button" className="btn btn-sm btn-ghost" disabled={conds.length <= 1} aria-label="Remove condition" onClick={() => update(i, { [group]: conds.filter((_, k) => k !== j), next })}>
                          ✕
                        </button>
                      </div>
                    ))}
                    <button type="button" className="btn btn-sm" onClick={() => update(i, { [group]: [...conds, { variable: "$.", equals: "" }], next })}>
                      + condition
                    </button>
                  </div>
                )}
                <div className="row-gap">
                  <span className="muted">then go to</span>
                  <EnumSelect value={next} allowEmpty emptyLabel="choose…" options={others} onChange={(n) => update(i, { ...rule, next: n })} />
                  {!next && <span className="form-error">pick a state</span>}
                </div>
                <div className="muted small mono">{ruleLabel(rule)}</div>
              </div>
            );
          })}
          <button type="button" className="btn btn-sm" onClick={() => set("choices", [...rules, { variable: "$.", equals: "", next: others[0] || "" }])}>
            + Add rule
          </button>
        </div>
      </FormRow>
      <FormRow label="Otherwise" help="When no rule matches. Without a default the run fails with States.NoChoiceMatched.">
        <EnumSelect value={str(st.default)} allowEmpty emptyLabel="(fail)" options={others} onChange={(d) => set("default", d || undefined)} />
      </FormRow>
    </>
  );
}

// --------------------------------------------------------------------- retry / catch

function ErrorsInput({ value, onChange }: { value: Json[]; onChange: (v: string[]) => void }) {
  return (
    <TextInput
      mono
      value={value.map((e) => str(e)).join(", ")}
      placeholder="* (all errors), or e.g. TimeoutError, Payment.Declined"
      onChange={(t) => onChange(t.split(",").map((x) => x.trim()).filter(Boolean))}
    />
  );
}

function ListBlock({ title, children, onAdd, addLabel }: { title: string; children: ReactNode; onAdd: () => void; addLabel: string }) {
  return (
    <details className="advanced" open>
      <summary>{title}</summary>
      <div className="stack-xs">
        {children}
        <button type="button" className="btn btn-sm" onClick={onAdd}>
          + {addLabel}
        </button>
      </div>
    </details>
  );
}

function RetryEditor({ value, onChange }: { value: JsonObject[]; onChange: (v: JsonObject[]) => void }) {
  const upd = (i: number, patch: JsonObject) => onChange(value.map((r, j) => (j === i ? pruned({ ...r, ...patch }) : r)));
  return (
    <ListBlock title={`Retry (${value.length})`} addLabel="retry rule" onAdd={() => onChange([...value, { errors: ["*"], max_attempts: 3, interval_seconds: 1, backoff_rate: 2 }])}>
      {value.map((r, i) => (
        <div key={i} className="card card-pad stack-xs">
          <div className="row-gap">
            <span className="muted small grow">on errors</span>
            <button type="button" className="btn btn-sm btn-ghost" aria-label="Remove retry" onClick={() => onChange(value.filter((_, j) => j !== i))}>
              ✕
            </button>
          </div>
          <ErrorsInput value={asArray(r.errors)} onChange={(e) => upd(i, { errors: e.length ? e : ["*"] })} />
          <div className="mini-grid">
            <label>
              attempts
              <NumberInput integer min={0} max={99} value={typeof r.max_attempts === "number" ? r.max_attempts : 3} onChange={(v) => upd(i, { max_attempts: v ?? 3 })} />
            </label>
            <label>
              interval s
              <NumberInput min={0} value={typeof r.interval_seconds === "number" ? r.interval_seconds : 1} onChange={(v) => upd(i, { interval_seconds: v ?? 1 })} />
            </label>
            <label>
              backoff ×
              <NumberInput min={1} value={typeof r.backoff_rate === "number" ? r.backoff_rate : 2} onChange={(v) => upd(i, { backoff_rate: v ?? 2 })} />
            </label>
            <label>
              max delay s
              <NumberInput min={0} value={typeof r.max_delay_seconds === "number" ? r.max_delay_seconds : undefined} onChange={(v) => upd(i, { max_delay_seconds: v === undefined ? null : v })} />
            </label>
          </div>
        </div>
      ))}
    </ListBlock>
  );
}

function CatchEditor({ value, others, onChange }: { value: JsonObject[]; others: string[]; onChange: (v: JsonObject[]) => void }) {
  const upd = (i: number, patch: JsonObject) => onChange(value.map((r, j) => (j === i ? pruned({ ...r, ...patch }) : r)));
  return (
    <ListBlock title={`Catch (${value.length})`} addLabel="catch rule" onAdd={() => onChange([...value, { errors: ["*"], next: others[0] || "", result_path: "$.error" }])}>
      {value.map((c, i) => (
        <div key={i} className="card card-pad stack-xs">
          <div className="row-gap">
            <span className="muted small grow">on errors</span>
            <button type="button" className="btn btn-sm btn-ghost" aria-label="Remove catch" onClick={() => onChange(value.filter((_, j) => j !== i))}>
              ✕
            </button>
          </div>
          <ErrorsInput value={asArray(c.errors)} onChange={(e) => upd(i, { errors: e.length ? e : ["*"] })} />
          <div className="row-gap wrap">
            <span className="muted small">go to</span>
            <EnumSelect value={str(c.next)} allowEmpty emptyLabel="choose…" options={others} onChange={(n) => upd(i, { next: n })} />
            <span className="muted small">error at</span>
            <TextInput mono value={str(c.result_path, "$.error")} onChange={(p) => upd(i, { result_path: p })} />
          </div>
          {!c.next && <div className="form-error">pick a state</div>}
        </div>
      ))}
    </ListBlock>
  );
}

function pruned(o: JsonObject): JsonObject {
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(o)) if (v !== null && v !== "") out[k] = v;
  return out;
}
