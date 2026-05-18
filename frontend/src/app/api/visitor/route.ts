import { randomUUID } from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { visitorCookieName } from "@/lib/auth";

const VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export async function GET(request?: NextRequest | Request) {
  const visitorId = readVisitorId(request) ?? randomUUID();
  const response = NextResponse.json({ visitorId });

  response.cookies.set({
    name: visitorCookieName,
    value: visitorId,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: VISITOR_COOKIE_MAX_AGE,
  });

  return response;
}

function readVisitorId(request?: NextRequest | Request) {
  const cookieHeader = request?.headers.get("cookie") ?? "";
  const match = cookieHeader.match(
    new RegExp(`(?:^|;\\s*)${visitorCookieName}=([^;]+)`),
  );
  return match?.[1] ?? null;
}
