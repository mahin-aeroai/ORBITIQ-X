const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, LevelFormat, BorderStyle,
  WidthType, ShadingType, PageNumber, PageBreak, TabStopType,
  TabStopPosition, PositionalTab, PositionalTabAlignment,
  PositionalTabRelativeTo
} = require('docx');
const fs = require('fs');

// ── Color palette (ORBITIQ-X Mission Control Dark) ─────────────
const INDIGO   = "5B52C4";  // electric indigo
const NAVY     = "0D1B2A";  // deep space
const TEAL     = "1D9E75";  // phosphor mint
const AMBER    = "BA7517";  // phosphor amber
const RED      = "A32D2D";  // alert red
const GRAY     = "5F5E5A";
const LGRAY    = "D3D1C7";
const WHITE    = "FFFFFF";
const OFFWHITE = "F5F4F0";

// ── Helpers ────────────────────────────────────────────────────
const br  = () => new Paragraph({ children: [] });
const pb  = () => new Paragraph({ children: [new PageBreak()] });

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  children: [new TextRun({ text, bold: true, color: WHITE, font: "Arial", size: 36 })],
  shading: { fill: NAVY, type: ShadingType.CLEAR },
  spacing: { before: 480, after: 240 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: INDIGO, space: 1 } }
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  children: [new TextRun({ text, bold: true, color: NAVY, font: "Arial", size: 28 })],
  spacing: { before: 360, after: 120 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 3, color: INDIGO, space: 1 } }
});

const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  children: [new TextRun({ text, bold: true, color: INDIGO, font: "Arial", size: 24 })],
  spacing: { before: 240, after: 80 }
});

const body = (text) => new Paragraph({
  children: [new TextRun({ text, size: 22, font: "Arial" })],
  spacing: { after: 120 },
  alignment: AlignmentType.JUSTIFIED
});

const bodyBold = (label, text) => new Paragraph({
  children: [
    new TextRun({ text: label + " ", bold: true, size: 22, font: "Arial", color: NAVY }),
    new TextRun({ text, size: 22, font: "Arial" })
  ],
  spacing: { after: 100 },
  alignment: AlignmentType.JUSTIFIED
});

const bullet = (text, level = 0) => new Paragraph({
  numbering: { reference: "bullets", level },
  children: [new TextRun({ text, size: 22, font: "Arial" })],
  spacing: { after: 80 }
});

const numbered = (text, level = 0) => new Paragraph({
  numbering: { reference: "numbers", level },
  children: [new TextRun({ text, size: 22, font: "Arial" })],
  spacing: { after: 80 }
});

const caption = (text) => new Paragraph({
  children: [new TextRun({ text, size: 18, italics: true, color: GRAY, font: "Arial" })],
  alignment: AlignmentType.CENTER,
  spacing: { after: 200 }
});

const callout = (text) => new Paragraph({
  children: [new TextRun({ text, size: 22, italics: true, color: NAVY, font: "Arial" })],
  border: {
    left: { style: BorderStyle.THICK, size: 12, color: INDIGO, space: 4 }
  },
  spacing: { before: 120, after: 120 },
  indent: { left: 600 }
});

const metric = (label, value) => new Paragraph({
  children: [
    new TextRun({ text: label + ": ", bold: true, size: 22, font: "Arial", color: GRAY }),
    new TextRun({ text: value, bold: true, size: 28, font: "Arial", color: INDIGO })
  ],
  spacing: { after: 80 }
});

// ── Table helper ───────────────────────────────────────────────
const border = { style: BorderStyle.SINGLE, size: 1, color: LGRAY };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 100, bottom: 100, left: 140, right: 140 };

const headerCell = (text, w) => new TableCell({
  width: { size: w, type: WidthType.DXA },
  borders,
  margins: cellMargins,
  shading: { fill: NAVY, type: ShadingType.CLEAR },
  children: [new Paragraph({
    children: [new TextRun({ text, bold: true, size: 20, color: WHITE, font: "Arial" })],
    alignment: AlignmentType.CENTER
  })]
});

const dataCell = (text, w, shade = OFFWHITE) => new TableCell({
  width: { size: w, type: WidthType.DXA },
  borders,
  margins: cellMargins,
  shading: { fill: shade, type: ShadingType.CLEAR },
  children: [new Paragraph({
    children: [new TextRun({ text, size: 20, font: "Arial" })]
  })]
});

const boldDataCell = (text, w, shade = OFFWHITE) => new TableCell({
  width: { size: w, type: WidthType.DXA },
  borders,
  margins: cellMargins,
  shading: { fill: shade, type: ShadingType.CLEAR },
  children: [new Paragraph({
    children: [new TextRun({ text, bold: true, size: 20, font: "Arial", color: NAVY })]
  })]
});

const accentCell = (text, w) => new TableCell({
  width: { size: w, type: WidthType.DXA },
  borders,
  margins: cellMargins,
  shading: { fill: INDIGO, type: ShadingType.CLEAR },
  children: [new Paragraph({
    children: [new TextRun({ text, bold: true, size: 20, color: WHITE, font: "Arial" })],
    alignment: AlignmentType.CENTER
  })]
});

