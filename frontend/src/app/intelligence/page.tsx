"use client";
/**
 * ORBITIQ-X — AI Intelligence Workspace (v0.4.0)
 * =================================================
 * Conversational aerospace intelligence interface.
 * Full GraphRAG pipeline: query → embed → vector → graph → agents → Claude → answer.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { getApiAccessToken } from "@/lib/api";

const V1 = "/api/v1";

interface Message {
  id:         string;
  role:       "user" | "assistant";
  content:    string;
  latency?:   number;
  mode?:      string;
  confidence?: number;
  timestamp:  Date;
  error?:     boolean;
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
  { id: "embed",  label: "Embed Query",       icon: "◈", desc: "all-MiniLM-L6-v2 · 384-dim" },
  { id: "vector", label: "Vector Retrieval",  icon: "◑", desc: "Qdrant · 185 chunks" },
  { id: "graph",  label: "Knowledge Graph",   icon: "◉", desc: "Neo4j · 29,248 nodes" },
  { id: "synth",  label: "Claude Synthesis",  icon: "⊕", desc: "claude-sonnet-4-6" },
];

// Simple markdown-like renderer for answer text
function AnswerText({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div className="space-y-1">
      {lines.map((line, i) => {
        if (line.startsWith("## ")) return (
          <h3 key={i} className="mt-3 font-display text-[13px] font-semibold text-[var(--color-text-primary)] first:mt-0">
            {line.slice(3)}
          </h3>
        );
        if (line.startsWith("### ")) return (
          <h4 key={i} className="mt-2 font-display text-[11px] font-semibold text-[var(--color-accent-indigo-bright)]">
            {line.slice(4)}
          </h4>
        );
        if (line.startsWith("**") && line.endsWith("**") && line.length > 4) return (
          <p key={i} className="font-display text-[11px] font-semibold text-[var(--color-text-primary)]">
            {line.slice(2, -2)}
          </p>
        );
        if (line.startsWith("- ") || line.startsWith("• ")) return (
          <p key={i} className="flex gap-2 font-body text-[11px] leading-relaxed text-[var(--color-text-primary)]">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-[var(--color-accent-indigo)]" />
            <span>{line.slice(2)}</span>
          </p>
        );
        if (line.startsWith("> ")) return (
          <blockquote key={i} className="border-l-2 border-[var(--color-accent-indigo)] pl-3 font-mono text-[10px] italic text-[var(--color-text-secondary)]">
            {line.slice(2)}
          </blockquote>
        );
        if (line.startsWith("---")) return (
          <div key={i} className="my-2 border-t border-[var(--color-space-border)]" />
        );
        if (!line.trim()) return <div key={i} className="h-1" />;
        // Bold inline text
        const parts = line.split(/\*\*(.*?)\*\*/g);
        return (
          <p key={i} className="font-body text-[12px] leading-relaxed text-[var(--color-text-primary)]">
            {parts.map((part, j) =>
              j % 2 === 1
                ? <strong key={j} className="font-semibold text-[var(--color-text-primary)]">{part}</strong>
                : part
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function IntelligencePage() {
  const [messages,    setMessages]    = useState<Message[]>([]);
  const [input,       setInput]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [activeStep,  setActiveStep]  = useState<string | null>(null);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendQuery = useCallback(async (query: string) => {
    if (!query.trim() || loading) return;

    setMessages(prev => [...prev, {
      id: crypto.randomUUID(), role: "user", content: query.trim(), timestamp: new Date(),
    }]);
    setInput("");
    setLoading(true);
    setCompletedSteps(new Set());

    // Animate through pipeline steps
    for (const step of PIPELINE_STEPS) {
      setActiveStep(step.id);
      await new Promise(r => setTimeout(r, 800));
      setCompletedSteps(prev => new Set([...prev, step.id]));
    }
    setActiveStep(null);

    const t0 = Date.now();
    try {
      const token = getApiAccessToken();
      const res = await fetch(`${V1}/rag/query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const latency = Date.now() - t0;

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
      setLoading(false);
      setCompletedSteps(new Set());
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [loading]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery(input);
    }
  };

  return (
    <div className="flex h-full flex-col bg-[var(--color-space-deep)]">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--color-space-border)] bg-[var(--color-space-midnight)] px-6 py-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-base text-[var(--color-accent-indigo-bright)]">◈</span>
            <h1 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              AI Intelligence Workspace
            </h1>
          </div>
          <p className="mt-0.5 font-mono text-[9px] text-[var(--color-text-tertiary)]">
            GraphRAG · 185 chunks · 29,248 Neo4j nodes · claude-sonnet-4-6 · full_graphrag mode
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-accent-green-bright)]" />
          <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">LIVE</span>
        </div>
      </div>

      {/* ── Pipeline visualization ───────────────────────────────────────── */}
      <div className="flex shrink-0 items-center border-b border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2">
        {PIPELINE_STEPS.map((step, i) => {
          const isActive    = activeStep === step.id;
          const isCompleted = completedSteps.has(step.id);
          return (
            <div key={step.id} className="flex items-center">
              <div
                className="flex items-center gap-1.5 rounded px-2 py-1 transition-all duration-300"
                style={{
                  backgroundColor: isActive ? "var(--color-accent-indigo-glow)" : "transparent",
                  color: isActive
                    ? "var(--color-accent-indigo-bright)"
                    : isCompleted
                    ? "var(--color-accent-green-bright)"
                    : "var(--color-text-tertiary)",
                }}
              >
                <span className={`text-sm transition-all ${isActive ? "animate-pulse" : ""}`}>{step.icon}</span>
                <div className="hidden sm:block">
                  <div className="font-mono text-[9px] font-semibold">{step.label}</div>
                  <div className="font-mono text-[8px] opacity-60">{step.desc}</div>
                </div>
                {isCompleted && <span className="font-mono text-[9px] text-[var(--color-accent-green-bright)]">✓</span>}
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <span
                  className="mx-1 font-mono text-xs transition-colors"
                  style={{ color: isCompleted ? "var(--color-accent-green-bright)" : "var(--color-space-border-strong)" }}
                >→</span>
              )}
            </div>
          );
        })}
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
              <p className="max-w-xs font-mono text-[10px] leading-relaxed text-[var(--color-text-tertiary)]">
                Ask about orbital mechanics, conjunction analysis, debris mitigation, spacecraft systems, launch vehicles, or space missions.
              </p>
            </div>

            {/* Example queries */}
            <div className="grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
              {EXAMPLE_QUERIES.map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendQuery(q)}
                  className="rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-2.5 text-left font-mono text-[10px] leading-relaxed text-[var(--color-text-secondary)] transition-all hover:border-[var(--color-accent-indigo)] hover:bg-[var(--color-accent-indigo-glow)] hover:text-[var(--color-text-primary)]"
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Corpus stats */}
            <div className="flex gap-4 rounded border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-2.5">
              {[
                { label: "Corpus chunks", value: "185", color: "var(--color-accent-indigo-bright)" },
                { label: "Domains",       value: "12",  color: "var(--color-accent-green-bright)" },
                { label: "Graph nodes",   value: "29,248", color: "var(--color-accent-amber-bright)" },
                { label: "Retrieval",     value: "100%", color: "var(--color-accent-green-bright)" },
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
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-accent-indigo)] bg-[var(--color-accent-indigo-glow)] font-mono text-xs text-[var(--color-accent-indigo-bright)]">
                ◈
              </div>
            )}
            <div
              className={`max-w-2xl rounded-lg border px-4 py-3 ${
                msg.role === "user"
                  ? "border-[var(--color-space-border-strong)] bg-[var(--color-space-elevated)]"
                  : msg.error
                  ? "border-[var(--color-accent-red)] bg-[rgba(239,68,68,0.05)]"
                  : "border-[var(--color-space-border)] bg-[var(--color-space-navy)]"
              }`}
            >
              {msg.role === "user" ? (
                <p className="font-body text-[12px] leading-relaxed text-[var(--color-text-primary)]">{msg.content}</p>
              ) : (
                <AnswerText content={msg.content} />
              )}

              {msg.role === "assistant" && !msg.error && (
                <div className="mt-2.5 flex flex-wrap items-center gap-3 border-t border-[var(--color-space-border)] pt-2">
                  {msg.latency != null && (
                    <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
                      ⏱ {(msg.latency / 1000).toFixed(1)}s
                    </span>
                  )}
                  {msg.mode && (
                    <span className="rounded border border-[var(--color-accent-indigo)] bg-[var(--color-accent-indigo-glow)] px-1.5 py-0.5 font-mono text-[8px] text-[var(--color-accent-indigo-bright)]">
                      {msg.mode}
                    </span>
                  )}
                  {msg.confidence != null && (
                    <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
                      conf {(msg.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[9px] text-[var(--color-text-tertiary)]">
                    {msg.timestamp.toLocaleTimeString()}
                  </span>
                </div>
              )}
            </div>
            {msg.role === "user" && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-space-border-strong)] bg-[var(--color-space-elevated)] font-mono text-xs text-[var(--color-text-secondary)]">
                ⊙
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex justify-start gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-accent-indigo)] bg-[var(--color-accent-indigo-glow)] font-mono text-xs text-[var(--color-accent-indigo-bright)] animate-pulse">
              ◈
            </div>
            <div className="rounded-lg border border-[var(--color-space-border)] bg-[var(--color-space-navy)] px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-[var(--color-text-secondary)]">
                  {activeStep
                    ? `${PIPELINE_STEPS.find(s => s.id === activeStep)?.label ?? "Processing"}…`
                    : "Synthesizing…"}
                </span>
                {[0, 150, 300].map(delay => (
                  <span
                    key={delay}
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--color-accent-indigo)]"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
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
            placeholder="Ask about orbital mechanics, conjunction analysis, spacecraft systems… (Enter to send, Shift+Enter for newline)"
            rows={2}
            disabled={loading}
            className="flex-1 resize-none rounded border border-[var(--color-space-border)] bg-[var(--color-space-surface)] px-3 py-2 font-mono text-[11px] leading-relaxed text-[var(--color-text-primary)] placeholder-[var(--color-text-tertiary)] outline-none focus:border-[var(--color-accent-indigo)] transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => sendQuery(input)}
            disabled={loading || !input.trim()}
            className="self-end rounded border border-[var(--color-accent-indigo)] bg-[var(--color-accent-indigo-glow)] px-5 py-2 font-mono text-[11px] font-semibold text-[var(--color-accent-indigo-bright)] transition-all hover:bg-[var(--color-accent-indigo)] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "…" : "Send ⏎"}
          </button>
        </div>
        <p className="mt-1.5 font-mono text-[8px] text-[var(--color-text-tertiary)]">
          vector retrieval (185 chunks, 12 domains) · knowledge graph (29,248 nodes) · Claude Sonnet 4.6 synthesis · avg 28s
        </p>
      </div>
    </div>
  );
}
