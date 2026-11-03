import type { JobLine, JobStatus } from "./types";
import { stripAnsi } from "./util";

/**
 * Structured view of an on-prem `pskit deploy` / `pskit remove` job, parsed from its output lines.
 *
 * The output, in order (core/deployer.py, terraform/runner.py, cli/main.py):
 *   check & build   validation issues, "Packaging <service> for ...", "  collected ...", "  artifact ...", "  terraform: N resource(s) -> ..."
 *   terraform plan  "Running terraform init", "Initializing ...", "Running terraform apply", "<resource>: Refreshing state...", "Plan: ..."
 *   hosts           "terraform_data.host[_<group>]: Creating... / Still creating... [10s elapsed] / Creation complete after 12s [id=...]"
 *                   "terraform_data.host_x (local-exec): ..." its own output; "on-prem host did not become healthy; see ..."
 *                   followed by "  | <host.log line>" (the log tail); "Error: ..." blocks naming the resource;
 *                   "Apply complete! Resources: ..." / "Destroy complete! ..."
 *   load balancer   "Load balancer edge:", "  http://... -> owner: ...", "  WARNING: ..." (core/onprem_balancers.py)
 *   firewall        "Firewall - <title> (open these; ...):", "  <server> (<address>)", "    [REQUIRED] inbound  TCP 8080 ...",
 *                   "    ufw on <server>:", "      sudo ufw ..." (core/onprem_network.py `lines`)
 *   done            "Deployed <service> (<stage>) to ...", "endpoint: ...", "functions:" + URLs, "Dashboard: ...", "Removed."
 *
 * Parallel hosts interleave their lines; each host keeps only its own. Parsing is incremental (O(new lines)).
 */

export type StepStatus = "waiting" | "running" | "done" | "failed" | "cancelled";
export type HostAction = "create" | "modify" | "destroy" | "";

export interface HostStep {
  /** `host` (the default group) or `host_<group with - as _>`. */
  key: string;
  status: StepStatus;
  action: HostAction;
  /** Latest progress, e.g. "Creation complete after 12s" or "20s elapsed". */
  detail: string;
  /** Every line of this resource (prefix kept). */
  lines: string[];
  /** "on-prem host did not become healthy; see .../host.log". */
  error: string[];
  /** The host.log tail printed after it (without the `  | ` marker). */
  tail: string[];
  /** Terraform's `Error:` block that names this resource. */
  errorBlock: string[];
}

export type FirewallLevel = "required" | "feature" | "optional";

export interface FirewallRule {
  level: FirewallLevel;
  direction: string;
  port: string;
  peer: string;
  why: string;
  /** The line without its level mark (when the parts could not be split). */
  text: string;
}

export interface FirewallSection {
  title: string;
  rules: FirewallRule[];
  ufw: string[];
}

export interface FirewallServer {
  /** "name" or "name (address)" as printed. */
  server: string;
  sections: FirewallSection[];
}

/** 0 build, 1 terraform init/plan, 2 apply, 3 after apply (load balancer, firewall), 4 done. */
export type Stage = 0 | 1 | 2 | 3 | 4;

export interface DeployLog {
  stage: Stage;
  build: string[];
  plan: string[];
  /** "Plan: 1 to add, 0 to change, 0 to destroy." or "No changes.". */
  planSummary: string;
  /** Apply output not of a host: other resources, outputs. */
  apply: string[];
  /** "Apply complete! Resources: ..." / "Destroy complete! Resources: ...". */
  applySummary: string;
  hosts: HostStep[];
  balancer: string[];
  balancerWarnings: number;
  firewall: FirewallServer[];
  done: string[];
  endpoints: string[];
  /** Error blocks that name no host. */
  errors: string[][];
  lineCount: number;
}

const RESOURCE_RE = /^((?:module\.[\w-]+\.)*(?:data\.)?[a-z0-9]+_[a-z0-9_]+\.[\w-]+(?:\[[^\]]*\])?)(?: \(([a-z-]+)\))?: (.*)$/;
const HOST_RE = /^terraform_data\.(host(?:_[a-z0-9_]+)?)$/;
const HOST_MENTION_RE = /terraform_data\.(host(?:_[a-z0-9_]+)?)\b/;
const PLAN_START_RE = /^(Running terraform (init|plan|apply|destroy)|Initializing (the backend|provider plugins|modules)|Terraform (has been successfully initialized|used the selected providers|will perform))/;
const APPLY_DONE_RE = /^(Apply|Destroy) complete! Resources: /;
const FIREWALL_RE = /^Firewall - (.*?)(?: \(open these;[^)]*\))?:?\s*$/;
const BALANCER_HEAD_RE = /^(Load balancer [\w.-]+:\s*$|(Setting up|Updating|Rewriting|Stopped) load balancer |Load balancer [\w.-]+ (now|no longer) |Removed \S+ .*from load balancer )/;
const BALANCER_LINE_RE = /^\s+(WARNING: )?(provider\.options\.balancer|(could not update )?load balancer )/i;
const DONE_RE = /^(Deployed \S.* to |Removed\.\s*$)/;
const LEVELS: Record<string, FirewallLevel> = { REQUIRED: "required", NEEDED: "feature", optional: "optional" };
const MAX_BLOCK = 400;

