import { FORBIDDEN_OPS } from "@/lib/mock-pi/types";

export const dynamic = "force-dynamic";

/**
 * Explicit reject surface for anything that looks like a vehicle command.
 * The companion API must never arm, change mode, or write MAVLink.
 */
function reject(request: Request) {
  const path = new URL(request.url).pathname;
  return Response.json(
    {
      error: "forbidden_op",
      message:
        "No vehicle command endpoints exist. Phone companion is read-only status/alerts only.",
      path,
      forbidden_ops: FORBIDDEN_OPS,
      demo: true,
    },
    { status: 403 },
  );
}

export async function GET(request: Request) {
  return reject(request);
}
export async function POST(request: Request) {
  return reject(request);
}
export async function PUT(request: Request) {
  return reject(request);
}
export async function PATCH(request: Request) {
  return reject(request);
}
export async function DELETE(request: Request) {
  return reject(request);
}
