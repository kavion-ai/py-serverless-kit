import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { OnPremDeployed, OnPremServer } from "../types";

/** Saved SSH servers and where on-prem `stage` was last deployed (null: never deployed from this folder). */
export function useOnPremServers(onprem: boolean, stage: string) {
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [deployed, setDeployed] = useState<OnPremDeployed | null>(null);
  const [loaded, setLoaded] = useState(false);
  const reload = useCallback(() => {
    if (!onprem) {
      setServers([]);
      setDeployed(null);
      return;
    }
    api.onpremServers(stage).then(
      (r) => {
        setServers(r.servers);
        setDeployed(r.deployed || null);
        setLoaded(true);
      },
      () => {
        setServers([]);
        setDeployed(null);
        setLoaded(true);
      },
    );
  }, [onprem, stage]);
  useEffect(reload, [reload]);
  return { servers, deployed, loaded, reload };
}

/**
 * The server a command talks to, starting on the one the stage was deployed to (its saved server, or "" for a
 * deploy that used no saved server). Re-selects it when the stage or its deploy target changes, until the user picks.
 */
export function useServerChoice(onprem: boolean, stage: string) {
  const info = useOnPremServers(onprem, stage);
  const [server, setServer] = useState("");
  const [touched, setTouched] = useState(false);
  useEffect(() => setTouched(false), [stage]);
  const deployedServer = info.deployed?.server || "";
  useEffect(() => {
    if (!touched) setServer(deployedServer);
  }, [deployedServer, touched]);
  const choose = (value: string) => {
    setTouched(true);
    setServer(value);
  };
  return { ...info, server, setServer: choose };
}

export function ServerSelect({
  value,
  onChange,
  servers,
  deployed,
  emptyLabel,
  label = "Server",
}: {
  value: string;
  onChange: (value: string) => void;
  servers: OnPremServer[];
  deployed: OnPremDeployed | null;
  /** The "" option; defaults to where the stage was deployed. */
  emptyLabel?: string;
  label?: string;
}) {
  const known = !value || value === "local" || servers.some((s) => s.name === value);
  return (
    <select className="select" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">{emptyLabel || (deployed ? `Where it was deployed: ${deployed.label}` : "Where it was deployed")}</option>
      <option value="local">This machine (local){deployed && !deployed.server && deployed.method === "local" ? " · deployed here" : ""}</option>
      {servers.map((s) => (
        <option key={s.name} value={s.name}>
          {s.name} ({s.label}){deployed?.server === s.name ? " · deployed here" : ""}
        </option>
      ))}
      {!known && <option value={value}>{value} (not saved any more)</option>}
    </select>
  );
}

/** One line: where the stage runs now. */
export function DeployedBadge({ deployed }: { deployed: OnPremDeployed | null }) {
  if (!deployed) return <span className="muted small">Not deployed from this folder yet.</span>;
  return (
    <span className="muted small">
      Deployed on <b>{deployed.label}</b>
      {deployed.endpoint ? (
        <>
          {" "}
          · <code className="mono">{deployed.endpoint}</code>
        </>
      ) : null}
      {deployed.deployed_at ? ` · ${new Date(deployed.deployed_at).toLocaleString()}` : ""}
    </span>
  );
}