function clean(text: string): string {
  return stripAnsi(text).replace(/\r?\n$/, "").replace(/^[│╷╵] ?/, "");
}

export function emptyDeployLog(): DeployLog {
  return {
    stage: 0,
    build: [],
    plan: [],
    planSummary: "",
    apply: [],
    applySummary: "",
    hosts: [],
    balancer: [],
    balancerWarnings: 0,
    firewall: [],
    done: [],
    endpoints: [],
    errors: [],
    lineCount: 0,
  };
}

type Block =
  | { kind: "error"; lines: string[]; host: HostStep | null }
  | { kind: "firewall"; section: FirewallSection | null; title: string; server: FirewallServer | null; ufw: boolean }
  | { kind: "balancer" }
  | { kind: "done" }
  | null;

export class DeployLogParser {
  private log: DeployLog = emptyDeployLog();
  private lastSeq = -Infinity;
  private block: Block = null;
  private hostsByKey = new Map<string, HostStep>();
  private tailOf = new Set<string>();

  /** Feed lines (any already seen, by `seq`, are skipped). */
  push(lines: JobLine[]): void {
    for (const line of lines) {
      if (line.seq <= this.lastSeq) continue;
      this.lastSeq = line.seq;
      this.line(clean(line.text));
    }
  }

  /** Feed plain text lines (tests). */
  pushText(lines: string[]): void {
    for (const text of lines) this.line(clean(text));
  }

  /** A new object each call (the arrays inside are shared and only grow). */
  snapshot(): DeployLog {
    const log = this.log;
    return {
      ...log,
      hosts: log.hosts.map((h) => ({ ...h })),
      firewall: log.firewall.map((s) => ({ ...s, sections: [...s.sections] })),
      endpoints: [...log.endpoints],
      errors: [...log.errors],
    };
  }

  private host(key: string): HostStep {
    let h = this.hostsByKey.get(key);
    if (!h) {
      h = { key, status: "waiting", action: "", detail: "", lines: [], error: [], tail: [], errorBlock: [] };
      this.hostsByKey.set(key, h);
      this.log.hosts.push(h);
    }
    return h;
  }

  /** Lines that do not belong to a block go to the current stage. */
  private generic(text: string): void {
    const log = this.log;
    const target = [log.build, log.plan, log.apply, log.apply, log.done][log.stage];
    target.push(text);
  }

