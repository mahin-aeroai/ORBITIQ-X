"use client";
/**
 * ORBITIQ-X — SideNav
 * =====================
 * Role-aware left sidebar navigation.
 * Items are filtered by the current user's minimum required role.
 *
 * Access matrix (mirrors router.py RBAC)
 * ─────────────────────────────────────────
 *   Dashboard      — any authenticated user
 *   Catalog        — operator | admin
 *   Conjunctions   — operator | admin
 *   Agents         — analyst | admin
 *   Knowledge Graph— analyst | admin
 *   Foundation     — admin only
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth, type UserRole } from "@/components/providers/AuthProvider";

// ─── Nav item definitions ─────────────────────────────────────────────────────

interface NavItem {
  href:     string;
  label:    string;
  icon:     string;
  minRole?: UserRole;   // undefined = any authenticated user
}

const NAV_ITEMS: NavItem[] = [
  { href: "/",                label: "Dashboard",       icon: "⊕" },
  { href: "/catalog",         label: "Catalog",         icon: "◫", minRole: "operator" },
  { href: "/conjunctions",    label: "Conjunctions",    icon: "⚠", minRole: "operator" },
  { href: "/agents",          label: "Agents",          icon: "◈", minRole: "analyst"  },
  { href: "/knowledge-graph", label: "Knowledge Graph", icon: "◎", minRole: "analyst"  },
  { href: "/system",          label: "System Status",   icon: "⊛", minRole: "analyst"  },
  { href: "/foundation",      label: "Foundation",      icon: "◧", minRole: "admin"    },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function SideNav() {
  const pathname          = usePathname();
  const { hasMinRole, isAuthenticated } = useAuth();

  // Filter nav items by role
  const visibleItems = NAV_ITEMS.filter((item) => {
    if (!isAuthenticated) return false;
    if (!item.minRole)    return true;       // any auth user
    return hasMinRole(item.minRole);
  });

  return (
    <nav
      className="flex w-12 flex-col items-center gap-1 border-r border-space-border bg-space-midnight py-3 lg:w-48 lg:items-start lg:px-3"
      aria-label="Primary navigation"
    >
      {visibleItems.map(({ href, label, icon }) => {
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
