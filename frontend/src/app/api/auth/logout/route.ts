/**
 * POST /api/auth/logout
 * Revoke the refresh token on the backend and clear the HttpOnly cookie.
 */
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "orbitiq_refresh";
const API_BASE    = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").split("/api/v1")[0].replace(/\/$/, "");

export async function POST(req: NextRequest): Promise<NextResponse> {
  const refreshToken = req.cookies.get(COOKIE_NAME)?.value;

  // Best-effort revocation — don't fail if token is already gone
  if (refreshToken) {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch { /* ignore */ }
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.delete(COOKIE_NAME);
  return res;
}
