"use client";
/**
 * ORBITIQ-X — OrbitalGlobe (v0.4.0)
 * ====================================
 * Animated CSS/SVG globe with:
 * - Auto-rotating Earth with continent outlines
 * - Orbital rings at LEO / MEO / GEO altitudes
 * - Animated satellite dots in correct orbits
 * - Ground station markers
 * - Real-time satellite count from Digital Twin
 */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCatalogHealth } from "@/lib/api";

export interface OrbitalGlobeProps {
  className?: string;
  style?: React.CSSProperties;
  defaultObjectTypes?: string[];
  showConjunctions?: boolean;
  showGroundTracks?: boolean;
  autoRotate?: boolean;
}

// Satellites orbiting at different altitudes and speeds
const ORBITAL_SATS = [
  // LEO - fast, many
  { id:"l1",  rx:210, ry:58,  tilt:-15, period:6,  size:2,   color:"#818cf8", phase:0   },
  { id:"l2",  rx:210, ry:58,  tilt:-15, period:6,  size:2,   color:"#818cf8", phase:0.3 },
  { id:"l3",  rx:210, ry:58,  tilt:-15, period:6,  size:2,   color:"#818cf8", phase:0.6 },
  { id:"l4",  rx:195, ry:54,  tilt:25,  period:5.5,size:1.5, color:"#818cf8", phase:0.15},
  { id:"l5",  rx:195, ry:54,  tilt:25,  period:5.5,size:1.5, color:"#818cf8", phase:0.5 },
  { id:"l6",  rx:195, ry:54,  tilt:25,  period:5.5,size:1.5, color:"#818cf8", phase:0.85},
  { id:"l7",  rx:220, ry:50,  tilt:-35, period:7,  size:2,   color:"#818cf8", phase:0.2 },
  { id:"l8",  rx:220, ry:50,  tilt:-35, period:7,  size:2,   color:"#818cf8", phase:0.7 },
  { id:"l9",  rx:205, ry:60,  tilt:50,  period:6.5,size:1.5, color:"#7dd3fc", phase:0.1 },
  { id:"l10", rx:205, ry:60,  tilt:50,  period:6.5,size:1.5, color:"#7dd3fc", phase:0.6 },
  // SSO - polar
  { id:"s1",  rx:45,  ry:225, tilt:0,   period:8,  size:2,   color:"#7dd3fc", phase:0   },
  { id:"s2",  rx:45,  ry:225, tilt:0,   period:8,  size:2,   color:"#7dd3fc", phase:0.5 },
  // MEO - GPS altitude
  { id:"m1",  rx:265, ry:72,  tilt:20,  period:16, size:2.5, color:"#34d399", phase:0   },
  { id:"m2",  rx:265, ry:72,  tilt:20,  period:16, size:2.5, color:"#34d399", phase:0.33},
  { id:"m3",  rx:265, ry:72,  tilt:20,  period:16, size:2.5, color:"#34d399", phase:0.66},
  { id:"m4",  rx:265, ry:72,  tilt:-20, period:14, size:2.5, color:"#34d399", phase:0.17},
  { id:"m5",  rx:265, ry:72,  tilt:-20, period:14, size:2.5, color:"#34d399", phase:0.5 },
  // GEO - slow equatorial
  { id:"g1",  rx:320, ry:12,  tilt:0,   period:60, size:3,   color:"#fbbf24", phase:0   },
  { id:"g2",  rx:320, ry:12,  tilt:0,   period:60, size:3,   color:"#fbbf24", phase:0.25},
  { id:"g3",  rx:320, ry:12,  tilt:0,   period:60, size:3,   color:"#fbbf24", phase:0.5 },
  { id:"g4",  rx:320, ry:12,  tilt:0,   period:60, size:3,   color:"#fbbf24", phase:0.75},
];

// Ground stations
const GROUND_STATIONS = [
  { name:"KSC",   angle:-80, lat:28,  color:"#34d399" },
  { name:"ESOC",  angle:8,   lat:50,  color:"#7dd3fc" },
  { name:"ISRO",  angle:80,  lat:13,  color:"#fbbf24" },
  { name:"JAXA",  angle:135, lat:36,  color:"#c084fc" },
];

function AnimatedSat({ sat, time }: { sat: typeof ORBITAL_SATS[0]; time: number }) {
  const angle = ((time / sat.period + sat.phase) % 1) * Math.PI * 2;
  const tiltR = (sat.tilt * Math.PI) / 180;

  // Ellipse point
  const ex = sat.rx * Math.cos(angle);
  const ey = sat.ry * Math.sin(angle);

  // Apply tilt rotation (rotate around X axis)
  const cx = 350, cy = 320; // SVG center
  const rotatedY = ey * Math.cos(tiltR) - 0 * Math.sin(tiltR);
  const rotatedZ = ey * Math.sin(tiltR) + 0 * Math.cos(tiltR);

  const x = cx + ex;
  const y = cy + rotatedY;
  const depth = rotatedZ + (ex * Math.sin(tiltR * 0.3));

  // Depth-based opacity (behind globe = dimmer)
  const isBehind = depth > sat.ry * 0.5;
  const opacity = isBehind ? 0.25 : 0.95;

  return (
    <g>
      {!isBehind && (
        <circle cx={x} cy={y} r={sat.size + 1.5} fill={sat.color} opacity={0.15} />
      )}
      <circle cx={x} cy={y} r={sat.size} fill={sat.color} opacity={opacity} />
    </g>
  );
}

