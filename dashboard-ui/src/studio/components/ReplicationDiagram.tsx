/** How a replicated database scales: the functions, the load balancer (or the driver), the primary that takes the
 * writes, and the read replicas that copy it. Drawn from the form while it is filled in, and from a created
 * service's topology (with each member's state). */

export interface DiagramNode {
  /** Saved server name, or "this machine". */
  title: string;
  /** address:port */
  detail?: string;
  /** running / exited / missing (status only). */
  state?: string;
}

export interface ReplicationDiagramProps {
  /** PostgreSQL, MySQL, ... */
  engine: string;
  sync: "async" | "sync";
  primary: DiagramNode;
  replicas: DiagramNode[];
  /** The load balancer; null when the functions connect to the members themselves. */
  balancer: (DiagramNode & { kind: string }) | null;
  /** MongoDB: the driver routes from one replica set URL. */
  driverRoutes?: boolean;
  /** Show a "+ more replicas later" slot. */
  growable?: boolean;
}

const W = 720;
const COL_L = 70; // primary column x
const COL_R = 440; // replica column x
const BOX_W = 210;
const REP_H = 58;
const REP_GAP = 14;
const BUS_X = COL_R + BOX_W + 24;

const COLORS = {
  write: "var(--warn)",
  read: "var(--info)",
  repl: "var(--ok)",
  line: "var(--line-strong)",
};

function stateColor(state?: string) {
  if (!state) return "var(--line-strong)";
  return state === "running" ? "var(--ok)" : "var(--err)";
}

function Box({ x, y, w, h, role, node, accent }: { x: number; y: number; w: number; h: number; role: string; node: DiagramNode; accent: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill="var(--panel)" stroke={accent} strokeWidth={1.6} />
      <rect x={x} y={y} width={5} height={h} rx={2} fill={accent} />
      <text x={x + 14} y={y + 18} fontSize={12} fontWeight={700} fill="var(--text)">
        {role}
      </text>
      <text x={x + 14} y={y + 34} fontSize={11} fill="var(--muted)">
        {node.title.length > 28 ? node.title.slice(0, 27) + "…" : node.title}
      </text>
      {node.detail && h >= 56 && (
        <text x={x + 14} y={y + 49} fontSize={10.5} fill="var(--muted)" fontFamily="var(--mono)">
          {node.detail}
        </text>
      )}
      {node.state && (
        <g>
          <circle cx={x + w - 14} cy={y + 14} r={5} fill={stateColor(node.state)} />
          <title>{node.state}</title>
        </g>
      )}
    </g>
  );
}

function Label({ x, y, text, color, anchor = "middle" }: { x: number; y: number; text: string; color: string; anchor?: "start" | "middle" | "end" }) {
  const width = text.length * 6.1 + 10;
  const left = anchor === "middle" ? x - width / 2 : anchor === "end" ? x - width : x;
  return (
    <g>
      <rect x={left} y={y - 11} width={width} height={16} rx={8} fill="var(--panel)" stroke={color} strokeWidth={0.8} />
      <text x={left + width / 2} y={y + 1} fontSize={10.5} textAnchor="middle" fill={color} fontWeight={600}>
        {text}
      </text>
    </g>
  );
}

