import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const expectedUser = process.env.FADS_DISPATCH_USER;
  const expectedPassword = process.env.FADS_DISPATCH_PASSWORD;
  if (!expectedUser || !expectedPassword) {
    return new NextResponse("Dispatcher authentication is not configured.", { status: 503 });
  }

  const authorization = request.headers.get("authorization");
  const expected = `Basic ${Buffer.from(`${expectedUser}:${expectedPassword}`).toString("base64")}`;
  if (authorization !== expected) {
    return new NextResponse("Authentication required.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="FADS Dispatch"' },
    });
  }

  return NextResponse.next();
}

export const config = { matcher: ["/dispatch/:path*"] };