export function OrbitalGlobe({ className, style, autoRotate = true }: OrbitalGlobeProps) {
  const [time, setTime] = useState(0);
  const animRef = useRef<number>(0);
  const lastRef = useRef<number>(0);

  const { data: health } = useQuery({
    queryKey: ["catalog-health"],
    queryFn: fetchCatalogHealth,
    staleTime: 60_000,
  });

  useEffect(() => {
    const tick = (ts: number) => {
      if (lastRef.current) {
        const dt = (ts - lastRef.current) / 1000;
        setTime(t => t + dt * 0.15); // speed factor
      }
      lastRef.current = ts;
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  // Earth rotation angle
  const earthRotation = (time * 2) % 360;

  return (
    <div
      className={className}
      style={{
        position: "relative", width: "100%", height: "100%",
        background: "radial-gradient(ellipse at 25% 30%, #0a1628 0%, #060d16 50%, #020508 100%)",
        overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center",
        ...style,
      }}
    >
      {/* Star field */}
      <svg style={{ position:"absolute", inset:0, width:"100%", height:"100%", pointerEvents:"none" }}>
        {Array.from({ length: 120 }, (_, i) => {
          const seed = i * 2654435761;
          const x = ((seed * 1.3) % 100);
          const y = ((seed * 0.7) % 100);
          const s = 0.5 + (seed % 15) / 10;
          const op = 0.2 + (seed % 6) / 10;
          return <circle key={i} cx={`${x}%`} cy={`${y}%`} r={s} fill="white" opacity={op} />;
        })}
      </svg>

      {/* Main globe SVG */}
      <svg viewBox="0 0 700 640" style={{ width:"100%", height:"100%", maxWidth:900 }}>

        {/* Orbital rings - GEO */}
        <ellipse cx="350" cy="320" rx="320" ry="12" fill="none"
          stroke="rgba(251,191,36,0.15)" strokeWidth="0.8" strokeDasharray="4 6"/>

        {/* Orbital rings - MEO */}
        <ellipse cx="350" cy="320" rx="265" ry="72" fill="none"
          stroke="rgba(52,211,153,0.12)" strokeWidth="0.6" strokeDasharray="3 5"/>
        <ellipse cx="350" cy="320" rx="265" ry="72" fill="none"
          stroke="rgba(52,211,153,0.08)" strokeWidth="0.6"
          transform="rotate(20 350 320)" strokeDasharray="3 5"/>

        {/* Orbital rings - LEO */}
        <ellipse cx="350" cy="320" rx="210" ry="58" fill="none"
          stroke="rgba(99,102,241,0.18)" strokeWidth="0.7" strokeDasharray="2 4"
          transform="rotate(-15 350 320)"/>
        <ellipse cx="350" cy="320" rx="195" ry="54" fill="none"
          stroke="rgba(99,102,241,0.15)" strokeWidth="0.6" strokeDasharray="2 4"
          transform="rotate(25 350 320)"/>

        {/* SSO ring - near-polar */}
        <ellipse cx="350" cy="320" rx="45" ry="225" fill="none"
          stroke="rgba(125,211,252,0.12)" strokeWidth="0.7" strokeDasharray="2 4"/>

        {/* Earth - atmosphere glow */}
        <circle cx="350" cy="320" r="145"
          fill="none" stroke="rgba(56,189,248,0.12)" strokeWidth="8"/>

        {/* Earth - ocean base */}
        <circle cx="350" cy="320" r="140"
          fill="url(#earthGrad)"/>

        {/* Earth - rotating continent overlay */}
        <g clipPath="url(#globeClip)">
          <g transform={`translate(350,320)`}>
            {/* Simplified continent shapes as rotating paths */}
            {/* North America */}
            <g transform={`rotate(${earthRotation})`}>
              <ellipse cx="-80" cy="-40" rx="35" ry="45" fill="rgba(34,197,94,0.25)" />
              <ellipse cx="-70" cy="20"  rx="20" ry="25" fill="rgba(34,197,94,0.2)" />
              {/* Europe */}
              <ellipse cx="30"  cy="-55" rx="22" ry="18" fill="rgba(34,197,94,0.22)" />
              {/* Asia */}
              <ellipse cx="80"  cy="-40" rx="50" ry="30" fill="rgba(34,197,94,0.25)" />
              <ellipse cx="100" cy="-15" rx="30" ry="20" fill="rgba(34,197,94,0.2)" />
              {/* Africa */}
              <ellipse cx="20"  cy="10"  rx="25" ry="40" fill="rgba(34,197,94,0.22)" />
              {/* South America */}
              <ellipse cx="-60" cy="55"  rx="20" ry="35" fill="rgba(34,197,94,0.2)" />
              {/* Australia */}
              <ellipse cx="110" cy="55"  rx="20" ry="15" fill="rgba(34,197,94,0.18)" />
            </g>
            {/* Grid lines */}
            <circle cx="0" cy="0" r="140" fill="none" stroke="rgba(99,102,241,0.06)" strokeWidth="0.5"/>
            {[-60,-30,0,30,60].map(lat => {
              const y = lat / 90 * 140;
              const rx = Math.sqrt(Math.max(0, 140*140 - y*y));
              return <ellipse key={lat} cx="0" cy={y} rx={rx} ry={rx*0.15} fill="none" stroke="rgba(99,102,241,0.06)" strokeWidth="0.4"/>;
            })}
            {[0,30,60,90,120,150].map((lon, i) => (
              <line key={lon} x1="0" y1="-140" x2="0" y2="140"
                fill="none" stroke="rgba(99,102,241,0.05)" strokeWidth="0.4"
                transform={`rotate(${lon})`}/>
            ))}
          </g>
        </g>

        {/* Earth - terminator (day/night) */}
        <clipPath id="globeClip">
          <circle cx="350" cy="320" r="140"/>
        </clipPath>

        {/* Earth - terminator shadow */}
        <path d={`M 350 180 A 140 140 0 0 0 350 460 Z`}
          fill="rgba(0,0,0,0.35)" clipPath="url(#globeClip)"/>

        {/* Earth - atmosphere rim */}
        <circle cx="350" cy="320" r="140"
          fill="none" stroke="rgba(56,189,248,0.3)" strokeWidth="2"/>

        {/* Gradient defs */}
        <defs>
          <radialGradient id="earthGrad" cx="38%" cy="35%" r="65%">
            <stop offset="0%"   stopColor="#0e3a5e"/>
            <stop offset="40%"  stopColor="#0a2545"/>
            <stop offset="100%" stopColor="#061428"/>
          </radialGradient>
        </defs>

        {/* Ground stations */}
        {GROUND_STATIONS.map(gs => {
          const lonR = ((gs.angle + earthRotation) * Math.PI) / 180;
          const latR = (gs.lat * Math.PI) / 180;
          const x = 350 + 140 * Math.cos(latR) * Math.sin(lonR);
          const y = 320 - 140 * Math.sin(latR);
          const visible = Math.cos(latR) * Math.cos(lonR) > 0;
          if (!visible) return null;
          return (
            <g key={gs.name}>
              <circle cx={x} cy={y} r={4} fill="none" stroke={gs.color} strokeWidth="1.5" opacity="0.8"/>
              <circle cx={x} cy={y} r={2} fill={gs.color} opacity="0.9"/>
              <text x={x+6} y={y+3} fill={gs.color} fontSize="7" fontFamily="monospace" opacity="0.7">{gs.name}</text>
            </g>
          );
        })}

        {/* Animated satellites */}
        {ORBITAL_SATS.map(sat => (
          <AnimatedSat key={sat.id} sat={sat} time={time} />
        ))}

        {/* Satellite count overlay */}
        <g>
          <rect x="14" y="10" width="160" height="22" rx="2" fill="rgba(6,13,22,0.7)" stroke="rgba(99,102,241,0.2)" strokeWidth="0.5"/>
          <text x="22" y="25" fill="rgba(99,102,241,0.5)" fontSize="8" fontFamily="monospace" letterSpacing="1">TRACKING</text>
          <text x="75" y="25" fill="rgba(129,140,248,0.9)" fontSize="8" fontFamily="monospace" fontWeight="bold">
            {(health?.database_satellite_count ?? 29198).toLocaleString()}
          </text>
          <text x="112" y="25" fill="rgba(99,102,241,0.5)" fontSize="8" fontFamily="monospace" letterSpacing="1">RSOs</text>
        </g>

        {/* Legend */}
        <g transform="translate(14, 580)">
          {[
            { color:"#818cf8", label:"LEO" },
            { color:"#34d399", label:"MEO/GPS" },
            { color:"#fbbf24", label:"GEO" },
            { color:"#7dd3fc", label:"SSO" },
          ].map(({ color, label }, i) => (
            <g key={label} transform={`translate(${i * 80}, 0)`}>
              <circle cx="5" cy="4" r="3" fill={color} opacity="0.9"/>
              <text x="12" y="8" fill="rgba(148,163,184,0.6)" fontSize="8" fontFamily="monospace">{label}</text>
            </g>
          ))}
        </g>

      </svg>

      {/* Bottom label */}
      <div style={{
        position:"absolute", bottom:16, left:"50%", transform:"translateX(-50%)",
        fontFamily:"monospace", fontSize:"9px", color:"rgba(99,102,241,0.35)",
        letterSpacing:"0.15em", whiteSpace:"nowrap",
      }}>
        ORBITAL SURVEILLANCE ACTIVE
      </div>
    </div>
  );
}
