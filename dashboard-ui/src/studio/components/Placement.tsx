import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useStudio } from "../store";
import type { DeployedGroup, JsonObject, OnPremCluster, OnPremDeployed, OnPremServer } from "../types";
import { asArray, asObject, getIn, isObject, setIn, str } from "../util";
import {
  clusterName,
  GROUP_HINT,
  GROUP_RE,
  groupOf,
  nextGroupName,
  placeableFunctions,
  placementPath,
  prune,
  readPlacement,
  NEW_GROUP,
  effectivePort,
  TARGET_KEYS,
  targetLabel,
  targetValue,
  withKey,
  writePlacement,
  type Placement,
  type PlacementGroup,
  type RunsOnChoice,
  type RunsOnErrors,
} from "../placement";
import { ServerForm } from "./OnPremMachines";
import { ServerSelect } from "./ServerPicker";
import { FormRow, NumberInput, Segmented, TextInput } from "./Forms";

// The draft edits live in ../placement (pure, unit tested); re-exported for the views.
export {
  assignFunction,
  GROUP_RE,
  groupOf,
  moveFunction,
  placeableFunctions,
  placementPath,
  readPlacement,
  renameInPlacement,
  targetLabel,
  type Placement,
  type PlacementGroup,
} from "../placement";

/** Saved servers and clusters for the target pickers (`reload` after saving a new server). */
export function usePlacementTargets(enabled: boolean): { servers: OnPremServer[]; clusters: OnPremCluster[]; reload: () => void } {
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [clusters, setClusters] = useState<OnPremCluster[]>([]);
  const reload = useCallback(() => {
    if (!enabled) return;
    api.onpremServers().then(
      (r) => setServers(r.servers),
      () => setServers([]),
    );
    api.clusters().then(
      (r) => setClusters(r.clusters),
      () => setClusters([]),
    );
  }, [enabled]);
  useEffect(reload, [reload]);
  return { servers, clusters, reload };
}

