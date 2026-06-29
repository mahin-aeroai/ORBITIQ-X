/**
 * /graphrag — redirects to /intelligence (AI Workspace)
 * The GraphRAG interface lives at /intelligence.
 */
"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GraphRAGPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/intelligence"); }, [router]);
  return (
    <div className="flex h-full items-center justify-center">
      <span style={{ color: "var(--color-text-tertiary)" }} className="font-mono text-sm">
        Redirecting to AI Workspace…
      </span>
    </div>
  );
}
