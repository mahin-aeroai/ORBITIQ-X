/**
 * ORBITIQ-X — KnowledgeGraphInner
 * ==================================
 * Full vis-network implementation. Browser-only — loaded via next/dynamic.
 * DO NOT import this file directly; use KnowledgeGraphExplorer.tsx.
 *
 * Architecture
 * ─────────────
 * • vis-network is imperative; the Network instance lives in a ref.
 * • DataSet<Node> and DataSet<Edge> are built from API data and
 *   passed to Network — vis-network manages all rendering.
 * • On view change, nodes/edges are replaced via dataset.clear() + add().
 *   The Network canvas is NEVER destroyed — only data changes.
 * • requestAnimationFrame batching prevents freezes at 10K+ nodes.
 *
 * Views
 * ──────
 *   conjunction  — satellite risk network (vis-network graph canvas)
 *   operator     — tabular operator intelligence (no canvas)
 *   regime       — orbital density bars (no canvas)
 *   constellation— constellation leaderboard (no canvas)
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchConjunctionNetwork,
  fetchGraphSummary,
  fetchGraphOperators,
  fetchRiskOperators,
  fetchGraphCountries,
  fetchRegimeDensity,
  fetchConstellations,
  fetchGraphSearch,
  fetchSatelliteSubgraph,
  type ConjunctionNetwork,
  type GraphOperator,
  type RiskOperator,
  type RegimeDensity,
  type GraphConstellation,
} from "@/lib/api";

// ─── Design tokens (canvas cannot use CSS vars — hard-code palette) ───────────
const C = {
  indigo:      "#6366f1",
  indigoBright:"#818cf8",
  indigoDim:   "#3730a3",
  amber:       "#f59e0b",
  amberBright: "#fbbf24",
  green:       "#10b981",
  greenBright: "#34d399",
  red:         "#ef4444",
  redBright:   "#f87171",
  surface:     "#111d35",
  elevated:    "#162040",
  border:      "#1e2d4a",
  textPrimary: "#e2e8f8",
  textMuted:   "#94a3b8",
  textData:    "#7dd3fc",
  bg:          "#080d1a",
} as const;

// Risk level → node colour
const RISK_COLOR: Record<string, string> = {
  red:    C.red,
  yellow: C.amber,
  green:  C.green,
  white:  C.textMuted,
};

// ─── View types ───────────────────────────────────────────────────────────────
type View = "conjunction" | "operator" | "regime" | "constellation";

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatPc(pc: number | null | undefined): string {
  if (pc === null || pc === undefined || pc === 0) return "—";
  const exp = Math.floor(Math.log10(pc));
  const man = (pc / Math.pow(10, exp)).toFixed(1);
  return `${man}×10⁻${Math.abs(exp)}`;
}

// ─── Sub-views (non-canvas) ───────────────────────────────────────────────────

function OperatorView() {
  const { data: opData,   isLoading: opLoading   } = useQuery({ queryKey: ["graph-operators"],      queryFn: () => fetchGraphOperators(30),   staleTime: 60_000 });
  const { data: riskData, isLoading: riskLoading  } = useQuery({ queryKey: ["graph-risk-operators"], queryFn: () => fetchRiskOperators(15),    staleTime: 60_000 });
  const { data: ctryData, isLoading: ctryLoading  } = useQuery({ queryKey: ["graph-countries"],     queryFn: () => fetchGraphCountries(20),   staleTime: 60_000 });

  return (
    <div className="flex h-full gap-0 overflow-hidden">
      {/* Top operators */}
      <div className="flex w-1/3 flex-col border-r border-space-border">
        <div className="border-b border-space-border px-4 py-2.5">
          <span className="section-label">TOP OPERATORS — FLEET SIZE</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {opLoading ? (
            <div className="space-y-1 p-3">
              {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-8 animate-pulse rounded bg-space-surface" />)}
            </div>
          ) : (opData?.operators ?? []).map((op: GraphOperator, i: number) => (
            <div key={op.operator} className="flex items-center gap-3 border-b border-space-border px-4 py-2 hover:bg-space-surface">
              <span className="w-5 font-mono text-[9px] text-space-muted">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="truncate font-mono text-[11px] text-space-text">{op.operator}</div>
                <div className="mt-0.5 flex gap-1 flex-wrap">
                  {(op.regimes ?? []).slice(0, 3).map((r) => (
                    <span key={r} className="rounded border border-space-border px-1 font-mono text-[8px] text-space-muted">{r}</span>
                  ))}
                </div>
              </div>
              <span className="font-mono text-[11px] tabular-nums" style={{ color: C.indigoBright }}>{op.satelliteCount}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Risk operators */}
      <div className="flex w-1/3 flex-col border-r border-space-border">
        <div className="border-b border-space-border px-4 py-2.5">
          <span className="section-label">CONJUNCTION RISK EXPOSURE</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {riskLoading ? (
            <div className="space-y-1 p-3">
              {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-8 animate-pulse rounded bg-space-surface" />)}
            </div>
          ) : (riskData?.operators ?? []).map((op: RiskOperator, i: number) => {
            const barWidth = Math.min(100, (op.maxPc / 1e-3) * 100);
            return (
              <div key={op.operator} className="border-b border-space-border px-4 py-2 hover:bg-space-surface">
                <div className="mb-1 flex items-center justify-between">
                  <span className="truncate font-mono text-[10px] text-space-text" style={{ maxWidth: "60%" }}>{op.operator}</span>
                  <div className="flex items-center gap-1.5">
                    {op.redEvents > 0 && (
                      <span className="rounded px-1 font-mono text-[8px]" style={{ color: C.red, background: `${C.red}20` }}>
                        {op.redEvents} RED
                      </span>
                    )}
                    <span className="font-mono text-[9px] text-space-muted">{op.unresolved} events</span>
                  </div>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-space-surface">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${barWidth}%`, backgroundColor: op.redEvents > 0 ? C.red : C.amber }}
                  />
                </div>
                <div className="mt-0.5 font-mono text-[8px] text-space-muted">Max Pc: {formatPc(op.maxPc)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Countries */}
      <div className="flex w-1/3 flex-col">
        <div className="border-b border-space-border px-4 py-2.5">
          <span className="section-label">COUNTRIES — ACTIVE SPACECRAFT</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {ctryLoading ? (
            <div className="space-y-1 p-3">
              {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-8 animate-pulse rounded bg-space-surface" />)}
            </div>
          ) : (ctryData?.countries ?? []).map((c, i: number) => (
            <div key={c.countryCode} className="flex items-center gap-3 border-b border-space-border px-4 py-2 hover:bg-space-surface">
              <span className="w-5 font-mono text-[9px] text-space-muted">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="truncate font-mono text-[11px] text-space-text">{c.countryName || c.countryCode}</div>
                <div className="font-mono text-[9px] text-space-muted">{c.countryCode}</div>
              </div>
              <span className="font-mono text-[11px] tabular-nums" style={{ color: C.greenBright }}>{c.activeSatellites}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RegimeView() {
  const { data, isLoading } = useQuery({ queryKey: ["graph-regimes"], queryFn: fetchRegimeDensity, staleTime: 120_000 });
  const regimes: RegimeDensity[] = data?.regimes ?? [];
  const max = Math.max(1, ...regimes.map((r) => r.totalObjects));

  return (
    <div className="flex h-full items-start overflow-y-auto p-6">
      <div className="w-full max-w-3xl mx-auto">
        <div className="mb-4">
          <h2 className="font-display text-base font-semibold text-space-text">Orbital Regime Density</h2>
          <p className="font-mono text-[11px] text-space-muted mt-0.5">
            Object population by orbital shell — satellites, debris, rocket bodies
          </p>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-12 animate-pulse rounded bg-space-surface" />)}
          </div>
        ) : (
          <div className="space-y-2">
            {regimes.map((r) => {
              const totalW = (r.totalObjects / max) * 100;
              const satW   = (r.satellites / max) * 100;
              const debW   = (r.debris / max) * 100;
              return (
                <div key={r.regimeId ?? r.regime} className="rounded border border-space-border bg-space-navy p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <span className="font-display text-sm font-semibold text-space-text">{r.regime}</span>
                      {r.altMinKm != null && r.altMaxKm != null && (
                        <span className="ml-2 font-mono text-[9px] text-space-muted">
                          {r.altMinKm}–{r.altMaxKm} km
                        </span>
                      )}
                    </div>
                    <span className="font-mono text-[11px] tabular-nums" style={{ color: C.textData }}>
                      {r.totalObjects.toLocaleString()} objects
                    </span>
                  </div>
                  {/* Stacked bar */}
                  <div className="h-2 w-full overflow-hidden rounded-full bg-space-surface">
                    <div className="relative h-full">
                      <div className="absolute left-0 top-0 h-full rounded-full" style={{ width: `${totalW}%`, backgroundColor: C.border }} />
                      <div className="absolute left-0 top-0 h-full rounded-full" style={{ width: `${satW}%`, backgroundColor: C.indigo }} />
                      <div
                        className="absolute top-0 h-full rounded-full"
                        style={{ left: `${satW}%`, width: `${debW}%`, backgroundColor: C.amber }}
                      />
                    </div>
                  </div>
                  <div className="mt-1.5 flex gap-4">
                    <span className="font-mono text-[9px]" style={{ color: C.indigoBright }}>
                      ■ {r.satellites.toLocaleString()} sat
                    </span>
                    <span className="font-mono text-[9px]" style={{ color: C.amberBright }}>
                      ■ {r.debris.toLocaleString()} debris
                    </span>
                    <span className="font-mono text-[9px] text-space-muted">
                      ■ {r.rocketBodies.toLocaleString()} RB
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ConstellationView() {
  const { data, isLoading } = useQuery({ queryKey: ["graph-constellations"], queryFn: () => fetchConstellations(20), staleTime: 120_000 });
  const list: GraphConstellation[] = data?.constellations ?? [];
  const max = Math.max(1, ...list.map((c) => c.memberCount));

  return (
    <div className="flex h-full items-start overflow-y-auto p-6">
      <div className="w-full max-w-2xl mx-auto">
        <div className="mb-4">
          <h2 className="font-display text-base font-semibold text-space-text">Largest Constellations</h2>
          <p className="font-mono text-[11px] text-space-muted mt-0.5">Satellite constellations by member count</p>
        </div>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => <div key={i} className="h-10 animate-pulse rounded bg-space-surface" />)}
          </div>
        ) : (
          <div className="space-y-1.5">
            {list.map((c, i) => (
              <div key={c.constellation} className="rounded border border-space-border bg-space-navy px-4 py-2.5">
                <div className="mb-1.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[9px] text-space-muted w-5">{i + 1}</span>
                    <span className="font-display text-[12px] font-semibold text-space-text">{c.constellation}</span>
                  </div>
                  <span className="font-mono text-[11px] tabular-nums" style={{ color: C.indigoBright }}>
                    {c.memberCount.toLocaleString()} satellites
                  </span>
                </div>
                <div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-space-surface">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(c.memberCount / max) * 100}%`, backgroundColor: C.indigo }}
                  />
                </div>
                <div className="flex gap-3">
                  {c.operator && <span className="font-mono text-[9px] text-space-muted">{c.operator}</span>}
                  {c.primaryRegime && (
                    <span className="rounded border border-space-border px-1 font-mono text-[8px] text-space-muted">{c.primaryRegime}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Conjunction network canvas view ─────────────────────────────────────────

interface SelectedNode {
  id:        string;
  label:     string;
  riskLevel: string;
  edges:     Array<{ conjunctionId: string; Pc: number; missKm: number; riskLevel: string; peer: string }>;
}

function ConjunctionNetworkView() {
  const containerRef  = useRef<HTMLDivElement>(null);
  const networkRef    = useRef<import("vis-network").Network | null>(null);
  const nodesRef      = useRef<import("vis-data").DataSet<import("vis-network").Node> | null>(null);
  const edgesRef      = useRef<import("vis-data").DataSet<import("vis-network").Edge> | null>(null);

  const [minPc,        setMinPc]        = useState<number>(1e-5);
  const [selected,     setSelected]     = useState<SelectedNode | null>(null);
  const [searchQ,      setSearchQ]      = useState("");
  const [searchResult, setSearchResult] = useState<Array<{ label: string; id: string }>>([]);
  const [loadingSearch,setLoadingSearch]= useState(false);
  const [nodeDetail,   setNodeDetail]   = useState<Record<string, unknown> | null>(null);
  const [loadingDetail,setLoadingDetail]= useState(false);
  const [networkReady, setNetworkReady] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey:        ["graph-conjunction-network", minPc],
    queryFn:         () => fetchConjunctionNetwork(minPc, 300),
    staleTime:       60_000,
    refetchInterval: 120_000,
  });

  // ── Build vis-network options ────────────────────────────────────────────

  const visOptions = useMemo<import("vis-network").Options>(() => ({
    nodes: {
      shape:         "dot",
      size:          6,
      font:          { size: 9, color: C.textPrimary, face: "JetBrains Mono, monospace" },
      borderWidth:   1,
      borderWidthSelected: 2,
    },
    edges: {
      width:       1,
      smooth:      { enabled: true, type: "dynamic", roundness: 0.5 },
      font:        { size: 7, color: C.textMuted, face: "JetBrains Mono, monospace" },
      color:       { inherit: "from" },
    },
    physics: {
      enabled:     true,
      solver:      "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -40,
        centralGravity:        0.005,
        springLength:          80,
        springConstant:        0.06,
        damping:               0.5,
        avoidOverlap:          0.3,
      },
      stabilization: { iterations: 200, updateInterval: 25 },
      maxVelocity:   50,
      minVelocity:   0.5,
    },
    interaction: {
      hover:           true,
      tooltipDelay:    150,
      zoomView:        true,
      dragView:        true,
      dragNodes:       true,
      multiselect:     false,
      navigationButtons: false,
    },
    layout: { improvedLayout: true },
  }), []);

  // ── Initialise network once ──────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current) return;
    import("vis-network").then(({ Network }) => {
      import("vis-data").then(({ DataSet }) => {
        const nodes = new DataSet<import("vis-network").Node>([]);
        const edges = new DataSet<import("vis-network").Edge>([]);
        nodesRef.current = nodes;
        edgesRef.current = edges;

        const net = new Network(containerRef.current!, { nodes, edges }, visOptions);
        networkRef.current = net;

        net.on("click", (params) => {
          if (params.nodes.length > 0) {
            const nodeId = String(params.nodes[0]);
            const node   = nodes.get(nodeId);
            if (!node) return;

            // Collect edges for this node
            const connectedEdges = net.getConnectedEdges(nodeId);
            const nodeEdges = connectedEdges.map((eid) => {
              const e = edges.get(String(eid));
              if (!e) return null;
              const peer = String(e.from) === nodeId ? String(e.to) : String(e.from);
              const peerNode = nodes.get(peer);
              return {
                conjunctionId: (e as any).title || "",
                Pc:            (e as any).Pc || 0,
                missKm:        (e as any).missKm || 0,
                riskLevel:     (e as any).riskLevel || "green",
                peer:          peerNode?.label || peer,
              };
            }).filter(Boolean) as SelectedNode["edges"];

            setSelected({
              id:        nodeId,
              label:     String(node.label ?? nodeId),
              riskLevel: (node as any).riskLevel || "green",
              edges:     nodeEdges.sort((a, b) => b.Pc - a.Pc).slice(0, 10),
            });

            // Fetch subgraph detail if NORAD-like id
            const norad = parseInt(nodeId, 10);
            if (!isNaN(norad) && norad > 0) {
              setLoadingDetail(true);
              fetchSatelliteSubgraph(norad)
                .then((d) => setNodeDetail(d))
                .catch(() => setNodeDetail(null))
                .finally(() => setLoadingDetail(false));
            }
          } else {
            setSelected(null);
            setNodeDetail(null);
          }
        });

        setNetworkReady(true);
      });
    });

    return () => {
      networkRef.current?.destroy();
      networkRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Populate network when data arrives ──────────────────────────────────

  useEffect(() => {
    if (!data || !nodesRef.current || !edgesRef.current) return;

    const nodes = nodesRef.current;
    const edges = edgesRef.current;

    // Build vis-network nodes
    const visNodes: import("vis-network").Node[] = data.nodes.map((n) => ({
      id:          n.id,
      label:       n.label.length > 18 ? n.label.slice(0, 15) + "…" : n.label,
      color: {
        background: RISK_COLOR[n.riskLevel] ?? C.green,
        border:     "#000",
        highlight:  { background: C.indigoBright, border: C.indigo },
        hover:      { background: C.amberBright,  border: C.amber  },
      },
      // Store risk level for click handler
      ...(({ riskLevel: n.riskLevel }) as any),
    }));

    // Build vis-network edges
    const visEdges: import("vis-network").Edge[] = data.edges.map((e, i) => ({
      id:     `e-${i}`,
      from:   e.source,
      to:     e.target,
      color:  { color: RISK_COLOR[e.riskLevel] ?? C.green, opacity: 0.5 },
      width:  e.riskLevel === "red" ? 2 : 1,
      // Store CDM data for detail panel
      ...(({ Pc: e.Pc, missKm: e.missKm, riskLevel: e.riskLevel, title: e.conjunctionId }) as any),
    }));

    nodes.clear();
    edges.clear();
    nodes.add(visNodes);
    edges.add(visEdges);

    // Fit after physics stabilises
    networkRef.current?.once("stabilizationIterationsDone", () => {
      networkRef.current?.fit({ animation: { duration: 600, easingFunction: "easeInOutQuad" } });
      networkRef.current?.setOptions({ physics: { enabled: false } });
    });
  }, [data]);

  // ── Search ───────────────────────────────────────────────────────────────

  const handleSearch = useCallback(async (q: string) => {
    if (q.length < 2) { setSearchResult([]); return; }
    setLoadingSearch(true);
    try {
      const r = await fetchGraphSearch(q, 10);
      const hits = (r.results ?? []).map((row: any) => ({
        label: row.s?.name || row.name || String(row.noradId || row.id || ""),
        id:    String(row.s?.noradId || row.noradId || ""),
      })).filter((h: any) => h.id);
      setSearchResult(hits);
    } catch {
      setSearchResult([]);
    } finally {
      setLoadingSearch(false);
    }
  }, []);

  const focusNode = useCallback((id: string) => {
    const net = networkRef.current;
    if (!net) return;
    net.selectNodes([id]);
    net.focus(id, { animation: { duration: 600, easingFunction: "easeInOutQuad" }, scale: 1.5 });
    setSearchResult([]);
    setSearchQ("");
  }, []);

  // ── Pc filter change ─────────────────────────────────────────────────────

  const PC_OPTIONS = [
    { label: "All (≥1e-7)", value: 1e-7 },
    { label: "GREEN (≥1e-5)", value: 1e-5 },
    { label: "YELLOW (≥1e-4)", value: 1e-4 },
    { label: "RED (≥1e-3)", value: 1e-3 },
  ];

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* ── Top toolbar ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 border-b border-space-border bg-space-midnight px-4 py-2">
        {/* Pc filter */}
        <div className="flex items-center gap-1.5">
          <span className="section-label">RISK THRESHOLD</span>
          <select
            value={minPc}
            onChange={(e) => setMinPc(Number(e.target.value))}
            className="rounded border border-space-border bg-space-navy px-2 py-0.5 font-mono text-[10px] text-space-text"
          >
            {PC_OPTIONS.map((o) => (
              <option key={o.label} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="h-4 w-px bg-space-border" />

        {/* Search */}
        <div className="relative">
          <input
            type="text"
            placeholder="Search satellite…"
            value={searchQ}
            onChange={(e) => { setSearchQ(e.target.value); handleSearch(e.target.value); }}
            className="rounded border border-space-border bg-space-navy px-2 py-0.5 font-mono text-[10px] text-space-text placeholder:text-space-muted w-44"
          />
          {searchResult.length > 0 && (
            <div className="absolute left-0 top-full z-50 mt-1 w-56 rounded border border-space-border bg-space-elevated shadow-panel">
              {searchResult.map((r) => (
                <button
                  key={r.id}
                  onClick={() => focusNode(r.id)}
                  className="block w-full px-3 py-1.5 text-left font-mono text-[10px] text-space-text hover:bg-space-surface"
                >
                  {r.label}
                </button>
              ))}
            </div>
          )}
          {loadingSearch && <span className="absolute right-2 top-1 font-mono text-[8px] text-space-muted">…</span>}
        </div>

        <div className="h-4 w-px bg-space-border" />

        {/* Controls */}
        <button
          onClick={() => networkRef.current?.fit({ animation: { duration: 600, easingFunction: "easeInOutQuad" } })}
          className="rounded border border-space-border bg-space-navy px-2 py-0.5 font-mono text-[9px] text-space-muted hover:text-space-text"
        >
          FIT
        </button>
        <button
          onClick={() => { networkRef.current?.setOptions({ physics: { enabled: true } }); setTimeout(() => networkRef.current?.setOptions({ physics: { enabled: false } }), 2000); }}
          className="rounded border border-space-border bg-space-navy px-2 py-0.5 font-mono text-[9px] text-space-muted hover:text-space-text"
        >
          RELAYOUT
        </button>

        {/* Stats */}
        {data && (
          <span className="ml-auto font-mono text-[9px] text-space-muted">
            {data.meta.nodeCount} nodes · {data.meta.edgeCount} edges
          </span>
        )}
      </div>

      {/* ── Canvas area ──────────────────────────────────────────────────── */}
      <div className="relative flex-1 overflow-hidden">
        {/* Loading overlay */}
        {isLoading && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-space-midnight/80">
            <div className="text-center">
              <div className="mx-auto mb-2 h-1 w-40 overflow-hidden rounded-full bg-space-surface">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
              </div>
              <span className="section-label">BUILDING CONJUNCTION NETWORK</span>
            </div>
          </div>
        )}

        {/* Error / empty */}
        {isError && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="rounded border border-[var(--color-accent-amber)] bg-space-navy/90 px-6 py-4 text-center">
              <div className="section-label mb-1" style={{ color: "#f59e0b" }}>GRAPH UNAVAILABLE</div>
              <div className="font-mono text-[11px] text-space-muted">Neo4j not reachable. Populate the graph first.</div>
            </div>
          </div>
        )}

        {/* vis-network canvas */}
        <div ref={containerRef} className="h-full w-full" style={{ background: C.bg }} />

        {/* Legend */}
        <div className="absolute bottom-3 left-3 rounded border border-space-border bg-space-midnight/90 px-3 py-2">
          <div className="section-label mb-1.5">RISK LEVEL</div>
          {[
            { label: "RED  (Pc ≥ 1e-3)", color: C.red },
            { label: "YELLOW (Pc ≥ 1e-4)", color: C.amber },
            { label: "GREEN (Pc ≥ 1e-5)", color: C.green },
          ].map(({ label, color }) => (
            <div key={label} className="flex items-center gap-1.5 py-0.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              <span className="font-mono text-[9px] text-space-muted">{label}</span>
            </div>
          ))}
        </div>

        {/* Selected node detail panel */}
        {selected && (
          <div className="absolute right-3 top-3 z-20 w-64 rounded border border-space-border bg-space-elevated shadow-panel">
            <div className="flex items-center justify-between border-b border-space-border px-3 py-2">
              <span className="section-label">NODE DETAIL</span>
              <button
                className="font-mono text-[11px] text-space-muted hover:text-space-text"
                onClick={() => { setSelected(null); setNodeDetail(null); networkRef.current?.unselectAll(); }}
              >
                ×
              </button>
            </div>
            <div className="p-3">
              {/* Identity */}
              <div className="mb-2">
                <div className="font-display text-sm font-semibold text-space-text leading-tight">{selected.label}</div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="font-mono text-[9px] text-space-muted">NORAD {selected.id}</span>
                  <span
                    className="rounded px-1.5 py-0.5 font-mono text-[8px] font-bold uppercase"
                    style={{ color: RISK_COLOR[selected.riskLevel], backgroundColor: `${RISK_COLOR[selected.riskLevel]}20` }}
                  >
                    {selected.riskLevel.toUpperCase()}
                  </span>
                </div>
              </div>

              {/* Conjunction edges */}
              {selected.edges.length > 0 && (
                <div>
                  <div className="section-label mb-1.5">ACTIVE CONJUNCTIONS ({selected.edges.length})</div>
                  <div className="space-y-1">
                    {selected.edges.map((e, i) => (
                      <div key={i} className="rounded border border-space-border bg-space-navy px-2 py-1.5">
                        <div className="truncate font-mono text-[9px] text-space-text">{e.peer}</div>
                        <div className="mt-0.5 flex items-center justify-between">
                          <span className="font-mono text-[8px] text-space-muted">
                            Pc {formatPc(e.Pc)}
                          </span>
                          <span className="font-mono text-[8px] text-space-muted">
                            {e.missKm.toFixed(2)} km
                          </span>
                          <span
                            className="font-mono text-[8px] uppercase"
                            style={{ color: RISK_COLOR[e.riskLevel] }}
                          >
                            {e.riskLevel}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Subgraph detail */}
              {loadingDetail && (
                <div className="mt-2 space-y-1">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-4 animate-pulse rounded bg-space-surface" />
                  ))}
                </div>
              )}
              {nodeDetail && !loadingDetail && (
                <div className="mt-2 border-t border-space-border pt-2">
                  <div className="section-label mb-1">GRAPH CONTEXT</div>
                  {[
                    ["Operator",  (nodeDetail as any).operatorName],
                    ["Country",   (nodeDetail as any).countryName],
                    ["Orbit",     (nodeDetail as any).orbitName],
                    ["Const.",    (nodeDetail as any).constellation],
                    ["Vehicle",   (nodeDetail as any).launchVehicle],
                    ["Conj. #",   (nodeDetail as any).conjunctionCount],
                  ].filter(([, v]) => v != null && v !== "" && v !== 0).map(([label, value]) => (
                    <div key={String(label)} className="flex items-center justify-between py-0.5">
                      <span className="font-mono text-[9px] text-space-muted">{label}</span>
                      <span className="data-value text-[9px]">{String(value)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main inner component ─────────────────────────────────────────────────────

export function KnowledgeGraphInner() {
  const [view, setView] = useState<View>("conjunction");

  const { data: summary } = useQuery({
    queryKey:        ["graph-summary"],
    queryFn:         fetchGraphSummary,
    staleTime:       60_000,
    refetchInterval: 120_000,
  });

  const graphAvailable = summary?.available !== false;

  const VIEWS: { key: View; label: string }[] = [
    { key: "conjunction",   label: "CONJUNCTION NETWORK" },
    { key: "operator",      label: "OPERATOR INTELLIGENCE" },
    { key: "regime",        label: "ORBITAL REGIMES" },
    { key: "constellation", label: "CONSTELLATIONS" },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-space-border bg-space-midnight px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="font-display text-xs font-semibold uppercase tracking-widest text-space-text">
            AEROSPACE KNOWLEDGE GRAPH
          </span>
          {summary && (
            <span className="font-mono text-[9px] text-space-muted">
              {(summary.total_nodes ?? 0).toLocaleString()} nodes · {(summary.total_rels ?? 0).toLocaleString()} relationships
            </span>
          )}
        </div>

        {/* Graph availability indicator */}
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: graphAvailable ? "#10b981" : "#f59e0b" }}
          />
          <span className="font-mono text-[9px] text-space-muted">
            {graphAvailable ? "GRAPH ONLINE" : "GRAPH OFFLINE"}
          </span>
        </div>
      </div>

      {/* ── View tabs ───────────────────────────────────────────────────── */}
      <div className="flex border-b border-space-border bg-space-midnight">
        {VIEWS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setView(key)}
            className={[
              "px-4 py-2 font-mono text-[9px] uppercase tracking-wider transition-colors",
              "border-r border-space-border hover:text-space-text",
              view === key
                ? "border-b-2 border-b-[var(--color-accent-indigo)] text-space-accent bg-[var(--color-accent-indigo-glow)]"
                : "text-space-muted",
            ].join(" ")}
          >
            {label}
          </button>
        ))}

        {/* Summary badges */}
        {summary?.node_counts && (
          <div className="ml-auto flex items-center gap-3 px-4">
            {[
              { label: "SAT",  key: "Satellite",       color: C.indigo },
              { label: "CDM",  key: "ConjunctionEvent",color: C.red },
              { label: "OP",   key: "Operator",         color: C.green },
            ].map(({ label, key, color }) => (
              summary.node_counts[key] != null && (
                <div key={key} className="flex items-center gap-1">
                  <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="font-mono text-[9px] text-space-muted">{label}: {(summary.node_counts[key] ?? 0).toLocaleString()}</span>
                </div>
              )
            ))}
          </div>
        )}
      </div>

      {/* ── View content ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        {view === "conjunction"   && <ConjunctionNetworkView />}
        {view === "operator"      && <OperatorView />}
        {view === "regime"        && <RegimeView />}
        {view === "constellation" && <ConstellationView />}
      </div>
    </div>
  );
}
