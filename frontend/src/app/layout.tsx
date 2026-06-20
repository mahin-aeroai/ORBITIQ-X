/**
 * ORBITIQ-X — Root Layout
 * ========================
 * Application shell: providers, global styles, metadata.
 * All pages share this layout via the Next.js App Router.
 */
import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { Toaster } from "sonner";

import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { TopNav } from "@/components/ui/TopNav";
import { SideNav } from "@/components/ui/SideNav";

import "@/styles/globals.css";

// ─── Typography ───────────────────────────────────────────────────────────────
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});

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
      className={`${spaceGrotesk.variable} ${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body className="bg-space-deep text-space-text antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
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
        </ThemeProvider>
      </body>
    </html>
  );
}
