"use client";
/**
 * ORBITIQ-X — SideNav
 * =====================
 * Left sidebar navigation for mission control modules.
 * Collapsed to icon-only on narrow viewports.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/",               label: "Dashboard",      icon: "⊕" },
  { href: "/catalog",        label: "Catalog",        icon: "◫" },
  { href: "/conjunctions",   label: "Conjunctions",   icon: "⚠" },
  { href: "/agents",         label: "Agents",         icon: "◈" },
  { href: "/knowledge-graph",label: "Knowledge Graph",icon: "◎" },
  { href: "/foundation",     label: "Foundation",     icon: "◧" },
] as const;

export function SideNav() {
  const pathname = usePathname();

  return (
    <nav
      className="flex w-12 flex-col items-center gap-1 border-r border-space-border bg-space-midnight py-3 lg:w-48 lg:items-start lg:px-3"
      aria-label="Primary navigation"
    >
      {NAV_ITEMS.map(({ href, label, icon }) => {
        const active = pathname === href || (href !== "/" && pathname.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex w-full items-center gap-3 rounded px-2 py-2 text-xs font-medium transition-colors",
              "hover:bg-space-surface hover:text-space-text",
              active
                ? "bg-[var(--color-accent-indigo-glow)] text-space-accent"
                : "text-space-muted",
            ].join(" ")}
            aria-current={active ? "page" : undefined}
            title={label}
          >
            <span className="shrink-0 font-mono text-sm" aria-hidden="true">
              {icon}
            </span>
            <span className="hidden lg:block">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
