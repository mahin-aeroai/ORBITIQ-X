"use client";
/**
 * ORBITIQ-X — OrbitalGlobe (Static Placeholder)
 * Cesium WebGL globe disabled — static SVG visualization shown instead.
 */

export interface OrbitalGlobeProps {
  className?: string;
  style?: React.CSSProperties;
  // Legacy props from Cesium implementation — accepted but ignored
  defaultObjectTypes?: string[];
  showConjunctions?: boolean;
  showGroundTracks?: boolean;
  autoRotate?: boolean;
}

export function OrbitalGlobe({ className, style }: OrbitalGlobeProps) {
  return (
    <div
      className={className}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: "radial-gradient(ellipse at 30% 40%, #0d2137 0%, #060d16 60%, #020508 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: "12px",
        overflow: "hidden",
        ...style,
      }}
    >
      <svg width="300" height="300" viewBox="0 0 300 300" style={{opacity: 0.8}}>
        {/* Stars */}
        <circle cx="20" cy="30" r="1" fill="white" opacity="0.4"/>
        <circle cx="80" cy="15" r="1.5" fill="white" opacity="0.6"/>
        <circle cx="250" cy="40" r="1" fill="white" opacity="0.3"/>
        <circle cx="270" cy="90" r="1.5" fill="white" opacity="0.5"/>
        <circle cx="40" cy="200" r="1" fill="white" opacity="0.4"/>
        <circle cx="260" cy="220" r="1" fill="white" opacity="0.6"/>
        <circle cx="15" cy="260" r="1.5" fill="white" opacity="0.3"/>
        <circle cx="285" cy="270" r="1" fill="white" opacity="0.5"/>
        <circle cx="150" cy="20" r="1" fill="white" opacity="0.4"/>
        <circle cx="200" cy="280" r="1.5" fill="white" opacity="0.3"/>
        <circle cx="50" cy="120" r="1" fill="white" opacity="0.5"/>
        <circle cx="280" cy="150" r="1" fill="white" opacity="0.4"/>
        {/* Globe circle */}
        <circle cx="150" cy="150" r="100" fill="none" stroke="rgba(99,102,241,0.25)" strokeWidth="1"/>
        {/* Orbit rings */}
        <ellipse cx="150" cy="150" rx="100" ry="30" fill="none" stroke="rgba(99,102,241,0.15)" strokeWidth="0.8"/>
        <ellipse cx="150" cy="150" rx="130" ry="40" fill="none" stroke="rgba(99,102,241,0.1)" strokeWidth="0.8"/>
        <ellipse cx="150" cy="150" rx="60" ry="20" fill="none" stroke="rgba(99,102,241,0.12)" strokeWidth="0.8"/>
        {/* Grid lines */}
        <line x1="50" y1="150" x2="250" y2="150" stroke="rgba(99,102,241,0.1)" strokeWidth="0.5"/>
        <line x1="150" y1="50" x2="150" y2="250" stroke="rgba(99,102,241,0.1)" strokeWidth="0.5"/>
        {/* Satellite dots */}
        <circle cx="220" cy="110" r="2.5" fill="rgba(99,102,241,0.8)"/>
        <circle cx="90" cy="80" r="2" fill="rgba(34,197,94,0.8)"/>
        <circle cx="190" cy="200" r="2" fill="rgba(99,102,241,0.6)"/>
        <circle cx="80" cy="190" r="1.5" fill="rgba(251,191,36,0.8)"/>
        <circle cx="230" cy="180" r="2" fill="rgba(99,102,241,0.7)"/>
        {/* Center glow */}
        <circle cx="150" cy="150" r="8" fill="rgba(99,102,241,0.15)"/>
        <circle cx="150" cy="150" r="4" fill="rgba(99,102,241,0.3)"/>
        {/* Label */}
        <text x="150" y="158" textAnchor="middle" fill="rgba(148,163,184,0.4)" fontSize="8" fontFamily="monospace" letterSpacing="2">TRACKING</text>
      </svg>
      <div style={{
        fontFamily: "monospace",
        fontSize: "9px",
        color: "rgba(99,102,241,0.4)",
        letterSpacing: "0.15em",
        textAlign: "center",
      }}>
        ORBITAL SURVEILLANCE ACTIVE
      </div>
    </div>
  );
}
