import type { ReactNode } from "react";
import type { Tone } from "../format";

export function Badge({ tone = "accent", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Chip({ children, accent, title }: { children: ReactNode; accent?: boolean; title?: string }) {
  return (
    <span className={accent ? "chip chip-accent" : "chip"} title={title}>
      {children}
    </span>
  );
}
