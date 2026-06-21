/**
 * ORBITIQ-X — Root Layout
 * ========================
 * Application shell: providers, global styles, metadata.
 * All pages share this layout via the Next.js App Router.
 */
import type { Metadata, Viewport } from "next";
import { Toaster } from "sonner";

import { QueryProvider } from "@/components/providers/QueryProvider";
import { AuthProvider } from "@/components/providers/AuthProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { TopNav } from "@/components/ui/TopNav";
import { SideNav } from "@/components/ui/SideNav";

import "@/styles/globals.css";

// ─── Typography ───────────────────────────────────────────────────────────────
// Fonts are loaded via <link> in globals.css (Google Fonts CDN) so that
// next build works in offline / sandboxed CI environments.
// The CSS variables (--font-display, --font-body, --font-mono) are declared
// in globals.css and mapped in tailwind.config.ts.
const fontVars = {
  display: "--font-display",   // Space Grotesk
  body:    "--font-body",      // Inter
  mono:    "--font-mono",      // JetBrains Mono
};

// ─── Metadata ─────────────────────────────────────────────────────────────────
export const metadata: Metadata = {
  title: {
    default: "ORBITIQ-X — Aerospace Foundation Model",
    template: "%s | ORBITIQ-X",
  },
  description:
    "AI-powered Space Intelligence platform: SSA, Orbital Mechanics, Knowledge Graphs, RAG, and Multi-Agent Mission Planning.",
  keywords: [
    "space situational awareness",
    "orbital mechanics",
    "satellite catalog",
    "conjunction analysis",
    "space intelligence",
    "aerospace AI",
    "mission planning",
  ],
  authors: [{ name: "Mahin Nandipa", url: "https://mahin-nandipa.netlify.app" }],
  creator: "Mahin Nandipa",
  openGraph: {
    type: "website",
    locale: "en_US",
    title: "ORBITIQ-X — Aerospace Foundation Model for Space Intelligence",
    description: "Production-grade AI platform for Space Situational Awareness and Mission Intelligence.",
    siteName: "ORBITIQ-X",
  },
  robots: { index: false, follow: false },  // Private platform
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon-16x16.png",
    apple: "/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0f1e" },
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
  ],
  width: "device-width",
  initialScale: 1,
};

// ─── Root Layout ──────────────────────────────────────────────────────────────
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className="font-body"
    >
      <body className="bg-space-deep text-space-text antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <AuthProvider>
          <QueryProvider>
            {/* App shell */}
            <div className="flex h-screen overflow-hidden">
              <SideNav />
              <div className="flex flex-1 flex-col overflow-hidden">
                <TopNav />
                <main className="flex-1 overflow-y-auto">
                  {children}
                </main>
              </div>
            </div>

            {/* Toast notifications */}
            <Toaster
              theme="dark"
              position="bottom-right"
              toastOptions={{
                style: {
                  background: "var(--color-surface-elevated)",
                  border: "1px solid var(--color-border)",
                  color: "var(--color-text-primary)",
                },
              }}
            />
          </QueryProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
