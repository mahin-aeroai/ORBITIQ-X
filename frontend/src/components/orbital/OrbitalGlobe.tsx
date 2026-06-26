"use client";
/**
 * ORBITIQ-X — OrbitalGlobe (Static Placeholder)
 * Globe temporarily disabled — Cesium WebGL initialization 
 * causes client-side crashes. Static visualization shown instead.
 */

export interface OrbitalGlobeProps {
  className?: string;
  style?: React.CSSProperties;
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
        gap: 12,
        overflow: "hidden",
        ...style,
      }}
    >
      {/* Star field */}
      {Array.from({length: 80}).map((_, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            width: Math.random() * 2 + 1,
            height: Math.random() * 2 + 1,
            borderRadius: "50%",
            background: "white",
            opacity: Math.random() * 0.7 + 0.1,
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
          }}
        />
      ))}

      {/* Globe outline */}
      <div style={{
        width: 280,
        height: 280,
        borderRadius: "50%",
        border: "1px solid rgba(99,102,241,0.3)",
        boxShadow: "0 0 60px rgba(99,102,241,0.1), inset 0 0 60px rgba(99,102,241,0.05)",
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}>
        {/* Orbit rings */}
        {[120, 160, 200].map((size, i) => (
          <div key={i} style={{
            position: "absolute",
            width: size,
            height: size / 3,
            border: `1px solid rgba(99,102,241,${0.15 - i * 0.03})`,
            borderRadius: "50%",
            transform: `rotateX(${60 + i * 10}deg)`,
          }} />
        ))}
        <div style={{
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 10,
          color: "rgba(148,163,184,0.4)",
          letterSpacing: "0.2em",
          textAlign: "center",
        }}>
          ORBITAL<br/>TRACKING<br/>ACTIVE
        </div>
      </div>

      <div style={{
        fontFamily: "var(--font-mono, monospace)",
        fontSize: 9,
        color: "rgba(99,102,241,0.4)",
        letterSpacing: "0.15em",
        textAlign: "center",
      }}>
        3D GLOBE REQUIRES CHROME + WEBGL
      </div>
    </div>
  );
}