/** "Where functions run": one target for everything, or groups of functions on different servers / clusters. */
export function PlacementEditor() {
  const { draft, replace, issuesAt } = useStudio();
  const placement = readPlacement(draft);
  const { servers, clusters } = usePlacementTargets(true);
  const functions = placeableFunctions(draft);
  const path = placement?.path || placementPath(draft);
  // Validation reports the merged config: always provider.options.placement, even for a providers.onprem override.
  const issuePath = ["provider", "options", "placement"];
  const groupIssues = (name: string) => issuesAt([...issuePath, "groups", name]);
  const errors = issuesAt(issuePath)
    .filter((i) => !(placement?.groups || []).some((g) => groupIssues(g.name).includes(i)))
    .map((i) => i.message);

  const setMode = (split: boolean) => {
    if (split && !placement) {
      replace(writePlacement(draft, path, "main", [{ name: "main", body: {} }]));
    } else if (!split && placement) {
      replace(prune(setIn(draft, path, undefined) as JsonObject));
    }
  };

  const update = (def: string, groups: { name: string; body: JsonObject }[]) => replace(writePlacement(draft, path, def, groups));
  const groupsNow = () => (placement ? placement.groups.map((g) => ({ name: g.name, body: { ...g.body } })) : []);

  return (
    <div className="placement">
      <div className="row-gap wrap">
        <b>Where functions run</b>
        <Segmented
          label="Where functions run"
          value={placement ? "split" : "one"}
          onChange={(v) => setMode(v === "split")}
          options={[
            { value: "one", label: "All functions on one target" },
            { value: "split", label: "Split functions across servers" },
          ]}
        />
        <code className="mono small muted">provider.options.placement</code>
      </div>
      {!placement ? (
        <p className="muted small">
          Every function runs on the machine or cluster picked above. Split them to put, say, GPU functions on a GPU server and the API on another; each
          server then installs only what its functions need.
        </p>
      ) : (
        <>
          <p className="muted small">
            Every group is its own host with only its functions (and the requirements of their <code className="mono">functions/&lt;name&gt;/</code>{" "}
            folders). Functions call each other, queues, buckets, workflows and HTTP routes across servers automatically. Workflows run on the default group
            (their steps run where their functions are), and logs and invocation counts of every group show up on the default group. Functions not listed in
            any group run on the default group.
          </p>
          {(() => {
            const raw = asObject(getIn(draft, path));
            // On by default behind a load balancer: options.balancer, or a group's cluster with one (own or attached).
            const behind = new Set(
              clusters.filter((c) => !!c.balancer || (c.balancers || []).length > 0).map((c) => c.name),
            );
            const balancer =
              !!getIn(draft, ["provider", "options", "balancer"]) || placement.groups.some((g) => behind.has(clusterName(g.body.cluster)));
            const on = typeof raw.gateway === "boolean" ? raw.gateway : balancer;
            return (
              <label className="check small" title="provider.options.placement.gateway">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(e) => replace(setIn(draft, [...path, "gateway"], e.target.checked === balancer ? undefined : e.target.checked) as JsonObject)}
                />{" "}
                One URL: every group answers every route and passes other groups&apos; routes on
                <span className="muted">
                  {" "}
                  ({on ? "on" : "off"}: {on ? "any server can take any request" : "each server answers only the routes of its own functions"}
                  {balancer ? "; on by default behind a load balancer" : ""})
                </span>
              </label>
            );
          })()}
          {errors.length > 0 && (
            <div className="hint-box warn">
              {errors.map((e, i) => (
                <div key={i}>{e}</div>
              ))}
            </div>
          )}
          <div className="placement-groups">
            {placement.groups.map((g) => (
              <GroupCard
                key={g.name}
                group={g}
                placement={placement}
                functions={functions}
                servers={servers}
                clusters={clusters}
                issues={groupIssues(g.name).map((i) => i.message)}
                onRename={(to) => {
                  const groups = groupsNow().map((x) => (x.name === g.name ? { ...x, name: to } : x));
                  update(placement.default === g.name ? to : placement.default, groups);
                }}
                onBody={(body) => update(placement.default, groupsNow().map((x) => (x.name === g.name ? { name: x.name, body } : x)))}
                onDefault={() => update(g.name, groupsNow())}
                onRemove={() => {
                  const groups = groupsNow().filter((x) => x.name !== g.name);
                  if (!groups.length) {
                    setMode(false);
                    return;
                  }
                  update(placement.default === g.name ? groups[0].name : placement.default, groups);
                }}
                onMoveFunctions={(fns, to) => {
                  // A function lives in one group: moving it lists it in `to` only (the default group needs no
                  // listing: every function not listed elsewhere runs there).
                  const groups = groupsNow().map((x) => {
                    const listed = asArray(x.body.functions).map((f) => str(f)).filter((f) => !fns.includes(f));
                    if (x.name === to && to !== placement.default) listed.push(...fns);
                    return { name: x.name, body: { ...x.body, functions: listed } };
                  });
                  update(placement.default, groups);
                }}
              />
            ))}
          </div>
          <div className="row-gap">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                const taken = placement.groups.map((g) => g.name);
                const name = nextGroupName(taken);
                const body: JsonObject = servers.length ? { server: servers[0].name } : { local: true };
                update(placement.default, [...groupsNow(), { name, body }]);
              }}
            >
              + Add group
            </button>
            <span className="muted small">Two groups on one server each need their own port.</span>
          </div>
        </>
      )}
    </div>
  );
}