  private endpoint(url: string): void {
    const u = url.replace(/[),.;]+$/, "");
    if (!this.log.endpoints.includes(u)) this.log.endpoints.push(u);
  }

  private line(text: string): void {
    const log = this.log;
    log.lineCount++;

    // Blocks that continue on indented lines.
    const block = this.block;
    if (block) {
      if (block.kind === "error") {
        if (/^(Error|Warning): /.test(text) || APPLY_DONE_RE.test(text) || FIREWALL_RE.test(text) || DONE_RE.test(text) || block.lines.length >= MAX_BLOCK) {
          this.block = null;
        } else {
          block.lines.push(text);
          if (!block.host) {
            const m = HOST_MENTION_RE.exec(text);
            if (m) this.attachError(block, m[1]);
          }
          return;
        }
      } else if (block.kind === "firewall") {
        if (this.firewallLine(block, text)) return;
        this.block = null;
      } else if (block.kind === "balancer") {
        if (/^\s+\S/.test(text)) {
          log.balancer.push(text);
          if (/WARNING:/.test(text)) log.balancerWarnings++;
          return;
        }
        this.block = null;
      } else if (block.kind === "done") {
        if (/^\s+\S/.test(text)) {
          log.done.push(text);
          const url = /^\s+(?:[A-Z]+|\*|url:)\s+(https?:\/\/\S+)/.exec(text);
          if (url) this.endpoint(url[1]);
          return;
        }
        this.block = null;
      }
    }

    // Diagnostics (terraform's and pskit's own "Error: ..."); warnings stay in the current step's lines.
    if (text.startsWith("Error: ")) {
      const b: Extract<Block, { kind: "error" }> = { kind: "error", lines: [text], host: null };
      this.block = b;
      log.errors.push(b.lines);
      const m = HOST_MENTION_RE.exec(text);
      if (m) this.attachError(b, m[1]);
      return;
    }

    // Terraform resource lines.
    if (log.stage >= 1) {
      const m = RESOURCE_RE.exec(text);
      if (m) {
        this.resourceLine(text, m[1], m[2] || "", m[3]);
        return;
      }
    }

    if (log.stage === 0 && PLAN_START_RE.test(text)) {
      log.stage = 1;
      log.plan.push(text);
      return;
    }
    if (log.stage <= 1 && /^(Plan: \d+ to add|No changes\.)/.test(text)) {
      log.stage = 1;
      log.planSummary = text.trim();
      log.plan.push(text);
      return;
    }
    if (APPLY_DONE_RE.test(text)) {
      log.applySummary = text.trim();
      log.apply.push(text);
      if (log.stage < 3) log.stage = 3;
      return;
    }
    const fw = FIREWALL_RE.exec(text);
    if (fw) {
      if (log.stage < 3) log.stage = 3;
      this.block = { kind: "firewall", section: null, title: fw[1].trim(), server: null, ufw: false };
      return;
    }
    if (log.stage >= 1 && (BALANCER_HEAD_RE.test(text) || BALANCER_LINE_RE.test(text))) {
      if (log.stage < 3) log.stage = 3;
      log.balancer.push(text);
      if (/WARNING:/.test(text)) log.balancerWarnings++;
      if (!/^\s/.test(text)) this.block = { kind: "balancer" };
      return;
    }
    if (DONE_RE.test(text)) {
      log.stage = 4;
      log.done.push(text);
      return;
    }
    const ep = /^endpoint: (\S+)/.exec(text);
    if (ep && log.stage >= 3) {
      log.stage = 4;
      this.endpoint(ep[1]);
      log.done.push(text);
      return;
    }
    if (log.stage === 4 && /^(functions|workflows):\s*$/.test(text)) {
      log.done.push(text);
      this.block = { kind: "done" };
      return;
    }
    if (log.stage < 2 && /^Running terraform (apply|destroy)/.test(text)) log.stage = 1;
    this.generic(text);
  }

  private attachError(block: Extract<Block, { kind: "error" }>, key: string): void {
    const h = this.host(key);
    block.host = h;
    h.errorBlock = block.lines;
    h.status = "failed";
    const i = this.log.errors.indexOf(block.lines);
    if (i >= 0) this.log.errors.splice(i, 1);
  }

  private resourceLine(text: string, address: string, stream: string, msg: string): void {
    const log = this.log;
    const hm = HOST_RE.exec(address);
    const refresh = !stream && /^(Refreshing state|Reading\.\.\.|Read complete)/.test(msg);
    if (refresh) {
      log.plan.push(text);
      return;
    }
    if (log.stage < 2) log.stage = 2;
    if (!hm) {
      log.apply.push(text);
      return;
    }
    const h = this.host(hm[1]);
    h.lines.push(text);
    if (stream) {
      if (/did not become healthy/.test(msg)) {
        h.error.push(msg.trim());
        h.status = "failed";
        this.tailOf.add(h.key);
        return;
      }
      const tail = /^\s*\| ?(.*)$/.exec(msg);
      if (tail && this.tailOf.has(h.key)) {
        h.tail.push(tail[1]);
        return;
      }
      this.tailOf.delete(h.key);
      return;
    }
    let m: RegExpExecArray | null;
    if ((m = /^(Creating|Modifying|Destroying)\.\.\./.exec(msg))) {
      h.action = m[1] === "Creating" ? "create" : m[1] === "Modifying" ? "modify" : "destroy";
      if (h.status !== "failed") h.status = "running";
      h.detail = "";
    } else if ((m = /^Still (creating|modifying|destroying)\.\.\. \[(.+?) elapsed\]/.exec(msg))) {
      if (h.status !== "failed") h.status = "running";
      h.detail = `${m[2]} elapsed`;
    } else if ((m = /^(Creation|Modifications|Destruction) complete after (\S+)/.exec(msg))) {
      if (h.status !== "failed") h.status = "done";
      h.detail = `${m[1]} complete after ${m[2]}`;
    } else if ((m = /^(Creation|Modifications|Destruction) errored after (\S+)/.exec(msg))) {
      h.status = "failed";
      h.detail = `${m[1]} failed after ${m[2]}`;
    }
  }

  /** One line of a `Firewall - ...` block; false when the block has ended. */
  private firewallLine(block: Extract<Block, { kind: "firewall" }>, text: string): boolean {
    if (!/^\s{2}\S|^\s{4,}\S/.test(text)) return false;
    if (/^ {6,}\S/.test(text) && block.ufw && block.section) {
      block.section.ufw.push(text.trim());
      return true;
    }
    const ufw = /^ {4}ufw on (.+):\s*$/.exec(text);
    if (ufw && block.section) {
      block.ufw = true;
      return true;
    }
    const rule = /^ {4}\[\s*(REQUIRED|NEEDED|optional)\s*\]\s+(.*)$/.exec(text);
    if (rule && block.section) {
      block.ufw = false;
      block.section.rules.push(parseRule(LEVELS[rule[1]] || "optional", rule[2]));
      return true;
    }
    const server = /^ {2}(\S.*?)\s*$/.exec(text);
    if (server) {
      block.ufw = false;
      let entry = this.log.firewall.find((s) => s.server === server[1]);
      if (!entry) {
        entry = { server: server[1], sections: [] };
        this.log.firewall.push(entry);
      }
      block.server = entry;
      block.section = { title: block.title, rules: [], ufw: [] };
      entry.sections.push(block.section);
      return true;
    }
    if (block.section) {
      block.section.rules.push(parseRule("optional", text.trim()));
      return true;
    }
    return false;
  }
}

