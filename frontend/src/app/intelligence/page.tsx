"use client";
/**
 * ORBITIQ-X — AI Intelligence Workspace (v0.4.0)
 * =================================================
 * GraphRAG pipeline: embed → vector → graph → Claude synthesis.
 * Avg latency 28s — pipeline animation stays active during full fetch.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { getApiAccessToken } from "@/lib/api";

const V1 = "/api/v1";

interface Message {
  id:          string;
  role:        "user" | "assistant";
  content:     string;
  latency?:    number;
  mode?:       string;
  confidence?: number;
  timestamp:   Date;
  error?:      boolean;
}

const EXAMPLE_QUERIES = [
  "How does SGP4 propagation work and what are its accuracy limitations?",
  "What is the collision probability threshold for conjunction avoidance?",
  "Compare debris risk in LEO versus GEO and explain Kessler syndrome.",
  "Describe Starlink orbital shells and autonomous collision avoidance.",
  "What does a CCSDS Conjunction Data Message contain?",
  "How does the J2 zonal harmonic affect orbital elements?",
  "What are the IADC space debris mitigation guidelines?",
];

const PIPELINE_STEPS = [
  { id: "embed",  label: "Embedding query",      icon: "◈", desc: "all-MiniLM-L6-v2 · 384-dim",     ms: 200  },
  { id: "vector", label: "Vector retrieval",     icon: "◑", desc: "Qdrant · 185 aerospace chunks",   ms: 1500 },
  { id: "graph",  label: "Knowledge graph",      icon: "◉", desc: "Neo4j · 29,248 satellite nodes",  ms: 3000 },
  { id: "claude", label: "Claude synthesizing",  icon: "⊕", desc: "claude-sonnet-4-6 · streaming",  ms: null },
];

// Markdown renderer
function AnswerText({ content }: { content: string }) {
  return (
    <div className="space-y-1.5">
      {content.split("\n").map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />;
        if (line.startsWith("## ")) return (
          <h3 key={i} className="mt-3 font-display text-[13px] font-semibold text-[var(--color-text-primary)] first:mt-0">
            {line.slice(3)}
          </h3>
        );
        if (line.startsWith("### ")) return (
          <h4 key={i} className="mt-2 font-mono text-[10px] font-semibold uppercase tracking-wider text-[var(--color-accent-indigo-bright)]">
            {line.slice(4)}
          </h4>
        );
        if (line.startsWith("---")) return (
          <div key={i} className="my-2 border-t border-[var(--color-space-border)]" />
        );
        if (line.startsWith("- ") || line.startsWith("• ")) return (
          <div key={i} className="flex gap-2">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[var(--color-accent-indigo)]" />
            <span className="font-body text-[12px] leading-relaxed text-[var(--color-text-primary)]">
              {line.slice(2)}
            </span>
          </div>
        );
        if (line.startsWith("> ")) return (
          <blockquote key={i} className="border-l-2 border-[var(--color-accent-indigo)] pl-3 font-mono text-[10px] italic text-[var(--color-text-secondary)]">
            {line.slice(2)}
          </blockquote>
        );
        // Inline bold
        const parts = line.split(/\*\*(.*?)\*\*/g);
        return (
          <p key={i} className="font-body text-[12px] leading-relaxed text-[var(--color-text-primary)]">
            {parts.map((p, j) => j % 2 === 1
              ? <strong key={j} className="font-semibold">{p}</strong>
              : p
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function IntelligencePage() {
  const [messages,        setMessages]        = useState<Message[]>([]);
  const [input,           setInput]           = useState("");
  const [loading,         setLoading]         = useState(false);
  const [activeStepIdx,   setActiveStepIdx]   = useState(-1);
  const [completedSteps,  setCompletedSteps]  = useState<Set<number>>(new Set());
  const [elapsedMs,       setElapsedMs]       = useState(0);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const inputRef    = useRef<HTMLTextAreaElement>(null);
  const timerRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendQuery = useCallback(async (query: string) => {
    if (!query.trim() || loading) return;

    const trimmed = query.trim();
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: "user", content: trimmed, timestamp: new Date() }]);
    setInput("");
    setLoading(true);
    setActiveStepIdx(0);
    setCompletedSteps(new Set());
    setElapsedMs(0);

    // Start elapsed timer
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startTimeRef.current);
    }, 500);

    // Animate first 3 steps with known timings
    const animate = async () => {
      for (let i = 0; i < PIPELINE_STEPS.length - 1; i++) {
        const step = PIPELINE_STEPS[i];
        setActiveStepIdx(i);
        await new Promise(r => setTimeout(r, step.ms ?? 1000));
        setCompletedSteps(prev => new Set([...prev, i]));
      }
      // Last step (Claude) stays active until response
      setActiveStepIdx(PIPELINE_STEPS.length - 1);
    };

    animate();

    const t0 = Date.now();
    try {
      const token = getApiAccessToken();
      const res = await fetch(`${V1}/rag/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: trimmed }),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => `HTTP ${res.status}`);
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 120)}`);
      }

      const data = await res.json();
      const latency = Date.now() - t0;

      setCompletedSteps(new Set([0, 1, 2, 3]));
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: "assistant",
        content: data.answer ?? data.response ?? "No answer returned.",
        latency, mode: data.mode, confidence: data.confidence,
        timestamp: new Date(),
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: "assistant", error: true,
        content: `Query failed: ${e instanceof Error ? e.message : "Unknown error"}`,
        timestamp: new Date(),
      }]);
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setLoading(false);
      setActiveStepIdx(-1);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [loading]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQuery(input); }
  };

  const formatElapsed = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-base text-[var(--color-accent-indigo-bright)]">◈</span>
            <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">AI Intelligence Workspace</h1>
          </div>
          <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
            GraphRAG · 185 chunks · 29,248 Neo4j nodes · claude-sonnet-4-6 · avg 28s
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
          <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
        </div>
      </div>

      {/* ── Pipeline visualization ───────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-1 border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        {PIPELINE_STEPS.map((step, i) => {
          const isActive    = loading && activeStepIdx === i;
          const isCompleted = completedSteps.has(i);
          const isPending   = loading && activeStepIdx < i && !isCompleted;
          return (
            <div key={step.id} className="flex items-center">
              <div className="flex items-center gap-1.5 rounded px-2 py-1 transition-all duration-300"
                style={{
                  backgroundColor: isActive ? "rgba(99,102,241,0.15)" : "transparent",
                  color: isActive ? "#818cf8" : isCompleted ? "#34d399" : isPending ? "#475569" : "var(--color-text-tertiary)",
                }}>
                <span className={`text-sm ${isActive ? "animate-pulse" : ""}`}>{step.icon}</span>
                <div className="hidden sm:block">
                  <div className="font-mono text-[9px] font-semibold">{step.label}</div>
                  <div className="font-mono text-[8px] opacity-60">{step.desc}</div>
                </div>
                {isCompleted && <span className="text-[9px] text-[#34d399]">✓</span>}
                {isActive && step.id === "claude" && loading && (
                  <span className="font-mono text-[9px] text-[#818cf8]">{formatElapsed(elapsedMs)}</span>
                )}
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <span className="mx-1 font-mono text-xs"
                  style={{ color: isCompleted ? "#34d399" : "var(--color-space-border-strong)" }}>→</span>
              )}
            </div>
          );
        })}
        {loading && (
          <span className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">
            {formatElapsed(elapsedMs)} elapsed
          </span>
        )}
      </div>

      {/* ── Messages ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">

        {messages.length === 0 && !loading && (
          <div className="flex h-full flex-col items-center justify-center gap-6 py-8">
            <div className="text-center">
              <div className="mb-3 font-mono text-4xl text-[var(--color-accent-indigo)]">◈</div>
              <h2 className="mb-1 font-display text-base font-semibold text-[var(--color-text-primary)]">
                Aerospace Intelligence Ready
              </h2>
              <p className="max-w-sm font-mono text-[10px] leading-relaxed text-[var(--color-text-tertiary)]">
                Ask about orbital mechanics, conjunction analysis, debris mitigation, spacecraft systems, or space missions.
              </p>
              <p className="mt-1 font-mono text-[9px] text-[var(--color-accent-amber)]">
                Note: queries take ~28 seconds (Claude synthesis)
              </p>
            </div>

            <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
              {EXAMPLE_QUERIES.map((q, i) => (
                <button key={i} onClick={() => sendQuery(q)}
                  className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-2.5 text-left font-mono text-[10px] leading-relaxed text-[var(--color-text-secondary)] transition-all hover:border-[#6366f1] hover:bg-[rgba(99,102,241,0.08)] hover:text-[var(--color-text-primary)]">
                  {q}
                </button>
              ))}
            </div>

            <div className="flex gap-6 rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-5 py-3">
              {[
                { label: "Corpus chunks", value: "185",    color: "#818cf8" },
                { label: "Domains",       value: "12",     color: "#34d399" },
                { label: "Graph nodes",   value: "29,248", color: "#fbbf24" },
                { label: "Retrieval",     value: "100%",   color: "#34d399" },
              ].map(({ label, value, color }) => (
                <div key={label} className="text-center">
                  <div className="font-mono text-sm font-bold tabular-nums" style={{ color }}>{value}</div>
                  <div className="font-mono text-[8px] text-[var(--color-text-tertiary)]">{label}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            {msg.role === "assistant" && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[#6366f1] bg-[rgba(99,102,241,0.12)] font-mono text-xs text-[#818cf8]">◈</div>
            )}
            <div className={`max-w-2xl rounded-lg border px-4 py-3 ${
              msg.role === "user"
                ? "border-[var(--color-space-border-strong)] bg-[var(--color-space-elevated)]"
                : msg.error
                ? "border-[#ef4444] bg-[rgba(239,68,68,0.05)]"
                : "border-[var(--color-space-border)] bg-[var(--color-space-navy)]"
            }`}>
              {msg.role === "user"
                ? <p className="font-body text-[12px] leading-relaxed text-[var(--color-text-primary)]">{msg.content}</p>
                : <AnswerText content={msg.content} />
              }
              {msg.role === "assistant" && !msg.error && (
                <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-[var(--color-space-border)] pt-2">
                  {msg.latency != null && (
                    <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">⏱ {(msg.latency / 1000).toFixed(1)}s</span>
                  )}
                  {msg.mode && (
                    <span className="rounded border border-[#6366f1] bg-[rgba(99,102,241,0.1)] px-1.5 py-0.5 font-mono text-[8px] text-[#818cf8]">{msg.mode}</span>
                  )}
                  {msg.confidence != null && (
                    <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">conf {(msg.confidence * 100).toFixed(0)}%</span>
                  )}
                  <span className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">{msg.timestamp.toLocaleTimeString()}</span>
                </div>
              )}
            </div>
            {msg.role === "user" && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-space-border-strong)] bg-[var(--color-space-elevated)] font-mono text-xs text-[var(--color-text-secondary)]">⊙</div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[#6366f1] bg-[rgba(99,102,241,0.12)] font-mono text-xs text-[#818cf8] animate-pulse">◈</div>
            <div className="rounded-lg border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[11px] text-[var(--color-text-secondary)]">
                  {activeStepIdx >= 0
                    ? PIPELINE_STEPS[activeStepIdx].label
                    : "Processing"}…
                </span>
                {[0, 150, 300].map(d => (
                  <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6366f1]"
                    style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
              {elapsedMs > 5000 && (
                <p className="mt-1 font-mono text-[9px] text-[var(--color-text-tertiary)]">
                  Claude is synthesizing across 185 corpus chunks + graph context…
                </p>
              )}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ────────────────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-4 py-3">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about orbital mechanics, conjunction analysis, spacecraft systems… (Enter to send)"
            rows={2}
            disabled={loading}
            className="flex-1 resize-none rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-2 font-mono text-[11px] leading-relaxed text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[#6366f1] transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => sendQuery(input)}
            disabled={loading || !input.trim()}
            className="self-end rounded border border-[#6366f1] bg-[rgba(99,102,241,0.12)] px-5 py-2 font-mono text-[11px] font-semibold text-[#818cf8] transition-all hover:bg-[#6366f1] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? `${formatElapsed(elapsedMs)}` : "Send ⏎"}
          </button>
        </div>
        <p className="mt-1.5 font-mono text-[8px] text-[var(--color-text-tertiary)]">
          Vector retrieval (185 chunks, 12 domains) · Knowledge Graph (29,248 nodes) · Claude Sonnet 4.6 · avg 28s latency
        </p>
      </div>
    </div>
  );
}
