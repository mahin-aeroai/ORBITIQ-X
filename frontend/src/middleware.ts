/**
 * ORBITIQ-X — Next.js Route Middleware
 * ======================================
 * Server-side authentication guard. Runs on every request before page render.
 *
 * Logic
 * ──────
 *   1. Requests to /login or /api/auth/* pass through immediately.
 *   2. Requests to /api/* (non-auth) are left for the API client to handle
 *      the 401 → refresh → redirect cycle (see lib/api.ts).
 *   3. All other routes (dashboard pages) check for the HttpOnly refresh cookie.
 *      If absent, redirect to /login.
 *
 * Why cookie-based and not JWT-based?
 * ─────────────────────────────────────
 * The access token lives only in React state (memory) and is not available
 * to the middleware (Edge runtime has no access to the React tree).
 * The presence of the HttpOnly refresh cookie is a reliable proxy for
 * "user has authenticated recently" — if it's present, AuthProvider will
 * silently refresh on mount and supply a valid access token.
 *
 * Note: this is a presence check only, not a cryptographic verification.
 * The backend still verifies the JWT on every API call. The middleware's
 * purpose is to avoid flashing the dashboard to unauthenticated users.
 */

import { NextRequest, NextResponse } from "next/server";

const REFRESH_COOKIE = "orbitiq_refresh";

// Routes that are always public (no auth check)
const PUBLIC_PREFIXES = ["/login", "/api/auth"];

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // ── Always public ──────────────────────────────────────────────────────────
  if (PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  // ── API routes: let the client handle 401 ─────────────────────────────────
  // The apiFetch() in lib/api.ts handles token refresh and redirect.
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  // ── Static assets, Next.js internals ─────────────────────────────────────
  if (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/favicon") ||
    pathname.match(/\.(ico|png|jpg|jpeg|svg|webp|woff2?|ttf)$/)
  ) {
    return NextResponse.next();
  }

  // ── Protected pages: check for refresh cookie ────────────────────────────
  const hasSession = request.cookies.has(REFRESH_COOKIE);

  if (!hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    // Preserve the original destination so we can redirect back after login
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

// Apply middleware to all routes except Next.js internals
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
