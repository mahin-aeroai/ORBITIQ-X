"use client";
/**
 * ORBITIQ-X — AgentActivityFeed
 * ===============================
 * Right panel bottom: recent multi-agent task activity.
 *
 * Data source: GET /api/v1/agents/tasks?limit={maxItems}
 * Refresh:     20 seconds
 *
 * Shows each task with:
 *   • Status badge (color-coded)
 *   • Truncated query
 *   • Agents invoked
 *   • Latency / completion time
 */

import { useQuery } from "@tanstack/react-query";
import { fetchAgentTasks, type AgentTaskStatus } from "@/lib/api";

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  completed:     "var(--color-accent-green-bright)",
  running:       "var(--color-accent-indigo-bright)",
  queued:        "var(--color-text-secondary)",
  waiting_human: "var(--color-accent-amber)",
  failed:        "var(--color-accent-red-bright)",
  cancelled:     "var(--color-text-tertiary)",
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "var(--color-text-tertiary)";
  const isRunning = status === "running";
  return (
    <span className="flex items-center gap-1">
      <span
        className={["inline-block h-1.5 w-1.5 rounded-full", isRunning ? "animate-pulse" : ""].join(" ")}
        style={{ backgroundColor: color }}
        aria-hidden="true"
      />
      <span className="font-mono text-[9px] uppercase" style={{ color }}>
        {status.replace("_", " ")}
      </span>
    </span>
  );
}

// ─── Agent chip list ──────────────────────────────────────────────────────────

const AGENT_ABBREVS: Record<string, string> = {
  orbital_dynamics:     "ORB",
  conjunction_analysis: "CDM",
  space_debris:         "DEB",
  mission_planning:     "MSN",
  space_weather:        "WX",
  aerospace_research:   "RAG",
  satellite_intelligence: "SAT",
  ORCHESTRATOR:         "SUP",
};

function AgentChips({ agents }: { agents: string[] }) {
  if (!agents || agents.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {agents.slice(0, 4).map((a) => (
        <span
          key={a}
          className="rounded border border-[var(--color-space-border-strong)] px-1 py-0.5 font-mono text-[8px] text-space-muted"
          title={a}
        >
          {AGENT_ABBREVS[a] ?? a.slice(0, 3).toUpperCase()}
        </span>
      ))}
      {agents.length > 4 && (
        <span className="font-mono text-[8px] text-space-muted">+{agents.length - 4}</span>
      )}
    </div>
  );
}

// ─── Task row ─────────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: AgentTaskStatus }) {
  const latencyStr =
    task.latency_ms !== null && task.latency_ms !== undefined
      ? `${(task.latency_ms / 1000).toFixed(1)}s`
      : null;

  const timeStr = task.completed_at
    ? new Date(task.completed_at).toISOString().slice(11, 19) + " UTC"
    : task.submitted_at
    ? new Date(task.submitted_at).toISOString().slice(11, 19) + " UTC"
    : null;

  return (
    <div
      className="border-b border-space-border px-4 py-2.5 transition-colors hover:bg-space-surface"
      role="listitem"
    >
      {/* Status + latency */}
      <div className="mb-1 flex items-center justify-between">
        <StatusBadge status={task.status} />
        <span className="font-mono text-[9px] text-space-muted">
          {latencyStr ?? timeStr ?? "—"}
        </span>
      </div>

      {/* Query */}
      <p
        className="mb-0.5 truncate text-[11px] text-space-text"
        title={task.query}
      >
        {task.query}
      </p>

      {/* Agents */}
      <AgentChips agents={task.agents_invoked ?? []} />

      {/* Error message */}
      {task.status === "failed" && task.error_message && (
        <p className="mt-1 truncate font-mono text-[9px] text-[var(--color-accent-red)]">
          {task.error_message.slice(0, 80)}
        </p>
      )}
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8">
      <span className="section-label text-space-muted">NO RECENT AGENT TASKS</span>
      <span className="font-mono text-[10px] text-space-muted">
        Submit a query to activate agents
      </span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface AgentActivityFeedProps {
  maxItems?: number;
}

export function AgentActivityFeed({ maxItems = 5 }: AgentActivityFeedProps) {
  const { data, isLoading, isError } = useQuery<AgentTaskStatus[], Error>({
    queryKey:        ["agent-tasks", maxItems],
    queryFn:         () => fetchAgentTasks(maxItems),
    refetchInterval: 20_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2 px-4 py-2" role="status" aria-label="Loading agent activity">
        {Array.from({ length: maxItems }).map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded bg-space-surface" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="px-4 py-4">
        <span className="font-mono text-xs text-[var(--color-accent-amber)]">
          ⚠ AGENT FEED UNAVAILABLE
        </span>
      </div>
    );
  }

  const tasks = data ?? [];

  return (
    <div role="list" aria-label="Agent activity feed">
      {tasks.length === 0 ? (
        <EmptyState />
      ) : (
        tasks.map((task) => <TaskRow key={task.task_id} task={task} />)
      )}
    </div>
  );
}