// ── Document ───────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 600, hanging: 360 } } }
        }, {
          level: 1, format: LevelFormat.BULLET, text: "\u25E6",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 960, hanging: 360 } } }
        }]
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 600, hanging: 360 } } }
        }]
      }
    ]
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: WHITE },
        paragraph: { spacing: { before: 480, after: 240 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: NAVY },
        paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 1 }
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: INDIGO },
        paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 2 }
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
      }
    },
    headers: {
      default: new Header({
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "ORBITIQ-X  |  Technical Vision Document  |  CONFIDENTIAL DRAFT", size: 16, color: GRAY, font: "Arial" })
            ],
            border: { bottom: { style: BorderStyle.SINGLE, size: 3, color: INDIGO, space: 1 } },
            spacing: { after: 100 }
          })
        ]
      })
    },
    footers: {
      default: new Footer({
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: "\u00A9 2026 ORBITIQ-X Project  |  Mahin Nandipa  |  Page ", size: 16, color: GRAY, font: "Arial" }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GRAY, font: "Arial" }),
              new TextRun({ text: " of ", size: 16, color: GRAY, font: "Arial" }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GRAY, font: "Arial" })
            ],
            border: { top: { style: BorderStyle.SINGLE, size: 3, color: INDIGO, space: 1 } },
            spacing: { before: 100 }
          })
        ]
      })
    },
    children: [

      // ── COVER PAGE ──────────────────────────────────────────
      new Paragraph({
        children: [],
        spacing: { before: 720 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "ORBITIQ-X", bold: true, size: 96, font: "Arial", color: INDIGO })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "The Aerospace Foundation Model", bold: true, size: 48, font: "Arial", color: NAVY })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 200 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "Technical Vision Document", size: 32, italics: true, font: "Arial", color: GRAY })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "Version 1.0  |  June 2026  |  CONFIDENTIAL DRAFT", size: 22, font: "Arial", color: GRAY })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 600 }
      }),
      new Paragraph({
        children: [new TextRun({
          text: "Converging Orbital Mechanics \u00B7 Artificial Intelligence \u00B7 Space Operations \u00B7 Knowledge Graphs \u00B7 Digital Twins \u00B7 Agentic Systems",
          size: 20, italics: true, font: "Arial", color: INDIGO
        })],
        alignment: AlignmentType.CENTER,
        border: {
          top: { style: BorderStyle.SINGLE, size: 4, color: INDIGO, space: 4 },
          bottom: { style: BorderStyle.SINGLE, size: 4, color: INDIGO, space: 4 }
        },
        spacing: { before: 200, after: 200 }
      }),
      new Paragraph({ children: [], spacing: { before: 400 } }),
      new Paragraph({
        children: [new TextRun({ text: "Mahin Nandipa", bold: true, size: 24, font: "Arial", color: NAVY })],
        alignment: AlignmentType.CENTER
      }),
      new Paragraph({
        children: [new TextRun({ text: "ML/AI Engineer  |  github.com/mahin-aeroai", size: 20, font: "Arial", color: GRAY })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 60 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "B.Tech Aerospace Engineering, VIT Bhopal  |  PG Certificate AI/ML, IIIT Hyderabad", size: 20, font: "Arial", color: GRAY })],
        alignment: AlignmentType.CENTER
      }),

      pb(),

      // ── 1. EXECUTIVE SUMMARY ───────────────────────────────
      h1("1. Executive Summary"),
      body("Humanity has placed more than 10,000 active satellites and 50,000 tracked debris objects into Earth orbit. The number doubles every four years. The tools that govern this domain \u2014 two-line element sets developed in 1957, SSA platforms that aggregate radar tracks, and general-purpose language models that know nothing of astrodynamics \u2014 were not designed for this scale, this complexity, or this consequence."),
      br(),
      body("ORBITIQ-X is the world's first Aerospace Foundation Model: a vertically integrated AI reasoning system that fuses orbital mechanics, knowledge graphs, agentic intelligence, and a living digital twin of Earth orbit into a single coherent platform. It does not bolt AI onto existing SSA tools. It rebuilds the reasoning layer from the ground up, treating space operations as a knowledge-intensive engineering discipline that demands physics-grounded, traceable, multi-agent AI."),
      br(),
      callout("ORBITIQ-X asks: what if every question about any object in orbit could be answered with the rigor of a NASA flight dynamics team, the breadth of a global research library, and the speed of a real-time software system?"),
      br(),
      body("This document describes the technical vision, architectural design, and 10-year research roadmap for ORBITIQ-X. It is written for an audience of aerospace engineers, AI researchers, mission operators, and technical strategists at organizations including NASA, ESA, ISRO, SpaceX, and aerospace-adjacent investment institutions."),

      br(), br(),

      // ── 2. VISION & MISSION ────────────────────────────────
      h1("2. Vision & Mission"),

      h2("2.1 Vision"),
      body("A world where no collision in Earth orbit is unforeseeable, where every mission decision is informed by the full depth of aerospace knowledge, and where the intelligence layer of space operations is as sophisticated as the vehicles it monitors."),
      br(),
      body("ORBITIQ-X envisions a future in which an aerospace operator can ask a plain-language question about any of the 50,000+ objects in orbit and receive, within seconds, an answer that synthesizes live tracking data, orbital physics, research literature, historical mission precedent, and real-time space weather \u2014 with full citation, quantified uncertainty, and an actionable recommendation."),

      h2("2.2 Mission"),
      bullet("Build the first foundation model for aerospace intelligence \u2014 a system that understands the physics, the history, the engineering, and the operational context of Earth orbit"),
      bullet("Create a living digital twin of Earth's orbital environment updated continuously from real tracking data, TLE feeds, CDM messages, and space weather sensors"),
      bullet("Deploy a multi-agent agentic intelligence layer that autonomously monitors conjunction risk, detects anomalies, and recommends mitigations"),
      bullet("Ground every AI-generated answer in traceable, cited aerospace engineering sources using a purpose-built knowledge graph and retrieval system"),
      bullet("Open-source the platform infrastructure to democratize access to advanced SSA intelligence for emerging space nations and academic institutions"),

      h2("2.3 Core Principles"),
      bodyBold("Physics First:", "All AI reasoning is bounded by orbital mechanics. No generated answer may contradict a validated propagation result. The model knows SGP4, knows J2, knows drag, and respects all of them."),
      bodyBold("Traceable Answers:", "Every factual claim is citation-backed. The system knows which NASA technical memorandum, which ESA report, which paper in Acta Astronautica supports each assertion."),
      bodyBold("Conservative by Default:", "When uncertainty is high, ORBITIQ-X says so. For safety-critical outputs (maneuver recommendations, reentry alerts), human confirmation is required before any action is taken."),
      bodyBold("Open Architecture:", "APIs, schemas, and data formats follow open standards. No vendor lock-in. Compatible with Space-Track, CelesTrak, NOAA SWPC, and emerging commercial SSA data providers."),

      pb(),

      // ── 3. PROBLEM STATEMENT ───────────────────────────────
      h1("3. Problem Statement"),

      h2("3.1 The Orbital Environment in 2026"),
      body("As of mid-2026, the United States Space Surveillance Network (SSN) tracks approximately 50,000 resident space objects (RSOs). Of these, roughly 8,000 are active payloads. The rest are rocket bodies, mission-related debris, and fragmentation objects from the 550+ breakup events recorded since Sputnik."),
      br(),
      body("The growth trajectory is unprecedented. In 2019, there were fewer than 2,000 active satellites. In 2026, there are more than 8,000. By 2030, LEO alone may host 100,000 active satellites across Starlink, OneWeb, Amazon Kuiper, and dozens of national constellations. The orbital environment is approaching a phase transition: from a place where collisions are rare to a place where collision risk is a daily operational concern for every satellite operator on Earth."),

      h2("3.2 The Intelligence Gap"),
      body("The analytical tools available to the space operations community have not kept pace with this growth. The current state of practice suffers from three fundamental deficits:"),
      br(),
      bodyBold("The Data Fragmentation Problem:", "Orbital data lives in silos. Tracking data is at Space-Track. Space weather is at NOAA SWPC. Research literature is in NASA NTRS, ESA's publication archive, arXiv, and journal publishers. Operator documentation is on internal servers. No system synthesizes these sources at query time into a coherent answer."),
      bodyBold("The Reasoning Gap:", "Existing SSA tools are data pipelines, not reasoning systems. They can tell you that Pc = 1.3\u00D710\u207B\u00B3 for a given conjunction event. They cannot tell you why, what the historical analogue is, whether the covariance is reliable, what the maneuver trade-space looks like, or whether space weather is degrading the accuracy of the prediction. That chain of reasoning requires a domain expert."),
      bodyBold("The Scale Problem:", "A human analyst can monitor perhaps 50 conjunction events per day. ORBITIQ-X monitors 50,000 objects and generates hundreds of CDMs in every screening cycle. The human analyst is the bottleneck in every SSA organization on Earth."),

      h2("3.3 The Failure Mode"),
      body("The Iridium-Cosmos collision of 2009 was predicted. The conjunction had been flagged. The maneuver decision was not made. One barrier was the speed of the human decision-making loop relative to the volume of conjunction alerts. Another was the depth of analysis available within the maneuver window."),
      br(),
      callout("ORBITIQ-X is the system that closes the gap between the physics of an impending collision and the human decision to prevent it."),

      pb(),

      // ── 4. COMPETITIVE LANDSCAPE ────────────────────────────
      h1("4. Competitive Landscape & Differentiation"),

      h2("4.1 Comparison Matrix"),
      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 1480, 1480, 1480, 1480, 1440],
        rows: [
          new TableRow({
            children: [
              headerCell("Capability", 2000),
              headerCell("Traditional SSA", 1480),
              headerCell("SpaceTrack / ASTRIAGraph", 1480),
              headerCell("General LLMs", 1480),
              headerCell("Knowledge Graph Platforms", 1480),
              headerCell("ORBITIQ-X", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Live orbital propagation", 2000),
              dataCell("\u2705", 1480),
              dataCell("\u2705", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 SGP4 + J2", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Conjunction screening", 2000),
              dataCell("\u2705", 1480),
              dataCell("\u2705", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 Foster Pc + CDM", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Natural language Q&A", 2000),
              dataCell("\u274C", 1480),
              dataCell("Partial", 1480),
              dataCell("\u2705 (no physics)", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 Physics-grounded", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Cited aerospace knowledge", 2000),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u26A0\uFE0F Hallucination risk", 1480),
              dataCell("Partial", 1480),
              accentCell("\u2705 BGE-M3 + Qdrant RAG", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Knowledge graph reasoning", 2000),
              dataCell("\u274C", 1480),
              dataCell("Partial", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u2705", 1480),
              accentCell("\u2705 13-node aerospace KG", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Multi-agent collaboration", 2000),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 LangGraph 7-agent", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Re-entry prediction", 2000),
              dataCell("Basic", 1480),
              dataCell("Basic", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 NRLMSISE-00 + decay", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Space weather integration", 2000),
              dataCell("External link", 1480),
              dataCell("External link", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 Live NOAA + drag model", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("Safety-critical controls", 2000),
              dataCell("Operator-defined", 1480),
              dataCell("Operator-defined", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 Built-in safety gate", 1440)
            ]
          }),
          new TableRow({
            children: [
              boldDataCell("50K object scale", 2000),
              dataCell("\u2705", 1480),
              dataCell("\u2705", 1480),
              dataCell("\u274C", 1480),
              dataCell("\u274C", 1480),
              accentCell("\u2705 O(n) voxel filter", 1440)
            ]
          })
        ]
      }),
      br(),
      caption("Table 1. ORBITIQ-X capability comparison against existing systems and platforms"),

      pb(),

      // ── 5. TECHNICAL ARCHITECTURE ─────────────────────────
      h1("5. Technical Architecture"),

      h2("5.1 Architecture Philosophy"),
      body("ORBITIQ-X is a vertically integrated system. Every layer is designed to feed the layer above it with higher-quality, higher-abstraction signal. The orbital engine produces physics-validated state vectors. The knowledge graph structures those state vectors into relationships. The RAG system grounds answers in citable literature. The agent system synthesizes across all layers. The safety gate ensures no unsafe output reaches an operator without review."),
      br(),
      body("This vertical integration is the defining architectural choice. A horizontally assembled system \u2014 commercial SSA data plus a general LLM plus a separate database \u2014 cannot achieve the same coherence, because the interfaces between components carry no semantic guarantees. In ORBITIQ-X, every component speaks the same language: the language of aerospace engineering."),

      h2("5.2 Layer Stack"),
      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1200, 2400, 2400, 3360],
        rows: [
          new TableRow({
            children: [
              headerCell("Layer", 1200),
              headerCell("Components", 2400),
              headerCell("Technology", 2400),
              headerCell("Function", 3360)
            ]
          }),
          ...[
            ["L0", "Data Ingestion", "CelesTrak, Space-Track, NOAA SWPC, ESA DISCOS", "TLE feeds, CDMs, space weather, catalog synchronization. 2h refresh for active sats, 6h for full debris catalog."],
            ["L1", "Orbital Engine", "python-sgp4, Poliastro, SciPy RK78", "SGP4/SDP4 propagation for 50K objects. J2 correction, coordinate transforms (ECI/ECEF/GEO/LVLH), conjunction screening (voxel filter + Foster Pc), re-entry monitoring (King-Hele + NRLMSISE-00), pass prediction, relative motion (CW equations)."],
            ["L2", "Aerospace Knowledge Graph", "Neo4j 5.x, GDS plugin, HNSW vector index", "13-node ontology: Satellite, Orbit, LaunchVehicle, Operator, Country, Mission, Constellation, DebrisObject, ConjunctionEvent, SpaceWeatherEvent, ResearchPaper, Organization, LaunchSite. 10M+ nodes, 100M+ relationships."],
            ["L3", "Aerospace RAG System", "Qdrant, BGE-M3 (1024-dim), BGE-Reranker-v2-m3, DeBERTa NLI", "Hybrid dense+sparse retrieval over NASA/ESA/ISRO technical corpus. HyDE query expansion, MMR diversity, contextual compression, 3-layer hallucination guard (NLI entailment + numeric verification + uncertainty surfacing)."],
            ["L4", "Multi-Agent System", "LangGraph, Anthropic Claude Sonnet 4.6, Redis pub/sub", "7-agent parallel architecture: Orbital Dynamics, Conjunction Analysis, Space Debris, Mission Planning, Space Weather, Aerospace Research, Satellite Intelligence. Supervisor orchestrates with intent classification and deterministic routing."],
            ["L5", "Safety Layer", "Custom SafetyGate, rule engine", "Maneuver gate (\u0394V > 10 m/s requires human), re-entry escalation, collision escalation (Pc \u2265 1e-3), space weather gate (Kp > 5), TLE staleness detection, output sanitization."],
            ["L6", "API & Frontend", "FastAPI, Next.js 14, Cesium/Resium, Chart.js", "REST + SSE endpoints. Mission Control UI: live 3D globe, conjunction alert panel, space weather widget, agent activity feed. WebSocket alerts for red CDM events."]
          ].map(([layer, comp, tech, fn]) => new TableRow({
            children: [
              dataCell(layer, 1200, "E6F1FB"),
              boldDataCell(comp, 2400),
              dataCell(tech, 2400),
              dataCell(fn, 3360)
            ]
          }))
        ]
      }),
      br(),
      caption("Table 2. ORBITIQ-X seven-layer architecture stack"),

      h2("5.3 Scalability Design"),
      body("ORBITIQ-X is designed for the 2030 orbital environment, not the 2026 one. Key scalability decisions:"),
      br(),
      bodyBold("Conjunction screening:", "Two-stage voxel hash filter (O(n)) eliminates 99.99% of candidate pairs before Foster Pc computation. 50,000 objects screened in under 120 seconds on an 8-core worker using ProcessPoolExecutor."),
      bodyBold("Ephemeris storage:", "TimescaleDB hypertable partitioned by day. Daily chunk compression after 7 days. 30-day retention for raw ephemeris. Unlimited retention for conjunction event archive."),
      bodyBold("Embedding scale:", "Qdrant HNSW with on-disk storage for dense vectors (1024-dim, scalar int8 quantization for 4\u00D7 memory reduction with <1% recall loss). Sparse BM25 index for exact term matching."),
      bodyBold("Agent parallelism:", "LangGraph Send API dispatches all requested agents in parallel. Total latency = max(agent latencies) \u2248 8\u201315s for a full 7-agent ensemble."),

      pb(),

      // ── 6. DIGITAL TWIN OF EARTH ORBIT ────────────────────
      h1("6. Digital Twin of Earth Orbit"),

      h2("6.1 Concept"),
      body("The ORBITIQ-X Digital Twin of Earth Orbit (DTEO) is a continuously updated, physics-consistent computational representation of the near-Earth space environment. It is not a visualization tool. It is a reasoning substrate: a model that can be queried, simulated, perturbed, and analyzed to answer questions that cannot be answered from historical data alone."),
      br(),
      callout("The Digital Twin asks: if I change one variable \u2014 a satellite\u2019s ballistic coefficient, a solar storm\u2019s F10.7 index, a constellation\u2019s deployment schedule \u2014 what changes downstream across the entire orbital environment?"),

      h2("6.2 Components"),
      h3("6.2.1 Resident Space Object State"),
      body("Every tracked RSO (active satellite, debris object, rocket body) is represented as a first-class entity in the DTEO with: current TLE, propagated ECI state vector at every epoch, geodetic ground track, orbital regime classification, conjunction risk score, and decay prediction. Updates are continuous: TLEs refresh every 2h for active satellites, every 6h for the full debris catalog."),

      h3("6.2.2 Atmospheric Density Model"),
      body("Orbital decay rates depend critically on upper atmospheric density, which in turn depends on solar activity. The DTEO integrates NRLMSISE-00 lookup tables with live F10.7 and Kp indices from NOAA SWPC. Every decay prediction and drag-affected propagation is conditioned on the current atmospheric state, with uncertainty bounds derived from the space weather variability."),

      h3("6.2.3 Conjunction Risk Layer"),
      body("The DTEO maintains a live conjunction risk layer: a spatial index of every pair of objects whose closest approach in the next 72 hours falls below the screening threshold (5 km). For each such pair, a Foster Pc computation is triggered and the result is stored in the conjunction event archive in Neo4j. Red events (Pc \u2265 1e-3) trigger immediate WebSocket alerts and safety gate escalation."),

      h3("6.2.4 Orbital Density Heatmap"),
      body("The DTEO produces a live orbital density heatmap: a spherical shell decomposition of RSO concentration by altitude band (50 km intervals from 200\u20131200 km) and orbital regime. This heatmap updates every screening cycle and is rendered on the Mission Control 3D globe via a Cesium ring system. It provides immediate visual situational awareness of congestion regions."),

      h2("6.3 Simulation Capability (Roadmap)"),
      body("Phase 2 of the DTEO adds forward simulation: given the current state, the system can project the orbital environment forward by 7, 30, or 365 days under different scenario assumptions (new constellation launches, solar activity forecasts, debris mitigation policies). This enables what-if analysis at a policy level: 'If SpaceX launches 10,000 more Starlink satellites in the next 3 years, how does the LEO conjunction event rate change?'"),

      pb(),

      // ── 7. AEROSPACE KNOWLEDGE GRAPH ──────────────────────
      h1("7. Aerospace Knowledge Graph"),

      h2("7.1 Design"),
      body("The ORBITIQ-X Knowledge Graph (AKG) is a Neo4j property graph with 13 node types, 40+ relationship types, and a projected scale of 10 million nodes and 100 million relationships at full corpus ingestion. It is the structured memory of ORBITIQ-X: the system that knows that Chandrayaan-3 was launched by PSLV-C57 from SDSC SHAR, reached lunar south pole orbit, and is related to 87 research papers in the RAG corpus."),

      h2("7.2 Node Ontology"),
      body("The 13 node types span the full aerospace domain:"),
      bullet("Satellite \u2014 50K+ tracked objects with NORAD ID, COSPAR designator, TLE, status, regime"),
      bullet("Orbit \u2014 500K+ orbital shells (altitude, inclination, eccentricity, period, decay lifetime)"),
      bullet("Operator \u2014 5K satellite operators by type (government, commercial, military, academic)"),
      bullet("Country \u2014 250 nations with ISO codes and space agency links"),
      bullet("Organization \u2014 10K organizations (agencies, companies, research institutions)"),
      bullet("Mission \u2014 20K missions with type, status, objectives, budget, and satellite links"),
      bullet("Constellation \u2014 200 constellations with shell configuration and deployment status"),
      bullet("LaunchVehicle \u2014 500 vehicles (active and retired) with payload capacity and success rate"),
      bullet("LaunchSite \u2014 100 sites with geodetic coordinates and operational history"),
      bullet("DebrisObject \u2014 20K+ tracked debris with radar cross-section, origin, and decay profile"),
      bullet("ConjunctionEvent \u2014 100K+ CDMs with Pc, miss distance, TCA, and resolution history"),
      bullet("SpaceWeatherEvent \u2014 50K+ events (flares, storms, SPEs) with Kp/F10.7 indices"),
      bullet("ResearchPaper \u2014 500K+ papers with DOI, abstract, keywords, citation count, and embedding"),

      h2("7.3 Index Strategy"),
      body("Three index types serve different query patterns: range indexes (for altitude, Pc, date range queries), fulltext indexes (for semantic search across names, descriptions, abstracts), and vector indexes (1536-dim cosine, for ANN similarity search in the GraphRAG entry point). All constraints use IF NOT EXISTS guards, making schema initialization idempotent on every startup."),

      h2("7.4 GraphRAG Integration"),
      body("The AKG is the structured retrieval complement to the Qdrant vector RAG. When a query arrives at the Aerospace Research Agent, it runs in parallel: semantic retrieval from Qdrant returns unstructured text chunks, while a Cypher query to Neo4j returns structured facts. The context builder merges both, producing a hybrid context block that grounds the Claude-generated answer in both document evidence and graph-structured facts."),

      pb(),

      // ── 8. AI REASONING LAYER ─────────────────────────────
      h1("8. AI Reasoning Layer"),

      h2("8.1 The Retrieval Architecture"),
      body("The core reasoning layer of ORBITIQ-X is a three-stage hybrid retrieval system. Unlike general-purpose RAG that retrieves and generates, ORBITIQ-X retrieval is physics-bounded: every retrieved chunk is validated against the orbital propagation results before being included in the answer context."),
      br(),
      bodyBold("Stage 1 \u2014 Query expansion:", "BGE-M3 encodes the query. HyDE generates a hypothetical aerospace passage and embeds that instead, bridging the vocabulary gap between user phrasing ('why is this satellite falling faster') and technical document language ('anomalous aerodynamic drag enhancement'). Aerospace acronyms are expanded (TCA \u2192 Time of Closest Approach) to improve BM25 sparse recall."),
      bodyBold("Stage 2 \u2014 Hybrid retrieval:", "Qdrant executes dense (cosine) and sparse (BM25/SPLADE) search in parallel against the aerospace document collection. Reciprocal Rank Fusion (RRF, \u03B1=0.7) merges the ranked lists. BGE-Reranker-v2-m3 cross-encoder rescores the top candidates. MMR (\u03BB=0.7) selects diverse final chunks."),
      bodyBold("Stage 3 \u2014 Hallucination mitigation:", "Three defence layers: NLI entailment check (DeBERTa-v3 cross-encoder, every answer sentence must be entailed by retrieved context), numeric claim verification (\u00B110% tolerance against source values), and uncertainty surfacing (model instructed to mark uncertain claims with [UNCERTAIN] marker)."),

      h2("8.2 Aerospace-Specific Chunking"),
      body("Standard recursive character splitting destroys aerospace technical documents. ORBITIQ-X uses a three-pass aerospace-aware chunker: section splitting (by heading detection, preserving document logical structure), special block extraction (equations and tables kept intact with surrounding context sentences), and sentence-boundary-respecting fixed-size chunking (512 tokens, 64-token overlap). The sentence splitter protects 'Eq. (3.14)', 'Fig. 4', and 'approx. 500 km' from false sentence boundary detection \u2014 a critical failure mode in naive PDF extraction of technical documents."),

      h2("8.3 Citation Strategy"),
      body("Every ORBITIQ-X answer follows IEEE citation practice. The system prompt instructs Claude to end every factual sentence with an inline citation [N]. The context builder prepends a structured source header to each retrieved chunk, including agency, year, report number, section, and DOI. The citation formatter generates a full bibliography in IEEE or APA format and appends it to every answer. This makes every ORBITIQ-X response not just an answer but a citable, auditable intelligence product."),

      pb(),

      // ── 9. AGENTIC INTELLIGENCE LAYER ─────────────────────
      h1("9. Agentic Intelligence Layer"),

      h2("9.1 The Multi-Agent Architecture"),
      body("The ORBITIQ-X agentic layer is a LangGraph supervisor-parallel architecture with 7 specialist agents and a shared typed state. The supervisor classifies query intent into 10 categories (collision_risk, orbital_decay, maneuver_planning, mission_planning, space_weather, satellite_profile, debris_analysis, research_question, pass_prediction, general_ssa) and routes to the appropriate agent subset via a deterministic routing table. LLM-based routing is used for classification only; execution routing is rule-based for reliability."),
      br(),
      body("Agents execute in parallel via the LangGraph Send API. The total query latency is max(agent latencies), not the sum \u2014 typically 8\u201315 seconds for a full 7-agent ensemble. All agents write to a shared OrbitalState TypedDict with annotated list reducers that safely merge parallel writes."),

      h2("9.2 The Seven Agents"),
      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 2200, 2200, 2960],
        rows: [
          new TableRow({
            children: [
              headerCell("Agent", 2000),
              headerCell("Goal", 2200),
              headerCell("Key tools", 2200),
              headerCell("Safety controls", 2960)
            ]
          }),
          ...[
            ["Orbital Dynamics", "Accurate state vectors, ground tracks, passes, relative motion", "SGP4, orbit classifier, CW equations, ECEF/LVLH transforms", "Max propagation window: 30 days. TLE age > 7 days \u2192 degraded accuracy flag."],
            ["Conjunction Analysis", "Collision risk screening, CDM generation, maneuver planning", "Foster Pc, voxel spatial filter, CDM v1.0, \u0394V optimizer", "\u0394V > 10 m/s requires human sign-off. Pc \u2265 1e\u207B\u00B3 triggers external alert regardless of query."],
            ["Space Debris", "Debris environment, re-entry monitoring, anomaly detection", "Decay monitor, King-Hele drag, NRLMSISE-00 table, anomaly detector", "IMMINENT reentry (\u00A0< 24h) triggers pager alert. >3\u03C3 anomalies escalate immediately."],
            ["Mission Planning", "\u0394V budgets, launch windows, trajectory design, timelines", "Hohmann transfer, porkchop planner, mission Gantt, launch window", "Launch windows blocked during Kp > 5. Maneuver windows must not conflict with active red CDMs."],
            ["Space Weather", "NOAA Kp/F10.7 monitoring, drag impact, storm classification", "NOAA SWPC REST, Kp forecast, drag density model (F10.7)", "G3+ storm (Kp \u2265 6): all drag models flagged \u00B130% uncertainty."],
            ["Aerospace Research", "RAG retrieval, KG facts, paper search, cited synthesis", "BGE-M3 Qdrant RAG, Neo4j Cypher, BGE-Reranker, DeBERTa NLI", "Faithfulness score < 0.7 \u2192 low confidence flag. All numeric claims verified against sources."],
            ["Satellite Intelligence", "RSO profiles, constellation analysis, operator intelligence", "RSO catalog, TLE fetch, constellation analyzer, Space-Track", "Only public catalog data. No classified information accessed or inferred."]
          ].map(([a, g, t, s]) => new TableRow({
            children: [boldDataCell(a, 2000), dataCell(g, 2200), dataCell(t, 2200), dataCell(s, 2960)]
          }))
        ]
      }),
      br(),
      caption("Table 3. ORBITIQ-X seven specialist agents with goals, tools, and safety controls"),

      h2("9.3 The Safety Gate"),
      body("The safety gate is the most important node in the ORBITIQ-X graph. It runs sequentially after all agents complete, before synthesis. Its five control layers are non-negotiable: no agent output bypasses the gate, no exception in the gate releases outputs (fail-safe design \u2014 gate failure blocks all maneuver recommendations). Every safety decision is logged for full audit trail."),

      pb(),

      // ── 10. CONVERGENCE THESIS ────────────────────────────
      h1("10. The Convergence Thesis"),

      h2("10.1 Why Now"),
      body("ORBITIQ-X is possible in 2026 because five independent technology curves have matured simultaneously:"),
      br(),
      numbered("Foundation models (Claude, GPT-4, Gemini) can now reason over long technical contexts with instruction-following sufficient for structured aerospace outputs."),
      numbered("Multilingual dense retrievers (BGE-M3) achieve recall@10 > 0.95 on domain-specific technical text without fine-tuning."),
      numbered("Vector databases (Qdrant) support hybrid dense+sparse search with millisecond latency at million-document scale."),
      numbered("Graph databases (Neo4j 5.x with GDS) support vector indexes, ANN similarity search, and real-time graph analytics at billion-edge scale."),
      numbered("Agentic orchestration frameworks (LangGraph) enable reliable multi-step multi-agent reasoning with typed state, parallel execution, and checkpointed conversation history."),
      br(),
      body("No single one of these technologies makes ORBITIQ-X possible. The convergence of all five, applied to a domain (aerospace) that has 70 years of structured data, makes it inevitable."),

      h2("10.2 The Six-Domain Convergence"),
      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1700, 2000, 1680, 3980],
        rows: [
          new TableRow({
            children: [
              headerCell("Domain", 1700),
              headerCell("What ORBITIQ-X brings", 2000),
              headerCell("Key technology", 1680),
              headerCell("Convergence value", 3980)
            ]
          }),
          ...[
            ["Orbital Mechanics", "Physics-validated propagation at scale", "python-sgp4, Poliastro", "AI cannot hallucinate orbital parameters: every generated answer is cross-checked against a deterministic physics engine."],
            ["Artificial Intelligence", "Foundation model reasoning over aerospace context", "Claude Sonnet 4.6, BGE-M3", "Natural language interface to complex technical content: operators query in plain English, receive engineering-grade answers."],
            ["Space Operations", "Live SSA data integration and anomaly detection", "Space-Track, CelesTrak, CDM pipeline", "The system knows the operational state of the orbital environment in real time, not as a static training corpus."],
            ["Knowledge Graphs", "Structured aerospace entity relationships", "Neo4j, 13-node ontology, GDS", "Answers that trace mission lineage, operator relationships, and research provenance across the full aerospace knowledge base."],
            ["Digital Twins", "Living computational model of Earth orbit", "TimescaleDB, NRLMSISE-00, Cesium 3D", "Forward simulation: project the orbital environment under different scenario assumptions to inform policy and operations."],
            ["Agentic Systems", "Multi-agent collaboration for complex queries", "LangGraph, 7 specialist agents", "Questions that require multiple domain perspectives (conjunction risk + space weather + research context) are answered by a coordinated team, not a single model pass."]
          ].map(([d, w, k, c]) => new TableRow({
            children: [boldDataCell(d, 1700), dataCell(w, 2000), dataCell(k, 1680), dataCell(c, 3980)]
          }))
        ]
      }),
      br(),
      caption("Table 4. The six-domain convergence in ORBITIQ-X"),

      pb(),

      // ── 11. ROADMAP ────────────────────────────────────────
      h1("11. Development Roadmap"),

      h2("11.1 3-Year Technical Roadmap (2026\u20132028)"),
      br(),

      h3("Phase 1 \u2014 Foundation (H2 2026)"),
      body("Status: COMPLETE (current state of ORBITIQ-X as of June 2026)"),
      bullet("Monorepo scaffold: orbital-engine, knowledge-graph, RAG, agents, frontend (84 files, 10K+ LOC)"),
      bullet("Orbital engine: SGP4/SDP4 propagator, coordinate transforms, orbit classifier, Foster Pc conjunction screener (50K object capacity), re-entry monitor, Clohessy-Wiltshire relative motion, pass predictor"),
      bullet("Knowledge graph: Neo4j schema (13 node types, 40+ relationships, 8 payload indexes, vector index)"),
      bullet("RAG system: BGE-M3 embeddings, Qdrant hybrid dense+sparse, HyDE, MMR, 3-layer hallucination guard"),
      bullet("Multi-agent system: LangGraph 7-agent supervisor-parallel architecture with typed shared state and safety gate"),
      bullet("Mission Control UI: Next.js 14, Cesium/Resium 3D globe, SSE streaming endpoints"),
      bullet("Docker Compose: 11-service dev stack (PostgreSQL, Redis, Neo4j, Qdrant, InfluxDB, Prometheus, Grafana)"),

      h3("Phase 2 \u2014 Intelligence (H1\u2013H2 2027)"),
      bullet("Document corpus ingestion: 50K+ aerospace documents (NASA NTRS, ESA publication archive, ISRO technical reports, arXiv aerospace papers, AIAA proceedings)"),
      bullet("Knowledge graph population: 1M+ satellite records, full mission lineage, launch vehicle family trees, 500K research paper nodes"),
      bullet("TLE archive: historical TLE database from 1957 to present (Space-Track bulk download)"),
      bullet("Maneuver optimization: full CW two-impulse rendezvous solver with fuel cost optimization"),
      bullet("Constellation intelligence: full Starlink, OneWeb, Kuiper shell analysis with coverage maps"),
      bullet("ORBITIQ NEXUS: apex platform deployment to production (orbitiq-nexus.mahin-aeroai.workers.dev)"),
      bullet("Evaluation framework: 500-question aerospace benchmark, RAGAS faithfulness \u2265 0.85"),
      bullet("API rate limiting, authentication, multi-tenant support for external operator access"),

      h3("Phase 3 \u2014 Production (2028)"),
      bullet("Real-time CDM integration: Space-Track API continuous feed, 15-minute conjunction screening cycle"),
      bullet("Fragmentation event response: automated debris cloud characterization within 2h of breakup event"),
      bullet("Mission planning copilot: full mission design workflow (launch window \u2192 orbit insertion \u2192 ops phase \u2192 EOL)"),
      bullet("Digital twin forward simulation: 30-day and 365-day orbital environment projections under scenario assumptions"),
      bullet("External operator API: REST + WebSocket interface for third-party integration (SSA organizations, satellite operators, insurance underwriters)"),
      bullet("Compliance: IADC debris mitigation guideline checking for proposed mission designs"),
      bullet("Mobile app: real-time satellite pass alerts and conjunction notifications for ground station operators"),

      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2080, 2080, 2080, 3120],
        rows: [
          new TableRow({
            children: [
              headerCell("Milestone", 2080),
              headerCell("Phase 1 (H2 2026)", 2080),
              headerCell("Phase 2 (2027)", 2080),
              headerCell("Phase 3 (2028)", 3120)
            ]
          }),
          ...[
            ["Tracked objects", "50K (capacity)", "50K (live)", "100K (incl. commercial)"],
            ["Document corpus", "Schema ready", "50K documents", "500K documents"],
            ["KG nodes", "Schema + sample data", "1M+", "10M+"],
            ["Agent response time", "8\u201315s (prototype)", "5\u201310s (optimized)", "<3s (GPU-accelerated)"],
            ["Conjunction screening", "1h cycle", "15m cycle", "Continuous (real-time)"],
            ["RAG faithfulness", "Development", "\u22650.85", "\u22650.92"],
            ["Deployment", "GitHub Pages + Railway", "Cloudflare Workers + PG", "Multi-region production"]
          ].map(([m, p1, p2, p3]) => new TableRow({
            children: [boldDataCell(m, 2080), dataCell(p1, 2080), dataCell(p2, 2080), dataCell(p3, 3120)]
          }))
        ]
      }),
      br(),
      caption("Table 5. Three-year technical milestones"),

      pb(),

      // ── 12. 10-YEAR VISION ─────────────────────────────────
      h1("12. Ten-Year Vision (2026\u20132036)"),

      h2("12.1 The Aerospace Foundation Model"),
      body("By 2036, ORBITIQ-X aims to be to aerospace operations what GPT-4 is to general text: a foundation upon which an entire ecosystem of specialized tools is built. Just as biomedical AI builds on ESM2 for protein sequences and clinical AI builds on domain-tuned language models, every future aerospace AI application should be able to build on ORBITIQ-X\u2019s orbital intelligence layer."),
      br(),
      callout("The long-term goal is not to replace aerospace engineers. It is to give every aerospace engineer the reasoning capacity of a team of 20 domain experts, available at any time, for any object in orbit."),

      h2("12.2 Research Roadmap (2029\u20132036)"),
      h3("Near-term (2029\u20132030): Precision and Autonomy"),
      bullet("High-fidelity integrator: Cowell/RK78 numerical propagation for precision conjunction analysis, replacing SGP4 for objects approaching critical Pc thresholds"),
      bullet("Autonomous conjunction management: agent-initiated contact with operator notification systems, automated CDM generation and transmission to counterpart operators"),
      bullet("Fine-tuned aerospace language model: domain-adapted version of a foundation model trained on the full ORBITIQ-X corpus (NASA NTRS + ESA + ISRO + 70 years of aerospace literature)"),
      bullet("Orbital debris radar integration: direct sensor data feed from radar networks for sub-10cm object tracking (below current catalog threshold)"),

      h3("Mid-term (2031\u20132032): Prediction and Planning"),
      bullet("Collision probability forecasting: ML models that predict future conjunction risk based on constellation deployment trajectories, not just current orbital states"),
      bullet("Atmospheric drag neural operator: surrogate model for NRLMSISE-00 that runs 1000\u00D7 faster, enabling Monte Carlo uncertainty quantification in real time"),
      bullet("Maneuver planning autonomy: end-to-end autonomous avoidance maneuver design, notification, approval workflow, and execution confirmation (with human-in-the-loop gate)"),
      bullet("Digital twin Level 4: bidirectional coupling between the ORBITIQ-X digital twin and real satellite telemetry. The twin is no longer a model of the environment; it is synchronized with it"),
      bullet("International data sharing: ORBITIQ-X as the intelligence layer for a proposed international SSA data sharing consortium"),

      h3("Long-term (2033\u20132036): The Aerospace Brain"),
      bullet("Orbital environment governance AI: ORBITIQ-X as an analytical tool for international space law and debris mitigation policy, quantifying the long-term consequences of different orbital use regimes"),
      bullet("Lunar and cislunar extension: extend the digital twin beyond GEO to the cislunar volume as Artemis-era traffic grows"),
      bullet("On-orbit autonomy: ORBITIQ-X as the ground intelligence complement to autonomous satellite systems, providing mission context and maneuver authority that individual satellites cannot compute for themselves"),
      bullet("Academic partnership: ORBITIQ-X codebase as the platform for university aerospace AI research programs, analogous to how TensorFlow enabled the deep learning research community"),
      bullet("Aerospace engineering education: interactive educational layer that teaches orbital mechanics, SSA, and mission design through natural language interaction with a verified-accurate knowledge base"),

      h2("12.3 The Kessler Mitigation Case"),
      body("The ultimate test of ORBITIQ-X is its contribution to preventing the Kessler Syndrome: the runaway debris cascade that makes LEO unusable for generations. This is not a hypothetical risk. The Iridium-Cosmos collision added 2,000 trackable debris objects. The Fengyun-1C ASAT test added 3,000. The current collision rate in LEO is estimated at one significant event every 5\u201310 years. As object density triples over the next decade, this rate increases nonlinearly."),
      br(),
      body("ORBITIQ-X contributes to Kessler mitigation on three timescales: immediate (real-time conjunction alerts with faster human decision loops), medium-term (mission planning that incorporates debris mitigation compliance from design inception), and long-term (policy analysis that quantifies the orbital capacity consequences of different constellation deployment strategies)."),

      pb(),

      // ── 13. CURRENT STATUS ────────────────────────────────
      h1("13. Current Status"),

      h2("13.1 Repository"),
      body("ORBITIQ-X is under active development at github.com/mahin-aeroai/ORBITIQ-X. The repository contains a production-grade monorepo with four major subsystems fully designed and implemented at the architecture level."),
      br(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 1500, 2000, 3460],
        rows: [
          new TableRow({
            children: [
              headerCell("Subsystem", 2400),
              headerCell("Files / LOC", 1500),
              headerCell("Status", 2000),
              headerCell("Key capabilities", 3460)
            ]
          }),
          ...[
            ["Orbital engine", "16 files / 4,173 LOC", "Architecture complete", "SGP4, orbit classifier, Foster Pc, re-entry monitor, CW, pass predictor, coordinate transforms"],
            ["Knowledge graph", "6 files / 1,916 LOC", "Schema complete", "Neo4j 13-node ontology, Cypher queries, GraphRAG integration strategy"],
            ["RAG system", "9 files / 3,239 LOC", "Architecture complete", "BGE-M3 embedder, Qdrant hybrid search, HyDE, MMR, 3-layer hallucination guard"],
            ["Multi-agent system", "8 files / 2,467 LOC", "Architecture complete", "7-agent LangGraph, supervisor, safety gate, 28 tools, SSE streaming"],
            ["Mission Control UI", "5 files / ~1,200 LOC", "Architecture complete", "Next.js 14, Cesium globe, agent feed, space weather widget"],
            ["Deployment stack", "8 files / ~500 LOC", "Dev stack complete", "Docker Compose (11 services), Prometheus, health-check"]
          ].map(([s, f, st, k]) => new TableRow({
            children: [boldDataCell(s, 2400), dataCell(f, 1500), dataCell(st, 2000), dataCell(k, 3460)]
          }))
        ]
      }),
      br(),
      caption("Table 6. ORBITIQ-X repository status as of June 2026"),

      h2("13.2 Deployed Platforms"),
      body("Three public-facing aerospace platforms are live as proof-of-concept demonstrations:"),
      bullet("ORBITIQ Explorer v2 (mahin-aeroai.github.io/orbitiq-explorer-v2): 15-module aerospace intelligence platform including live SGP4 propagation, pass prediction for Hyderabad, asteroid intelligence (NASA NeoWS), and AI Copilot"),
      bullet("ORBITIQ NEXUS (mahin-aeroai.github.io/NEXUS): apex aerospace intelligence platform with orbital density heatmap ring system, 9 intelligence modules, and Cloudflare Worker proxy for secure Anthropic API access"),
      bullet("ASTRA WATCH (mahin-aeroai.github.io/ASTRA-WATCH): real-time SSA operations platform with live ISS tracking, Chart.js orbital visualizations, and 8 monitoring modules"),

      pb(),

      // ── 14. CLOSING ────────────────────────────────────────
      h1("14. Closing Argument"),
      body("The aerospace community has spent 70 years building extraordinary physical infrastructure in orbit. It has spent far less time building the intelligence infrastructure to manage it. The result is a domain of profound consequence \u2014 telecommunications, navigation, weather forecasting, national security, human spaceflight \u2014 managed by tools that were designed for a world with hundreds of objects, not hundreds of thousands."),
      br(),
      body("ORBITIQ-X is not a product in search of a market. It is an answer to a demonstrated problem: the intelligence gap between the physics of what is happening in Earth orbit and the human capacity to understand, predict, and respond to it."),
      br(),
      body("The technical components described in this document \u2014 the orbital engine, the knowledge graph, the RAG system, the multi-agent architecture, the digital twin, the safety layer \u2014 are not speculative. They are implemented. They are on GitHub. They are the foundation on which the next phase is being built."),
      br(),
      callout("The question is not whether AI will transform space operations. It is whether that transformation will be built on a foundation of aerospace engineering rigour, or whether it will arrive as a general-purpose tool applied badly to a domain it was not designed for."),
      br(),
      body("ORBITIQ-X is the case for the former."),

      br(), br(),
      new Paragraph({
        children: [new TextRun({ text: "\u2014 Mahin Nandipa, June 2026", italics: true, size: 22, color: GRAY, font: "Arial" })],
        alignment: AlignmentType.RIGHT
      }),

      pb(),

      // ── APPENDIX: KEY METRICS ─────────────────────────────
      h1("Appendix A: Key Metrics & Design Targets"),
      br(),
      h3("Orbital Engine"),
      metric("Max tracked objects", "50,000 (current) \u2192 100,000 (Phase 3)"),
      metric("Conjunction screening cycle", "60s (priority) / 15min (full catalog) \u2192 real-time"),
      metric("SGP4 batch throughput", "50,000 objects / <120s on 8-core CPU"),
      metric("Foster Pc accuracy", "<10% deviation from NASA CARA for Pc \u2265 1e-5"),
      metric("TLE refresh cadence", "2h (active satellites) / 6h (debris catalog)"),

      br(),
      h3("RAG System"),
      metric("Embedding model", "BGE-M3, 1024-dim dense + SPLADE sparse"),
      metric("Vector store", "Qdrant HNSW m=16, ef=200, on-disk int8 quantization"),
      metric("Target faithfulness", "\u22650.90 on 500-question aerospace benchmark"),
      metric("Target numeric accuracy", "\u22650.92 (\u00B110% tolerance)"),
      metric("Hallucination rate target", "<0.10 (fraction of unsupported claims)"),
      metric("RAG query latency", "<2s end-to-end (retrieval + generation)"),

      br(),
      h3("Multi-Agent System"),
      metric("Agent ensemble latency", "8\u201315s full 7-agent parallel (Claude Sonnet 4.6)"),
      metric("Intent classification accuracy", ">95% on 10-category aerospace taxonomy"),
      metric("Safety gate coverage", "100% of maneuver recommendations, 100% of Pc \u2265 1e-4 events"),
      metric("Conversation history", "Redis-backed, unlimited turn multi-session"),

      br(),
      h3("Knowledge Graph"),
      metric("Node types", "13"),
      metric("Relationship types", "40+"),
      metric("Target scale", "10M nodes / 100M relationships"),
      metric("Index types", "Range + fulltext + 1536-dim vector (HNSW cosine)"),
      metric("GraphRAG ANN recall@10", ">0.95"),

      br(),
      h3("Digital Twin"),
      metric("RSO catalog coverage", "All Space-Track cataloged objects (NORAD IDs 1\u201399999)"),
      metric("Ephemeris retention", "30 days raw (TimescaleDB hypertable), unlimited CDM archive"),
      metric("Space weather update cadence", "30 minutes (NOAA SWPC)"),
      metric("3D globe render", "Cesium/Resium, real-time orbital positions, density heatmap ring system"),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/mnt/user-data/outputs/ORBITIQ-X_Technical_Vision.docx', buffer);
  console.log('Document written successfully');
}).catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
