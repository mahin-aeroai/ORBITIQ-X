"use client";
/**
 * ORBITIQ-X — SideNav (v0.4.0)
 * Full sidebar with all platform sections.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth, type UserRole } from "@/components/providers/AuthProvider";

interface NavItem {
  href:     string;
  label:    string;
  icon:     string;
  minRole?: UserRole;
  badge?:   string;
}

const NAV_GROUPS: { group: string; items: NavItem[] }[] = [
  {
    group: "OPERATIONS",
    items: [
      { href: "/",             label: "Mission Control",   icon: "⊕" },
      { href: "/catalog",      label: "Satellite Catalog", icon: "◫", minRole: "operator" },
      { href: "/conjunctions", label: "Conjunctions",      icon: "⚠",  minRole: "operator" },
    ],
  },
  {
    group: "INTELLIGENCE",
    items: [
      { href: "/intelligence",    label: "AI Workspace",     icon: "◈" },
      { href: "/agents",          label: "Agents",           icon: "◎", minRole: "analyst" },
      { href: "/knowledge-graph", label: "Knowledge Graph",  icon: "◉", minRole: "analyst" },
      { href: "/graphrag",        label: "GraphRAG",         icon: "◑", minRole: "analyst" },
    ],
  },
  {
    group: "PLATFORM",
    items: [
      { href: "/foundation",  label: "Foundation Model", icon: "◧", minRole: "admin" },
      { href: "/system",      label: "Infrastructure",   icon: "⊛", minRole: "analyst" },
    ],
  },
];

export function SideNav() {
  const pathname = usePathname();
  const { hasMinRole, isAuthenticated } = useAuth();

  return (
    <nav
      className="flex w-12 flex-col border-r border-space-border bg-space-midnight py-2 lg:w-52 lg:px-2"
      aria-label="Primary navigation"
    >
      {NAV_GROUPS.map(({ group, items }) => {
        const visible = items.filter((item) => {
          if (!isAuthenticated) return false;
          if (!item.minRole) return true;
          return hasMinRole(item.minRole);
        });
        if (!visible.length) return null;

        return (
          <div key={group} className="mb-4">
            {/* Group label — hidden on mobile */}
            <div className="mb-1 hidden px-2 lg:block">
              <span className="font-mono text-[9px] tracking-[0.15em] text-[var(--color-text-tertiary)]">
                {group}
              </span>
            </div>

            {visible.map(({ href, label, icon, badge }) => {
              const active = pathname === href || (href !== "/" && pathname.startsWith(href));
              return (
                <Link
                  key={href}
                  href={href}
                  className={[
                    "group flex items-center gap-2.5 rounded-md px-2 py-2 transition-all duration-150",
                    active
                      ? "bg-[var(--color-accent-indigo-glow)] text-[var(--color-accent-indigo-bright)]"
                      : "text-[var(--color-text-secondary)] hover:bg-space-surface hover:text-[var(--color-text-primary)]",
                  ].join(" ")}
                  aria-current={active ? "page" : undefined}
                >
                  {/* Active indicator bar */}
                  <span
                    className={[
                      "absolute left-0 h-5 w-0.5 rounded-r transition-all",
                      active ? "bg-[var(--color-accent-indigo)]" : "bg-transparent",
                    ].join(" ")}
                    aria-hidden="true"
                  />

                  <span className="text-base leading-none" aria-hidden="true">
                    {icon}
                  </span>

                  <span className="hidden truncate font-mono text-[11px] font-medium tracking-wide lg:block">
                    {label}
                  </span>

                  {badge && (
                    <span className="ml-auto hidden rounded bg-[var(--color-accent-amber-glow)] px-1.5 py-0.5 font-mono text-[9px] text-[var(--color-accent-amber)] lg:block">
                      {badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        );
      })}

      {/* Version stamp at bottom */}
      <div className="mt-auto hidden px-2 lg:block">
        <span className="font-mono text-[9px] text-[var(--color-text-tertiary)]">
          v0.4.0 · GraphRAG
        </span>
      </div>
    </nav>
  );
}
