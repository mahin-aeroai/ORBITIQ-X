"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAgentTasks, type AgentTaskStatus } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  completed:  "#34d399",
  running:    "#818cf8",
  pending:    "#fbbf24",
  failed:     "#ef4444",
  cancelled:  "#64748b",
};

const SPECIALISTS = [
  { id: "orbital_analyst",    label: "Orbital Analyst",    icon: "◈", desc: "SGP4 propagation · conjunction geometry · TCA prediction" },
  { id: "conjunction_risk",   label: "Risk Assessor",      icon: "⚠", desc: "Pc computation · CDM analysis · maneuver recommendation" },
  { id: "debris_expert",      label: "Debris Expert",      icon: "◎", desc: "Debris catalog · reentry prediction · fragmentation" },
  { id: "mission_planner",    label: "Mission Planner",    icon: "⊕", desc: "Launch windows · orbit transfers · delta-V budget" },
  { id: "space_weather",      label: "Space Weather",      icon: "◑", desc: "Kp/F10.7 monitoring · drag prediction · SEP alerts" },
  { id: "knowledge_graph",    label: "Graph Navigator",    icon: "◉", desc: "Neo4j traversal · operator intelligence · constellation mapping" },
  { id: "rag_retriever",      label: "RAG Retriever",      icon: "◫", desc: "185-chunk corpus · 12 aerospace domains · vector search" },
];