export function ReplicationDiagram({ engine, sync, primary, replicas, balancer, driverRoutes, growable }: ReplicationDiagramProps) {
  const lb = balancer;
  const shown = replicas.length ? replicas : [{ title: "pick a server", detail: "" }];
  const slots = shown.length + (growable ? 1 : 0);
  const funcY = 10;
  const lbY = 84;
  const top = lb ? 178 : 112;
  const colH = slots * REP_H + (slots - 1) * REP_GAP;
  const primH = 64;
  const primY = top + Math.max(0, (colH - primH) / 2);
  const height = top + Math.max(colH, primH) + 56;
  const repY = (i: number) => top + i * (REP_H + REP_GAP);
  const repMid = (i: number) => repY(i) + REP_H / 2;
  const primMidY = primY + primH / 2;
  const front = lb ? { x: W / 2, y: lbY + 58 } : { x: W / 2, y: funcY + 42 };
  const syncLabel = sync === "sync" ? "sync: commit waits for a replica" : "async: copied right after commit";
  const dash = sync === "sync" ? undefined : "6 5";

  return (
    <svg className="replication-diagram" viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label={`${engine}: primary with ${replicas.length} read replicas, ${sync} replication`}>
      <defs>
        {(["write", "read", "repl"] as const).map((k) => (
          <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={COLORS[k]} />
          </marker>
        ))}
        <style>{`.replication-diagram .flow { animation: pskit-flow 1.2s linear infinite; } @keyframes pskit-flow { to { stroke-dashoffset: -22; } } @media (prefers-reduced-motion: reduce) { .replication-diagram .flow { animation: none; } }`}</style>
      </defs>

      {/* the functions */}
      <Box x={W / 2 - 100} y={funcY} w={200} h={42} role="Your functions" node={{ title: lb ? "one address (URL)" : driverRoutes ? "one replica set URL" : "URL + READ_URLS" }} accent="var(--accent)" />

      {lb && (
        <>
          <line x1={W / 2} y1={funcY + 42} x2={W / 2} y2={lbY} stroke={COLORS.line} strokeWidth={2} markerEnd="url(#arrow-read)" />
          <Box x={W / 2 - 115} y={lbY} w={230} h={58} role={`Load balancer · ${lb.kind}`} node={lb} accent="var(--accent)" />
        </>
      )}

      {/* writes: front -> primary */}
      <path
        d={`M ${front.x - 40} ${front.y} C ${front.x - 40} ${front.y + 40}, ${COL_L + BOX_W / 2} ${primY - 40}, ${COL_L + BOX_W / 2} ${primY}`}
        fill="none"
        stroke={COLORS.write}
        strokeWidth={2.2}
        markerEnd="url(#arrow-write)"
      />
      <Label x={(front.x - 40 + COL_L + BOX_W / 2) / 2} y={(front.y + primY) / 2} text={driverRoutes ? "writes (driver)" : "writes"} color={COLORS.write} />

      {/* reads: front -> bus -> each replica */}
      <path d={`M ${front.x + 40} ${front.y} C ${front.x + 40} ${front.y + 20}, ${BUS_X} ${front.y + 10}, ${BUS_X} ${top}`} fill="none" stroke={COLORS.read} strokeWidth={2.2} strokeDasharray={lb || driverRoutes ? undefined : "3 4"} />
      <line x1={BUS_X} y1={top} x2={BUS_X} y2={repMid(shown.length - 1)} stroke={COLORS.read} strokeWidth={2.2} />
      {shown.map((_r, i) => (
        <line key={i} x1={BUS_X} y1={repMid(i)} x2={COL_R + BOX_W + 2} y2={repMid(i)} stroke={COLORS.read} strokeWidth={2} markerEnd="url(#arrow-read)" />
      ))}
      <Label
        x={BUS_X + 4}
        y={front.y + 24}
        anchor="end"
        text={lb ? "reads, balanced" : driverRoutes ? "reads (secondaryPreferred)" : "reads (READ_URLS)"}
        color={COLORS.read}
      />

      {/* replication: primary -> each replica */}
      {shown.map((_r, i) => (
        <path
          key={i}
          className={dash ? "flow" : undefined}
          d={`M ${COL_L + BOX_W} ${primMidY} C ${(COL_L + BOX_W + COL_R) / 2} ${primMidY}, ${(COL_L + BOX_W + COL_R) / 2} ${repMid(i)}, ${COL_R - 2} ${repMid(i)}`}
          fill="none"
          stroke={COLORS.repl}
          strokeWidth={2}
          strokeDasharray={dash}
          markerEnd="url(#arrow-repl)"
        />
      ))}
      <Label x={(COL_L + BOX_W + COL_R) / 2} y={primMidY - (shown.length > 1 ? 0 : 12)} text={sync === "sync" ? "sync" : "async"} color={COLORS.repl} />

      <Box x={COL_L} y={primY} w={BOX_W} h={primH} role="Primary · writes" node={primary} accent={COLORS.write} />
      {shown.map((r, i) => (
        <Box key={i} x={COL_R} y={repY(i)} w={BOX_W} h={REP_H} role={driverRoutes ? `Secondary ${i + 1} · reads` : `Replica ${i + 1} · reads`} node={r} accent={COLORS.read} />
      ))}
      {growable && (
        <g>
          <rect x={COL_R} y={repY(shown.length)} width={BOX_W} height={REP_H} rx={10} fill="none" stroke="var(--line-strong)" strokeDasharray="5 4" />
          <text x={COL_R + BOX_W / 2} y={repY(shown.length) + 29} fontSize={11.5} textAnchor="middle" fill="var(--muted)">
            + more replicas later, on demand
          </text>
        </g>
      )}

      {/* legend */}
      <g transform={`translate(16, ${height - 26})`} fontSize={11} fill="var(--muted)">
        <line x1={0} y1={0} x2={26} y2={0} stroke={COLORS.write} strokeWidth={2.2} />
        <text x={32} y={4}>writes → primary</text>
        <line x1={150} y1={0} x2={176} y2={0} stroke={COLORS.read} strokeWidth={2.2} />
        <text x={182} y={4}>reads → replicas</text>
        <line x1={300} y1={0} x2={326} y2={0} stroke={COLORS.repl} strokeWidth={2} strokeDasharray={dash} />
        <text x={332} y={4}>{syncLabel}</text>
      </g>
    </svg>
  );
}
