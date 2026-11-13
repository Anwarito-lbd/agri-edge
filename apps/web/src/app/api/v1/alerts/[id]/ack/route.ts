import { ackAlert } from "@/lib/mock-pi/state";
import { FORBIDDEN_OPS } from "@/lib/mock-pi/types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Ctx = { params: Promise<{ id: string }> };

/**
 * Ack-only. Still not a vehicle command.
 * Rejects any body that looks like a forbidden flight op.
 */
export async function POST(request: Request, ctx: Ctx) {
  const { id } = await ctx.params;

  let body: unknown = null;
  try {
    const text = await request.text();
    if (text) body = JSON.parse(text);
  } catch {
    return Response.json(
      { error: "invalid_json", demo: true },
      { status: 400 },
    );
  }

  if (body && typeof body === "object") {
    const op = (body as { op?: unknown }).op;
    if (typeof op === "string") {
      const normalized = op.toLowerCase();
      if ((FORBIDDEN_OPS as readonly string[]).includes(normalized)) {
        return Response.json(
          {
            error: "forbidden_op",
            message:
              "Companion API is read-only toward the aircraft. Arm/mode/mission/MAVLink write ops are rejected.",
            op: normalized,
            demo: true,
          },
          { status: 403 },
        );
      }
      if (normalized !== "ack_alert") {
        return Response.json(
          {
            error: "unknown_op",
            message: "Only ack_alert is accepted on this route.",
            op: normalized,
            demo: true,
          },
          { status: 400 },
        );
      }
    }
  }

  const alert = ackAlert(id);
  if (!alert) {
    return Response.json(
      { error: "not_found", id, demo: true },
      { status: 404 },
    );
  }

  return Response.json({
    schema_version: 1,
    ok: true,
    demo: true,
    alert,
  });
}

/** Reject non-ack methods that might look like commands. */
export async function PUT() {
  return rejectWrite();
}
export async function PATCH() {
  return rejectWrite();
}
export async function DELETE() {
  return rejectWrite();
}

function rejectWrite() {
  return Response.json(
    {
      error: "method_not_allowed",
      message: "Ack via POST only. No vehicle command endpoints exist.",
      demo: true,
    },
    { status: 405 },
  );
}
