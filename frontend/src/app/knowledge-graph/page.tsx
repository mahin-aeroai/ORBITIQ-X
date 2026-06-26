import type { Metadata } from "next";
export const metadata: Metadata = { title: "Knowledge Graph | ORBITIQ-X" };
export default function KnowledgeGraphPage() {
  return (
    <div style={{display:"flex",height:"100%",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:16,padding:32}}>
      <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"rgba(99,102,241,0.6)",letterSpacing:"0.2em"}}>ORBITIQ-X MODULE</div>
      <div style={{fontFamily:"var(--font-display)",fontSize:28,fontWeight:700,color:"var(--color-text-primary)"}}>Knowledge Graph</div>
      <div style={{fontFamily:"var(--font-mono)",fontSize:11,color:"rgba(148,163,184,0.5)",maxWidth:440,textAlign:"center",lineHeight:1.8}}>Operator profiles, satellite relationships, constellation topology. Neo4j graph intelligence. Requires Neo4j Aura configuration.</div>
      <div style={{marginTop:8,padding:"8px 20px",border:"1px solid rgba(99,102,241,0.3)",borderRadius:4,fontFamily:"var(--font-mono)",fontSize:9,color:"rgba(99,102,241,0.6)",letterSpacing:"0.15em"}}>BACKEND API OPERATIONAL</div>
    </div>
  );
}