function AgentCard({ agent }: { agent: typeof SPECIALISTS[0] }) {
  return (
    <div className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] p-3 transition-colors hover:border-[var(--color-accent-indigo)] hover:bg-[var(--color-space-elevated)]">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 font-mono text-base text-[var(--color-accent-indigo-bright)]">{agent.icon}</span>
        <div className="min-w-0">
          <div className="font-mono text-[10px] font-semibold text-[var(--color-text-primary)]">{agent.label}</div>
          <div className="mt-0.5 font-mono text-[9px] leading-relaxed text-[var(--color-text-tertiary)]">{agent.desc}</div>
        </div>
        <div className="ml-auto flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-[rgba(52,211,153,0.15)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#34d399]" />
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task }: { task: AgentTaskStatus }) {
  const [open, setOpen] = useState(false);
  const color = STATUS_COLOR[task.status] ?? "#64748b";
  const duration = task.completed_at && task.started_at
    ? ((new Date(task.completed_at).getTime() - new Date(task.started_at).getTime()) / 1000).toFixed(1) + "s"
    : task.status === "running" ? "running…" : "—";

  return (
    <div className="border-b border-[var(--color-space-border)] transition-colors hover:bg-[var(--color-space-surface)]">
      <button onClick={() => setOpen(o => !o)} className="grid w-full grid-cols-[80px_1fr_90px_70px_60px] items-center gap-2 px-4 py-2 text-left">
        <span className="rounded border px-1.5 py-px font-mono text-[8px] font-semibold uppercase"
          style={{ color, borderColor: `${color}50`, backgroundColor: `${color}15` }}>
          {task.status}
        </span>
        <span className="truncate font-mono text-[10px] text-[var(--color-text-primary)]" title={task.query}>
          {task.query ?? task.task_type ?? "—"}
        </span>
        <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">{duration}</span>
        <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">
          {task.agents_used?.length ?? "—"} agents
        </span>
        <span className="text-right font-mono text-[9px] text-[var(--color-text-tertiary)]">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-8 py-3 space-y-2">
          {task.query && (
            <div>
              <div className="font-mono text-[8px] text-[var(--color-text-tertiary)] mb-1">QUERY</div>
              <div className="font-mono text-[10px] text-[var(--color-text-primary)]">{task.query}</div>
            </div>
          )}
          {task.result && (
            <div>
              <div className="font-mono text-[8px] text-[var(--color-text-tertiary)] mb-1">RESULT PREVIEW</div>
              <div className="font-mono text-[10px] leading-relaxed text-[var(--color-text-secondary)] line-clamp-3">
                {typeof task.result === "string" ? task.result : JSON.stringify(task.result).slice(0, 200)}
              </div>
            </div>
          )}
          {task.agents_used && (
            <div className="flex flex-wrap gap-1">
              {task.agents_used.map((a: string) => (
                <span key={a} className="rounded border border-[var(--color-accent-indigo)] bg-[rgba(99,102,241,0.1)] px-1.5 py-px font-mono text-[8px] text-[#818cf8]">{a}</span>
              ))}
            </div>
          )}
          <div className="flex gap-4">
            {[["Task ID", task.task_id ?? task.id],["Started", task.started_at ? new Date(task.started_at).toLocaleTimeString() : "—"],["Completed", task.completed_at ? new Date(task.completed_at).toLocaleTimeString() : "—"]].map(([k,v]) => (
              <div key={k}>
                <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{k}</div>
                <div className="font-mono text-[9px] text-[var(--color-text-data)]">{String(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentsPage() {
  const { data: tasks, isLoading, refetch } = useQuery({
    queryKey: ["agent-tasks"],
    queryFn: () => fetchAgentTasks(50),
    refetchInterval: 15_000,
  });

  const taskList = Array.isArray(tasks) ? tasks : [];
  const running   = taskList.filter(t => t.status === "running").length;
  const completed = taskList.filter(t => t.status === "completed").length;
  const failed    = taskList.filter(t => t.status === "failed").length;

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">
      {/* Header */}
      <div className="shrink-0 border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-[var(--color-accent-indigo-bright)]">◎</span>
              <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">Agent Activity</h1>
            </div>
            <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
              7 specialist agents · multi-agent aerospace intelligence system
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => refetch()} className="rounded border border-[var(--color-space-border)] px-2 py-0.5 font-mono text-[9px] text-[var(--color-text-secondary)] hover:border-[var(--color-accent-indigo)] transition-colors">⟳ Refresh</button>
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
            <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
          </div>
        </div>
        {/* KPIs */}
        <div className="mt-3 grid grid-cols-4 gap-3">
          {[
            { label: "Specialists", value: 7, color: "#818cf8" },
            { label: "Running",     value: running,   color: "#818cf8" },
            { label: "Completed",   value: completed, color: "#34d399" },
            { label: "Failed",      value: failed,    color: failed > 0 ? "#ef4444" : "var(--color-text-tertiary)" },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-3 py-2">
              <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{label}</div>
              <div className="font-mono text-base font-bold tabular-nums" style={{ color }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: specialists */}
        <div className="w-64 shrink-0 overflow-y-auto border-r border-[var(--color-space-border)] bg-[var(--color-space-midnight)] p-3 space-y-2">
          <div className="font-mono text-[8px] tracking-widest text-[var(--color-text-tertiary)] px-1 pb-1">SPECIALIST ROSTER</div>
          {SPECIALISTS.map(a => <AgentCard key={a.id} agent={a} />)}
        </div>

        {/* Right: task history */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="grid grid-cols-[80px_1fr_90px_70px_60px] shrink-0 items-center gap-2 border-b border-[var(--color-space-border-strong)] bg-[var(--color-space-navy)] px-4 py-1">
            {["STATUS","QUERY","DURATION","AGENTS",""].map(h => (
              <span key={h} className="font-mono text-[8px] tracking-[0.1em] text-[var(--color-text-tertiary)]">{h}</span>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex h-32 items-center justify-center gap-2">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#818cf8]" />
                <span className="font-mono text-[10px] text-[var(--color-text-tertiary)]">Loading agent tasks…</span>
              </div>
            ) : taskList.length === 0 ? (
              <div className="flex h-48 flex-col items-center justify-center gap-2">
                <span className="font-mono text-2xl text-[var(--color-text-tertiary)]">◎</span>
                <span className="font-mono text-xs text-[var(--color-text-secondary)]">No recent agent tasks</span>
                <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">Submit a query in AI Workspace to activate agents</span>
              </div>
            ) : (
              taskList.map((t, i) => <TaskRow key={t.task_id ?? t.id ?? i} task={t} />)
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