/** `inbound  TCP 8080         from a, b  - why` -> its parts. */
export function parseRule(level: FirewallLevel, text: string): FirewallRule {
  const m = /^(inbound|outbound)\s+(\S+ \S+)\s+((?:from|to) .*?)\s+- (.*)$/.exec(text.trim());
  if (!m) return { level, direction: "", port: "", peer: "", why: "", text: text.trim() };
  return { level, direction: m[1], port: m[2], peer: m[3], why: m[4], text: text.trim() };
}

/** Parse a whole output at once (tests, small jobs). */
export function parseDeployLog(lines: string[]): DeployLog {
  const p = new DeployLogParser();
  p.pushText(lines);
  return p.snapshot();
}

// ----------------------------------------------------------------------------------------------- statuses

export type JobState = JobStatus | "idle";

function finished(job: JobState): StepStatus {
  return job === "succeeded" ? "done" : job === "cancelled" ? "cancelled" : job === "running" || job === "idle" ? "running" : "failed";
}

/** Status of the pre-apply steps: 0 check & build, 1 terraform plan. */
export function stageStatus(log: DeployLog, stage: 0 | 1, job: JobState): StepStatus {
  if (log.stage > stage) return "done";
  if (log.stage < stage) return job === "succeeded" ? "done" : "waiting";
  return finished(job);
}

/** A host card's status: its own, completed by how the job ended (untouched hosts are unchanged). */
export function hostStatus(host: HostStep | undefined, log: DeployLog, job: JobState): StepStatus {
  const own = host?.status || "waiting";
  if (own === "failed" || own === "done") return own;
  if (own === "running") return job === "running" ? "running" : job === "succeeded" ? "done" : job === "cancelled" ? "cancelled" : "failed";
  // Never mentioned by terraform: nothing to change once the apply is over.
  if (log.stage >= 3 || job === "succeeded") return "done";
  return job === "running" && log.stage >= 2 ? "waiting" : job === "cancelled" ? "cancelled" : "waiting";
}

/** Status of the apply step for output that is not a host's (or failures no host claims). */
export function applyStatus(log: DeployLog, job: JobState): StepStatus {
  if (log.stage > 2) return "done";
  if (log.stage < 2) return job === "succeeded" ? "done" : "waiting";
  return finished(job);
}

/** Load balancer / firewall steps (shown only when they printed something). */
export function afterStatus(log: DeployLog, which: "balancer" | "firewall", job: JobState): StepStatus {
  if (log.stage > 3 || job === "succeeded") return "done";
  if (job === "running") {
    // The load balancer is set up before the firewall rules are printed.
    if (which === "balancer" && log.firewall.length) return "done";
    return "running";
  }
  if (which === "balancer" && log.firewall.length) return "done";
  return finished(job);
}

export function doneStatus(log: DeployLog, job: JobState): StepStatus {
  if (job === "succeeded") return "done";
  if (log.stage < 4) return job === "running" ? "waiting" : job === "cancelled" ? "cancelled" : "waiting";
  return finished(job);
}
