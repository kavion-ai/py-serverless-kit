import { useEffect, useState } from "react";
import { parseWhere } from "./util";

export type View = "overview" | "setup" | "functions" | "workflows" | "resources" | "cluster" | "balancers" | "network" | "code" | "test" | "deploy" | "logs" | "yaml";
export const VIEWS: View[] = ["overview", "setup", "functions", "workflows", "resources", "cluster", "balancers", "network", "code", "test", "deploy", "logs", "yaml"];

export interface Route {
  view: View;
  /** Remaining segments, URI-decoded. */
  rest: string[];
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  if (raw.startsWith("token=")) return { view: "overview", rest: [] };
  const [path] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map((p) => {
    try {
      return decodeURIComponent(p);
    } catch {
      return p;
    }
  });
  const view = (VIEWS as string[]).includes(parts[0]) ? (parts[0] as View) : "overview";
  return { view, rest: view === parts[0] ? parts.slice(1) : [] };
}

export function useRoute(): Route {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function href(view: View, ...rest: string[]): string {
  const tail = rest.filter((r) => r !== "").map((r) => encodeURIComponent(r).replace(/%2F/g, "/"));
  return "#/" + [view, ...tail].join("/");
}

export function navigate(view: View, ...rest: string[]): void {
  window.location.hash = href(view, ...rest);
}

/** Where to go to fix an issue reported at `where`. */
export function routeForWhere(where?: string): { view: View; rest: string[] } {
  if (!where) return { view: "yaml", rest: [] };
  const path = parseWhere(where);
  const [head, name] = path;
  if (head === "functions" && typeof name === "string") return { view: "functions", rest: [name] };
  if (head === "workflows" && typeof name === "string") return { view: "workflows", rest: [name] };
  if (head === "resources") return { view: "resources", rest: typeof name === "string" ? [name] : [] };
  if (head === "provider" || head === "service" || head === "providers") return { view: "overview", rest: [] };
  if (head === "package") return { view: "overview", rest: [] };
  return { view: "yaml", rest: [] };
}
