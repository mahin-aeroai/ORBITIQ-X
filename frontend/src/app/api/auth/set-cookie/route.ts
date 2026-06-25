/**
 * POST /api/auth/set-cookie
 * Store the refresh token in an HttpOnly cookie so JavaScript cannot read it.
 */
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "orbitiq_refresh";
const DAYS_7_SEC  = 7 * 24 * 60 * 60;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const { refresh_token } = await req.json();

  if (!refresh_token || typeof refresh_token !== "string") {
    return NextResponse.json({ error: "Invalid token" }, { status: 400 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE_NAME, refresh_token, {
    httpOnly: true,
    secure:   process.env.NODE_ENV === "production",
    sameSite: "lax",
    path:     "/",
    maxAge:   DAYS_7_SEC,
  });
  return res;
}
