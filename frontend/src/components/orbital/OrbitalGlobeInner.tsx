/**
 * ORBITIQ-X — OrbitalGlobeInner
 * ================================
 * Full Cesium/Resium implementation. Loaded only client-side via next/dynamic.
 * Never import this file directly — use OrbitalGlobe.tsx (the SSR-safe shell).
 *
 * Performance architecture for 50 K+ objects
 * ─────────────────────────────────────────────
 *   PointPrimitiveCollection — single GPU draw call for all satellite dots.
 *   requestRenderMode: true  — Cesium only re-renders on explicit dirty flag.
 *   30-second refresh        — positions updated in-place; viewer never recreated.
 *   Conjunction entities     — separate Entity per CDM (count always ≤ 100).
 *
 * Data sources (verified against backend source before writing)
 * ──────────────────────────────────────────────────────────────
 *   Satellites    : GET /api/v1/digital-twin/cesium/states?limit=10000
 *   Detail panel  : GET /api/v1/digital-twin/state/{norad_id}
 *   Conjunctions  : GET /api/v1/ssa/conjunctions/high-risk?limit=50
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Viewer,
  Scene,
  ScreenSpaceEvent,
  ScreenSpaceEventHandler,
  Entity,
} from "resium";
import type { CesiumComponentRef } from "resium";
import {
  Cartesian3,
  Color,
  PointPrimitiveCollection,
  ScreenSpaceEventType,
  HeightReference,
  type Viewer as CesiumViewer,
  type PointPrimitive,
  type Cartesian2,
} from "cesium";

import type { OrbitalGlobeProps } from "./OrbitalGlobe";
import {
  fetchCesiumStates,
  fetchHighRiskConjunctions,
  fetchSatelliteDetail,
  type CesiumSatObject,
  type SatelliteDetailState,
  type ConjunctionItem,
} from "@/lib/api";

// ─── Design-token colour palette ──────────────────────────────────────────────
// Matches globals.css exactly; only values here, no CSS vars (Cesium is canvas).

const REGIME_COLOR: Record<string, Color> = {
  VLEO:     new Color(129 / 255, 140 / 255, 248 / 255, 1.0),  // indigo bright
  LEO:      new Color( 99 / 255, 102 / 255, 241 / 255, 1.0),  // indigo
  SSO:      new Color( 96 / 255, 165 / 255, 250 / 255, 1.0),  // sky
  MEO:      new Color(245 / 255, 158 / 255,  11 / 255, 1.0),  // amber
  GEO:      new Color( 16 / 255, 185 / 255, 129 / 255, 1.0),  // green
  GTO:      new Color(251 / 255, 191 / 255,  36 / 255, 1.0),  // yellow
  HEO:      new Color(249 / 255, 115 / 255,  22 / 255, 1.0),  // orange
  CISLUNAR: new Color(167 / 255,  85 / 255, 247 / 255, 1.0),  // purple
  UNKNOWN:  new Color( 71 / 255,  85 / 255, 105 / 255, 0.6),  // grey dim
};

const REGIME_PIXEL_SIZE: Record<string, number> = {
  VLEO: 2, LEO: 2, SSO: 2,
  MEO: 3, GEO: 4, GTO: 3,
  HEO: 3, CISLUNAR: 4, UNKNOWN: 1,
};

const CONJUNCTION_COLOR: Record<string, Color> = {
  red:    new Color(239 / 255,  68 / 255,  68 / 255, 0.95),
  yellow: new Color(245 / 255, 158 / 255,  11 / 255, 0.95),
  green:  new Color( 16 / 255, 185 / 255, 129 / 255, 0.90),
  white:  new Color(148 / 255, 163 / 255, 184 / 255, 0.70),
};

// ─── Camera presets ───────────────────────────────────────────────────────────

const CAMERA_PRESETS = {
  "Global View": { lon:  0.0, lat: 20.0, altKm: 25_000 },
  "LEO View":    { lon:  0.0, lat: 20.0, altKm:  2_000 },
  "MEO View":    { lon:  0.0, lat: 20.0, altKm: 12_000 },
  "GEO View":    { lon:  0.0, lat:  0.0, altKm: 45_000 },
  "Home View":   { lon: 78.9, lat: 20.6, altKm: 20_000 },
} as const;

type CameraPreset = keyof typeof CAMERA_PRESETS;

// ─── Local types ──────────────────────────────────────────────────────────────

interface TooltipState {
  visible:  boolean;
  x:        number;
  y:        number;
  noradId:  number;
  name:     string;
  regime:   string;
  altKm:    number;
  speedKms: number;
}

interface FilterState {
  showLEO:     boolean;
  showMEO:     boolean;
  showGEO:     boolean;
  showDebris:  boolean;
  showPayload: boolean;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function toCartesian3(lon: number, lat: number, altKm: number): Cartesian3 {
  return Cartesian3.fromDegrees(lon, lat, altKm * 1000);
}

function passesFilter(sat: CesiumSatObject, f: FilterState): boolean {
  const r = sat.regime;
  if (!f.showLEO    && (r === "LEO" || r === "VLEO" || r === "SSO")) return false;
  if (!f.showMEO    && r === "MEO")                                   return false;
  if (!f.showGEO    && (r === "GEO" || r === "GTO"))                 return false;
  if (!f.showDebris  && sat.type === "DEBRIS")                        return false;
  if (!f.showPayload && sat.type === "PAYLOAD")                       return false;
  return true;
}

// ─── Main component ───────────────────────────────────────────────────────────

export function OrbitalGlobeInner({ showConjunctions = false }: OrbitalGlobeProps) {

  // ── Refs ──────────────────────────────────────────────────────────────────
  const viewerRef   = useRef<CesiumComponentRef<CesiumViewer>>(null);
  const collRef     = useRef<PointPrimitiveCollection | null>(null);
  // noradId → PointPrimitive for O(1) position updates
  const pointMapRef = useRef<Map<number, PointPrimitive>>(new Map());

  // ── State ─────────────────────────────────────────────────────────────────
  const [satellites,    setSatellites]    = useState<CesiumSatObject[]>([]);
  const [conjunctions,  setConjunctions]  = useState<ConjunctionItem[]>([]);
  const [selectedSat,   setSelectedSat]   = useState<SatelliteDetailState | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadState,     setLoadState]     = useState<"loading" | "loaded" | "error">("loading");
  const [satCount,      setSatCount]      = useState(0);
  const [lastEpoch,     setLastEpoch]     = useState<string | null>(null);
  const [activePreset,  setActivePreset]  = useState<CameraPreset>("Global View");
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false, x: 0, y: 0,
    noradId: 0, name: "", regime: "", altKm: 0, speedKms: 0,
  });
  const [filter, setFilter] = useState<FilterState>({
    showLEO: true, showMEO: true, showGEO: true,
    showDebris: true, showPayload: true,
  });

  // Keep a ref to satellites for use in event callbacks (avoids stale closure)
  const satellitesRef = useRef<CesiumSatObject[]>([]);
  useEffect(() => { satellitesRef.current = satellites; }, [satellites]);

  // ── Build PointPrimitiveCollection ────────────────────────────────────────

  const buildCollection = useCallback(
    (viewer: CesiumViewer, sats: CesiumSatObject[], currentFilter: FilterState) => {
      // Remove old collection from scene
      if (collRef.current && !viewer.isDestroyed()) {
        viewer.scene.primitives.remove(collRef.current);
        collRef.current.destroy();
      }

      const coll    = new PointPrimitiveCollection();
      const ptMap   = new Map<number, PointPrimitive>();

      for (const sat of sats) {
        if (!passesFilter(sat, currentFilter)) continue;

        const pt = coll.add({
          position:  toCartesian3(sat.lon, sat.lat, sat.alt_km),
          color:     REGIME_COLOR[sat.regime] ?? REGIME_COLOR.UNKNOWN,
          pixelSize: REGIME_PIXEL_SIZE[sat.regime] ?? 2,
          id:        sat.id,  // stored on primitive for scene.pick()
        }) as PointPrimitive;

        ptMap.set(sat.id, pt);
      }

      viewer.scene.primitives.add(coll);
      collRef.current   = coll;
      pointMapRef.current = ptMap;
      viewer.scene.requestRender();
    },
    [],
  );

  // ── Update point positions in-place (no collection rebuild) ──────────────

  const updatePositions = useCallback((sats: CesiumSatObject[]) => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || viewer.isDestroyed()) return;
    const ptMap = pointMapRef.current;
    let dirty = false;
    for (const sat of sats) {
      const pt = ptMap.get(sat.id);
      if (pt) {
        pt.position = toCartesian3(sat.lon, sat.lat, sat.alt_km);
        dirty = true;
      }
    }
    if (dirty) viewer.scene.requestRender();
  }, []);

  // ── Camera fly-to ─────────────────────────────────────────────────────────

  const flyToPreset = useCallback((preset: CameraPreset) => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || viewer.isDestroyed()) return;
    const { lon, lat, altKm } = CAMERA_PRESETS[preset];
    viewer.camera.flyTo({
      destination: toCartesian3(lon, lat, altKm),
      duration:    1.5,
    });
    setActivePreset(preset);
  }, []);

  // ── Viewer initialisation (runs once after Viewer mounts) ─────────────────

  useEffect(() => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || viewer.isDestroyed()) return;

    // Mission-control dark theme
    viewer.scene.backgroundColor = new Color(0.02, 0.03, 0.08, 1.0);
    viewer.scene.fog.enabled = false;
    viewer.scene.globe.showGroundAtmosphere = false;
    viewer.scene.globe.enableLighting = true;

    // Render on demand — major perf win for 50K objects
    viewer.scene.requestRenderMode         = true;
    viewer.scene.maximumRenderTimeChange   = 0.0;

    // Initial camera
    viewer.camera.flyTo({
      destination: toCartesian3(0, 20, 25_000),
      duration:    0,
    });

    // Build collection if data already arrived
    if (satellitesRef.current.length > 0) {
      buildCollection(viewer, satellitesRef.current, filter);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run only on mount

  // ── Initial satellite fetch ───────────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchCesiumStates(10_000);
        if (cancelled) return;
        setSatellites(data.objects);
        setSatCount(data.count);
        setLastEpoch(data.epoch);
        setLoadState("loaded");

        // Build collection now if viewer already mounted
        const viewer = viewerRef.current?.cesiumElement;
        if (viewer && !viewer.isDestroyed()) {
          buildCollection(viewer, data.objects, filter);
        }
      } catch {
        if (!cancelled) setLoadState("error");
      }
    })();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // on mount only

  // ── Conjunction fetch ──────────────────────────────────────────────────────

  useEffect(() => {
    if (!showConjunctions) return;
    let cancelled = false;
    fetchHighRiskConjunctions(50)
      .then((d) => { if (!cancelled) setConjunctions(d.items); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [showConjunctions]);

  // ── 30-second live refresh ────────────────────────────────────────────────

  useEffect(() => {
    if (loadState !== "loaded") return;

    const id = setInterval(async () => {
      try {
        const data = await fetchCesiumStates(10_000);
        setSatCount(data.count);
        setLastEpoch(data.epoch);

        const viewer = viewerRef.current?.cesiumElement;
        if (!viewer || viewer.isDestroyed()) return;

        // Large delta → rebuild; small delta → update in-place
        const current = satellitesRef.current;
        if (Math.abs(data.objects.length - current.length) > 200) {
          setSatellites(data.objects);
          buildCollection(viewer, data.objects, filter);
        } else {
          updatePositions(data.objects);
        }
      } catch { /* skip failed refresh */ }
    }, 30_000);

    return () => clearInterval(id);
  }, [loadState, filter, buildCollection, updatePositions]);

  // ── Rebuild when filter changes ────────────────────────────────────────────

  const applyFilter = useCallback((newFilter: FilterState) => {
    setFilter(newFilter);
    const viewer = viewerRef.current?.cesiumElement;
    if (viewer && !viewer.isDestroyed() && satellitesRef.current.length > 0) {
      buildCollection(viewer, satellitesRef.current, newFilter);
    }
  }, [buildCollection]);

  // ── Hover handler ─────────────────────────────────────────────────────────

  const handleMouseMove = useCallback(
    (e: { endPosition: Cartesian2 }) => {
      const viewer = viewerRef.current?.cesiumElement;
      if (!viewer || viewer.isDestroyed()) return;

      const picked = viewer.scene.pick(e.endPosition);
      if (picked?.id !== undefined && typeof picked.id === "number") {
        const sat = satellitesRef.current.find((s) => s.id === picked.id);
        if (sat) {
          const h = viewer.canvas.clientHeight;
          setTooltip({
            visible:  true,
            x:        e.endPosition.x,
            y:        h - e.endPosition.y,
            noradId:  sat.id,
            name:     sat.name,
            regime:   sat.regime,
            altKm:    sat.alt_km,
            speedKms: sat.speed,
          });
          viewer.canvas.style.cursor = "crosshair";
          return;
        }
      }
      setTooltip((t) => ({ ...t, visible: false }));
      viewer.canvas.style.cursor = "default";
    },
    [],
  );

  // ── Click handler — detail panel ──────────────────────────────────────────

  const handleClick = useCallback(async (e: { position: Cartesian2 }) => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || viewer.isDestroyed()) return;

    const picked = viewer.scene.pick(e.position);
    if (typeof picked?.id === "number") {
      setLoadingDetail(true);
      try {
        const detail = await fetchSatelliteDetail(picked.id);
        setSelectedSat(detail);
      } catch {
        setSelectedSat(null);
      } finally {
        setLoadingDetail(false);
      }
    } else {
      setSelectedSat(null);
    }
  }, []);

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      const viewer = viewerRef.current?.cesiumElement;
      if (viewer && !viewer.isDestroyed()) {
        if (collRef.current) {
          viewer.scene.primitives.remove(collRef.current);
          collRef.current.destroy();
        }
      }
    };
  }, []);

  // ── Viewer creation options (stable reference — never changes) ────────────

  const viewerOptions = useMemo(() => ({
    animation:            false,
    baseLayerPicker:      false,
    fullscreenButton:     false,
    geocoder:             false,
    homeButton:           false,
    infoBox:              false,
    navigationHelpButton: false,
    sceneModePicker:      false,
    selectionIndicator:   false,
    timeline:             false,
    skyBox:               false as false,
    skyAtmosphere:        undefined as undefined,
  }), []);

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="relative h-full w-full">

      {/* ── Cesium Viewer ──────────────────────────────────────────────────── */}
      <Viewer
        ref={viewerRef}
        full
        {...viewerOptions}
        style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
      >
        <Scene />

        {/* Interaction events */}
        <ScreenSpaceEventHandler>
          <ScreenSpaceEvent
            type={ScreenSpaceEventType.MOUSE_MOVE}
            action={handleMouseMove as Parameters<typeof ScreenSpaceEvent>[0]["action"]}
          />
          <ScreenSpaceEvent
            type={ScreenSpaceEventType.LEFT_CLICK}
            action={handleClick as Parameters<typeof ScreenSpaceEvent>[0]["action"]}
          />
        </ScreenSpaceEventHandler>

        {/* Conjunction markers — Entity per CDM (always small count) */}
        {showConjunctions && conjunctions.map((cdm) => {
          const primary = satellitesRef.current.find((s) => s.id === cdm.primary.norad);
          if (!primary) return null;
          return (
            <Entity
              key={cdm.conjunction_id}
              position={toCartesian3(primary.lon, primary.lat, primary.alt_km)}
              point={{
                pixelSize:       10,
                color:           CONJUNCTION_COLOR[cdm.risk_level] ?? CONJUNCTION_COLOR.white,
                outlineColor:    Color.BLACK,
                outlineWidth:    1,
                heightReference: HeightReference.NONE,
              }}
            />
          );
        })}
      </Viewer>

      {/* ── Loading overlay ─────────────────────────────────────────────────── */}
      {loadState === "loading" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-space-midnight/80 z-10">
          <div className="text-center">
            <div className="mb-2 h-1 w-48 overflow-hidden rounded-full bg-space-surface mx-auto">
              <div className="h-full w-3/5 animate-pulse rounded-full bg-[var(--color-accent-indigo)]" />
            </div>
            <span className="section-label">LOADING ORBITAL CATALOG</span>
          </div>
        </div>
      )}

      {/* ── Error overlay ───────────────────────────────────────────────────── */}
      {loadState === "error" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center z-10">
          <div className="rounded border border-[var(--color-accent-amber)] bg-space-navy/90 px-6 py-4 text-center">
            <div className="section-label mb-1" style={{ color: "var(--color-accent-amber)" }}>
              DIGITAL TWIN UNAVAILABLE
            </div>
            <div className="font-mono text-[11px] text-space-muted">
              Backend not initialised — run catalog sync &amp; propagation first.
            </div>
          </div>
        </div>
      )}

      {/* ── Camera preset toolbar (left) ────────────────────────────────────── */}
      <div className="absolute left-3 top-3 z-20 flex flex-col gap-1">
        {(Object.keys(CAMERA_PRESETS) as CameraPreset[]).map((preset) => (
          <button
            key={preset}
            onClick={() => flyToPreset(preset)}
            className={[
              "rounded border px-2 py-1 font-mono text-[9px] uppercase tracking-wider transition-colors",
              "hover:border-[var(--color-accent-indigo)] hover:text-space-text",
              activePreset === preset
                ? "border-[var(--color-accent-indigo)] bg-[var(--color-accent-indigo-glow)] text-space-accent"
                : "border-space-border bg-space-midnight/80 text-space-muted",
            ].join(" ")}
          >
            {preset}
          </button>
        ))}
      </div>

      {/* ── Filter controls (bottom-left) ───────────────────────────────────── */}
      <div className="absolute bottom-3 left-3 z-20 flex flex-col gap-1">
        {(
          [
            { key: "showLEO"    as const, label: "LEO",    color: "var(--color-accent-indigo)" },
            { key: "showMEO"    as const, label: "MEO",    color: "var(--color-accent-amber)" },
            { key: "showGEO"    as const, label: "GEO",    color: "var(--color-accent-green)" },
            { key: "showDebris" as const, label: "DEBRIS", color: "var(--color-text-tertiary)" },
            { key: "showPayload"as const, label: "PAY",    color: "var(--color-text-secondary)" },
          ]
        ).map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => applyFilter({ ...filter, [key]: !filter[key] })}
            className="flex items-center gap-1.5 rounded border border-space-border bg-space-midnight/80 px-2 py-0.5"
          >
            <span
              className="inline-block h-2 w-2 rounded-full transition-colors"
              style={{ backgroundColor: filter[key] ? color : "var(--color-space-border-strong)" }}
            />
            <span className="font-mono text-[9px] text-space-muted">{label}</span>
          </button>
        ))}
      </div>

      {/* ── Regime legend (bottom-right) ────────────────────────────────────── */}
      <div className="absolute bottom-3 right-3 z-20 rounded border border-space-border bg-space-midnight/90 px-3 py-2">
        <div className="section-label mb-1.5">REGIME</div>
        {[
          { label: "VLEO / LEO / SSO", color: "var(--color-accent-indigo)" },
          { label: "MEO",              color: "var(--color-accent-amber)" },
          { label: "GEO / GTO",        color: "var(--color-accent-green)" },
          { label: "HEO / Cislunar",   color: "var(--color-accent-red)" },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1.5 py-0.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="font-mono text-[9px] text-space-muted">{label}</span>
          </div>
        ))}
        {showConjunctions && (
          <>
            <div className="my-1 border-t border-space-border" />
            {[
              { label: "RED alert",    color: "var(--color-accent-red)" },
              { label: "YELLOW watch", color: "var(--color-accent-amber)" },
            ].map(({ label, color }) => (
              <div key={label} className="flex items-center gap-1.5 py-0.5">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full border-2"
                  style={{ borderColor: color }}
                />
                <span className="font-mono text-[9px] text-space-muted">{label}</span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* ── Status badges (top-right) ───────────────────────────────────────── */}
      <div className="absolute right-3 top-3 z-20 flex flex-col items-end gap-1">
        {loadState === "loaded" && (
          <div className="rounded border border-space-border bg-space-midnight/90 px-2 py-1">
            <span className="font-mono text-[10px] text-space-text">
              {satCount.toLocaleString()} OBJECTS
            </span>
          </div>
        )}
        {lastEpoch && (
          <div className="rounded border border-space-border bg-space-midnight/80 px-2 py-0.5">
            <span className="font-mono text-[9px] text-space-muted">
              {new Date(lastEpoch).toISOString().slice(11, 19)} UTC
            </span>
          </div>
        )}
      </div>

      {/* ── Hover tooltip ───────────────────────────────────────────────────── */}
      {tooltip.visible && (
        <div
          className="pointer-events-none absolute z-30 rounded border border-space-border bg-space-elevated px-3 py-2 shadow-panel"
          style={{ left: tooltip.x + 14, bottom: tooltip.y + 8 }}
        >
          <div className="mb-1 font-display text-[11px] font-semibold text-space-text">
            {tooltip.name || `NORAD-${tooltip.noradId}`}
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            {[
              ["NORAD",    tooltip.noradId.toString()],
              ["REGIME",   tooltip.regime],
              ["ALT km",   tooltip.altKm.toFixed(1)],
              ["SPD km/s", tooltip.speedKms.toFixed(3)],
            ].map(([label, value]) => (
              <div key={label} className="contents">
                <span className="font-mono text-[9px] text-space-muted">{label}</span>
                <span className="data-value text-[9px]">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Selection detail panel ──────────────────────────────────────────── */}
      {(selectedSat || loadingDetail) && (
        <div className="absolute right-3 top-28 z-30 w-64 rounded border border-space-border bg-space-elevated shadow-panel">
          <div className="flex items-center justify-between border-b border-space-border px-3 py-2">
            <span className="section-label">OBJECT DETAIL</span>
            <button
              className="font-mono text-[11px] text-space-muted hover:text-space-text"
              onClick={() => { setSelectedSat(null); setLoadingDetail(false); }}
            >
              ×
            </button>
          </div>

          {loadingDetail && !selectedSat && (
            <div className="space-y-1.5 p-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-4 animate-pulse rounded bg-space-surface" />
              ))}
            </div>
          )}

          {selectedSat && (
            <div className="p-3">
              {/* Identity */}
              <div className="mb-2.5">
                <div className="font-display text-sm font-semibold text-space-text leading-tight">
                  {selectedSat.name || `NORAD-${selectedSat.norad_id}`}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="font-mono text-[9px] text-space-muted">
                    NORAD {selectedSat.norad_id}
                  </span>
                  <span
                    className="rounded px-1.5 py-0.5 font-mono text-[8px] font-bold uppercase"
                    style={{
                      color:           "var(--color-accent-indigo-bright)",
                      backgroundColor: "var(--color-accent-indigo-glow)",
                    }}
                  >
                    {selectedSat.orbital_regime}
                  </span>
                </div>
              </div>

              {/* Orbital data */}
              <div className="space-y-1">
                {[
                  { label: "Altitude",    value: `${selectedSat.altitude_km.toFixed(1)} km` },
                  { label: "Speed",       value: `${selectedSat.speed_kms.toFixed(3)} km/s` },
                  { label: "Latitude",    value: `${selectedSat.latitude_deg.toFixed(4)}°` },
                  { label: "Longitude",   value: `${selectedSat.longitude_deg.toFixed(4)}°` },
                  { label: "Inclination", value: `${(selectedSat.inclination_deg ?? 0).toFixed(2)}°` },
                  { label: "Perigee",     value: selectedSat.perigee_km  ? `${selectedSat.perigee_km.toFixed(1)} km`  : "—" },
                  { label: "Apogee",      value: selectedSat.apogee_km   ? `${selectedSat.apogee_km.toFixed(1)} km`   : "—" },
                  { label: "Period",      value: selectedSat.period_min   ? `${selectedSat.period_min.toFixed(2)} min` : "—" },
                ].map(({ label, value }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="font-mono text-[9px] text-space-muted">{label}</span>
                    <span className="data-value text-[10px]">{value}</span>
                  </div>
                ))}
              </div>

              {/* ECI position */}
              <div className="mt-2.5 border-t border-space-border pt-2">
                <div className="section-label mb-1">ECI POSITION km</div>
                <div className="font-mono text-[9px] text-space-muted break-all">
                  [{selectedSat.position_eci_km.map((v) => v.toFixed(0)).join(", ")}]
                </div>
              </div>

              {/* Epoch */}
              <div className="mt-1.5 font-mono text-[8px] text-[var(--color-text-tertiary)]">
                {new Date(selectedSat.epoch).toISOString().slice(0, 19).replace("T", " ")} UTC
              </div>

              {/* Propagation health flag */}
              {!selectedSat.propagation_ok && (
                <div
                  className="mt-2 rounded px-2 py-1 font-mono text-[9px]"
                  style={{
                    color:           "var(--color-accent-amber)",
                    backgroundColor: "var(--color-accent-amber-glow)",
                  }}
                >
                  ⚠ PROPAGATION DEGRADED
                </div>
              )}
            </div>
          )}
        </div>
      )}

    </div>
  );
}
