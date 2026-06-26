/**
 * POST /api/auth/refresh
 * Exchange HttpOnly refresh cookie for new access token + rotate refresh token.
 */
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "orbitiq_refresh";
const DAYS_7_SEC  = 7 * 24 * 60 * 60;
const API_BASE    = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/api\/v1\/?$/, "");

export async function POST(req: NextRequest): Promise<NextResponse> {
  const refreshToken = req.cookies.get(COOKIE_NAME)?.value;

  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }

  try {
    const backendRes = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!backendRes.ok) {
      // Clear stale cookie
      const errRes = NextResponse.json({ error: "Token expired" }, { status: 401 });
      errRes.cookies.delete(COOKIE_NAME);
      return errRes;
    }

    const data = await backendRes.json();
    const { access_token, refresh_token: newRefreshToken, user, expires_in } = data;

    const res = NextResponse.json({ access_token, user, expires_in });

    // Rotate refresh token cookie
    if (newRefreshToken) {
      res.cookies.set(COOKIE_NAME, newRefreshToken, {
        httpOnly: true,
        secure:   process.env.NODE_ENV === "production",
        sameSite: "lax",
        path:     "/",
        maxAge:   DAYS_7_SEC,
      });
    }

    return res;
  } catch {
    return NextResponse.json({ error: "Refresh failed" }, { status: 500 });
  }
}