function GroupCard({
  group,
  placement,
  functions,
  servers,
  clusters,
  issues,
  onRename,
  onBody,
  onDefault,
  onRemove,
  onMoveFunctions,
}: {
  group: PlacementGroup;
  placement: Placement;
  functions: string[];
  servers: OnPremServer[];
  clusters: OnPremCluster[];
  issues: string[];
  onRename: (to: string) => void;
  onBody: (body: JsonObject) => void;
  onDefault: () => void;
  onRemove: () => void;
  onMoveFunctions: (fns: string[], to: string) => void;
}) {
  const isDefault = placement.default === group.name;
  const [name, setName] = useState(group.name);
  useEffect(() => setName(group.name), [group.name]);
  const taken = placement.groups.some((g) => g.name === name && g.name !== group.name);
  const nameError = !GROUP_RE.test(name) ? GROUP_HINT : taken ? "another group has this name" : null;
  const commitName = () => {
    if (name !== group.name && !nameError) onRename(name);
  };
  const body = group.body;
  const target = targetValue(body);
  const setTarget = (v: string) => {
    const next: JsonObject = {};
    for (const [k, val] of Object.entries(body)) if (!(TARGET_KEYS as readonly string[]).includes(k)) next[k] = val;
    if (v === "local") next.local = true;
    else if (v.startsWith("server:")) next.server = v.slice(7);
    else if (v.startsWith("cluster:")) {
      const c = v.slice(8);
      // Keep {name, replicas} when the same cluster stays picked.
      next.cluster = isObject(body.cluster) && clusterName(body.cluster) === c ? body.cluster : c;
    }
    onBody(next);
  };
  const serverKnown = !body.server || servers.some((s) => s.name === str(body.server));
  const clusterKnown = !body.cluster || clusters.some((c) => c.name === clusterName(body.cluster));
  const others = placement.groups.map((g) => g.name).filter((n) => n !== group.name);
  const groupOfFn = (fn: string) => placement.listedIn[fn] || placement.default;
  const mine = functions.filter((fn) => groupOfFn(fn) === group.name);
  // Unticking a function of the default group needs somewhere else to run: ask where (one other group: there).
  const [leaving, setLeaving] = useState<string[]>([]);
  const [leaveTo, setLeaveTo] = useState("");
  const untick = (fns: string[]) => {
    if (!fns.length) return;
    if (!isDefault) onMoveFunctions(fns, placement.default);
    else if (others.length === 1) onMoveFunctions(fns, others[0]);
    else {
      setLeaving(fns);
      setLeaveTo(others[0] || "");
    }
  };
  return (
    <div className={`placement-group card card-pad${isDefault ? " is-default" : ""}`}>
      <div className="row-gap wrap">
        <TextInput mono value={name} invalid={!!nameError} onChange={setName} onBlur={commitName} aria-label="Group name" />
        {isDefault ? (
          <span className="badge badge-accent" title="Functions not ticked in another group, and every workflow, run here">
            default group
          </span>
        ) : (
          <button type="button" className="btn btn-sm" onClick={onDefault} title="Functions not ticked in another group, and every workflow, will run here">
            Make default
          </button>
        )}
        <span className="grow" />
        <button type="button" className="btn btn-sm btn-danger" onClick={onRemove} title="Its functions move to the default group">
          Remove group
        </button>
      </div>
      {nameError && <div className="form-error">{nameError}</div>}
      {isDefault && (
        <div className="form-help">
          The default group runs every function you don&apos;t tick in another group, and all workflows (logs of every group are collected here).
          Untick a function to move it to another group.
        </div>
      )}
      <div className="form">
        <div className="form-grid">
          <FormRow
            label="Runs on"
            help={isDefault && !target ? "The machine or cluster picked above (provider.options.deploy, or --server)." : undefined}
            error={!isDefault && !target ? "pick a server, cluster or this machine" : null}
          >
            <select className="select" value={target} onChange={(e) => setTarget(e.target.value)} aria-label={`Where group ${group.name} runs`}>
              {(isDefault || !target) && <option value="">{isDefault ? "The deploy target above" : "Pick…"}</option>}
              <option value="local">This machine (local)</option>
              {servers.length > 0 && (
                <optgroup label="Saved servers">
                  {servers.map((s) => (
                    <option key={s.name} value={`server:${s.name}`}>
                      {s.name} ({s.label})
                    </option>
                  ))}
                </optgroup>
              )}
              {!serverKnown && <option value={target}>{str(body.server)} (not saved here)</option>}
              {clusters.length > 0 && (
                <optgroup label="Scaling clusters">
                  {clusters.map((c) => (
                    <option key={c.name} value={`cluster:${c.name}`}>
                      cluster {c.name} ({c.nodes.length} server{c.nodes.length === 1 ? "" : "s"})
                    </option>
                  ))}
                </optgroup>
              )}
              {!clusterKnown && <option value={target}>cluster {clusterName(body.cluster)} (not found)</option>}
            </select>
          </FormRow>
          <FormRow label="Port" help="Optional; needed when two groups share a server.">
            <NumberInput integer min={1} max={65535} value={typeof body.port === "number" ? body.port : undefined} onChange={(v) => onBody(withKey(body, "port", v))} />
          </FormRow>
          <FormRow label="Advertise URL" help="Optional: the address the other groups call, when it differs from the server's.">
            <TextInput mono value={str(body.advertise)} placeholder="http://10.0.0.9:8080" onChange={(v) => onBody(withKey(body, "advertise", v || undefined))} />
          </FormRow>
        </div>
        <FormRow
          label={`Functions (${mine.length} of ${functions.length})`}
          help={
            isDefault
              ? "Ticking a function moves it here; unticking moves it to another group."
              : "Ticking a function moves it here from its group; unticking sends it back to the default group."
          }
        >
          {!functions.length ? (
            <span className="muted small">No functions yet.</span>
          ) : (
            <>
              <div className="row-gap placement-fn-actions">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={mine.length === functions.length}
                  onClick={() => onMoveFunctions(functions.filter((f) => !mine.includes(f)), group.name)}
                >
                  All here
                </button>
                <button type="button" className="btn btn-sm" disabled={!mine.length || (isDefault && !others.length)} onClick={() => untick(mine)}>
                  None
                </button>
              </div>
              <div className="placement-fns">
                {functions.map((fn) => {
                  const where = groupOfFn(fn);
                  const here = where === group.name;
                  return (
                    <label key={fn} className={`placement-fn${here ? " on" : ""}`} title={here ? `Runs in ${group.name}` : `Runs in ${where}; tick to move it here`}>
                      <input
                        type="checkbox"
                        checked={here}
                        disabled={here && isDefault && !others.length}
                        onChange={(e) => (e.target.checked ? onMoveFunctions([fn], group.name) : untick([fn]))}
                      />
                      <span className="mono">{fn}</span>
                      {!here && <span className="muted small">· {where}</span>}
                    </label>
                  );
                })}
              </div>
              {isDefault && !others.length && <div className="form-help">Add another group to move functions out of the default group.</div>}
              {leaving.length > 0 && (
                <div className="hint-box row-gap wrap" role="group" aria-label="Move functions to another group">
                  <span className="small">
                    Move <span className="mono">{leaving.join(", ")}</span> to
                  </span>
                  <select className="select" value={leaveTo} onChange={(e) => setLeaveTo(e.target.value)} aria-label="Group to move to">
                    {others.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={() => {
                      onMoveFunctions(leaving, leaveTo);
                      setLeaving([]);
                    }}
                  >
                    Move
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => setLeaving([])}>
                    Cancel
                  </button>
                </div>
              )}
            </>
          )}
        </FormRow>
        {issues.map((e, i) => (
          <div key={i} className="form-error">
            {e}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Small badge: the group (and its server) a function runs on. */
export function GroupBadge({ placement, fn }: { placement: Placement | null; fn: string }) {
  if (!placement) return null;
  const group = groupOf(placement, fn);
  const body = placement.groups.find((g) => g.name === group)?.body || {};
  const where = targetLabel(body);
  return (
    <span className="badge badge-info" title={`Placement group ${group}${where ? ` on ${where}` : ""}`}>
      {group}
      {where ? ` · ${where}` : ""}
    </span>
  );
}

/**
 * The function editor's "Runs on" field (on premises): an existing placement group, or "+ New group…" with its
 * name, where it runs (a saved server, a cluster or this machine) and an optional port. Without placement the
 * only group is the current deploy target; creating a group there creates the placement.
 */
export function RunsOnField({
  placement,
  value,
  onChange,
  errors,
  servers,
  clusters,
  onServerAdded,
  id = "frunson",
}: {
  placement: Placement | null;
  value: RunsOnChoice;
  onChange: (next: RunsOnChoice) => void;
  errors: RunsOnErrors;
  servers: OnPremServer[];
  clusters: OnPremCluster[];
  onServerAdded: () => void;
  id?: string;
}) {
  const { draft } = useStudio();
  const [adding, setAdding] = useState(false);
  const set = (patch: Partial<RunsOnChoice>) => onChange({ ...value, ...patch });
  const isNew = value.group === NEW_GROUP;
  const kind = value.target.startsWith("cluster:") ? "cluster" : value.target === "local" ? "local" : "server";
  const serverValue = value.target.startsWith("server:") ? value.target.slice(7) : "";
  const clusterValue = value.target.startsWith("cluster:") ? value.target.slice(8) : "";
  const portPlaceholder = String(effectivePort(draft, {}));
  const pick = (group: string) => {
    if (group !== NEW_GROUP) {
      set({ group });
      return;
    }
    const taken = placement ? placement.groups.map((g) => g.name) : [value.defaultName];
    set({ group, name: value.name || nextGroupName(taken), target: value.target || (servers.length ? `server:${servers[0].name}` : "local") });
  };
  return (
    <div className="runs-on">
      <select id={id} className="select" value={value.group} onChange={(e) => pick(e.target.value)} aria-label="Runs on">
        {placement ? (
          placement.groups.map((g) => {
            const where = targetLabel(g.body);
            const isDefault = g.name === placement.default;
            return (
              <option key={g.name} value={g.name}>
                {g.name}
                {isDefault ? " (default)" : ""} — {where || (isDefault ? "the deploy target" : "no target yet")}
                {typeof g.body.port === "number" ? `:${g.body.port}` : ""}
              </option>
            );
          })
        ) : (
          <option value="">Where the project deploys (the deploy target)</option>
        )}
        <option value={NEW_GROUP}>+ New group…</option>
      </select>
      {isNew && (
        <div className="runs-on-new card card-pad" role="group" aria-label="New placement group">
          {!placement && (
            <FormRow
              label="Other functions"
              htmlFor={`${id}-default`}
              error={errors.defaultName}
              help="This creates provider.options.placement: the other functions (and workflows) stay on the deploy target, as the default group with this name."
            >
              <TextInput id={`${id}-default`} mono value={value.defaultName} invalid={!!errors.defaultName} onChange={(v) => set({ defaultName: v })} />
            </FormRow>
          )}
          <FormRow label="Group name" required htmlFor={`${id}-name`} error={errors.name}>
            <TextInput id={`${id}-name`} mono value={value.name} invalid={!!errors.name} placeholder="gpu" onChange={(v) => set({ name: v })} />
          </FormRow>
          <FormRow label="Runs on" error={errors.target}>
            <div className="runs-on-target">
              <Segmented
                label="Where the group runs"
                value={kind}
                onChange={(k) =>
                  set({ target: k === "local" ? "local" : k === "cluster" ? (clusters[0] ? `cluster:${clusters[0].name}` : "") : servers[0] ? `server:${servers[0].name}` : "" })
                }
                options={[
                  { value: "server", label: "Saved server" },
                  { value: "cluster", label: "Cluster", disabled: !clusters.length },
                  { value: "local", label: "This machine" },
                ]}
              />
              {kind === "server" && (
                <div className="row-gap wrap">
                  <ServerSelect
                    value={serverValue}
                    onChange={(v) => set({ target: v === "local" ? "local" : v ? `server:${v}` : "" })}
                    servers={servers}
                    deployed={null}
                    label="Saved server"
                    emptyLabel={servers.length ? "Pick a server…" : "No saved servers yet"}
                  />
                  <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
                    + Add server
                  </button>
                </div>
              )}
              {kind === "cluster" && (
                <select className="select" value={clusterValue} onChange={(e) => set({ target: e.target.value ? `cluster:${e.target.value}` : "" })} aria-label="Cluster">
                  {!clusterValue && <option value="">Pick a cluster…</option>}
                  {clusters.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name} ({c.nodes.length} server{c.nodes.length === 1 ? "" : "s"})
                    </option>
                  ))}
                </select>
              )}
              {kind === "local" && <span className="muted small">The machine running pskit (and this studio).</span>}
            </div>
          </FormRow>
          <FormRow
            label="Port"
            htmlFor={`${id}-port`}
            error={errors.port}
            help={`Optional (default ${portPlaceholder}). Two groups on one server need different ports.`}
          >
            <div className="row-gap wrap">
              <NumberInput id={`${id}-port`} integer min={1} max={65535} value={value.port} placeholder={portPlaceholder} onChange={(v) => set({ port: v })} />
              {errors.suggestPort !== undefined && (
                <button type="button" className="btn btn-sm" onClick={() => set({ port: errors.suggestPort })}>
                  Use {errors.suggestPort}
                </button>
              )}
            </div>
          </FormRow>
        </div>
      )}
      {adding && (
        <ServerForm
          initial={null}
          taken={servers.map((s) => s.name)}
          onClose={() => setAdding(false)}
          onSaved={(name) => {
            setAdding(false);
            onServerAdded();
            set({ target: `server:${name}` });
          }}
        />
      )}
    </div>
  );
}

/** Where a deployed group runs, for one line of text: "cluster prod", "app1" or "this machine". */
export function groupWhere(g: DeployedGroup): string {
  return g.cluster ? `cluster ${g.cluster}` : g.server || (g.deploy === "local" || !g.deploy ? "this machine" : g.deploy);
}

/** After a deploy: each placement group's host and the load balancer URLs (deployment.json `groups` / `balancers`). */
export function DeployedGroups({ deployed }: { deployed: OnPremDeployed | null }) {
  const groups = Object.entries(deployed?.groups || {});
  const balancers = deployed?.balancers || [];
  if (!groups.length && !balancers.length) return null;
  return (
    <div className="deployed-groups">
      {groups.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Group</th>
                <th>Where</th>
                <th>Endpoint</th>
                <th>Functions</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(([name, g]) => (
                <tr key={name}>
                  <td className="mono">{name}</td>
                  <td className="small">{groupWhere(g)}</td>
                  <td className="mono small">
                    {g.endpoint ? (
                      <a href={g.endpoint} target="_blank" rel="noreferrer">
                        {g.endpoint}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <span className="chips">
                      {(g.functions || []).map((f) => (
                        <span key={f} className="chip">
                          {f}
                        </span>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {balancers.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Load balancer</th>
                <th>URL</th>
              </tr>
            </thead>
            <tbody>
              {balancers.map((b) => (
                <tr key={`${b.name}:${b.key}`}>
                  <td className="mono">{b.name}</td>
                  <td className="mono small">
                    <a href={b.url} target="_blank" rel="noreferrer">
                      {b.url}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
