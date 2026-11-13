import { getStatusSnapshot } from "@/lib/mock-pi/state";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Full companion snapshot (DEMO mock-Pi). Read-only. */
export async function GET() {
  const snapshot = getStatusSnapshot();
  return Response.json(snapshot, {
    headers: {
      "Cache-Control": "no-store",
      "X-Agri-Edge-Demo": "mock-pi",
    },
  });
}
