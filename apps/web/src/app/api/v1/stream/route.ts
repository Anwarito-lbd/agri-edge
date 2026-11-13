import { nextStreamFrames, getStatusSnapshot } from "@/lib/mock-pi/state";
import { FORBIDDEN_OPS, type Topic } from "@/lib/mock-pi/types";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
/** Allow longer SSE on platforms that honor maxDuration (e.g. Vercel). */
export const maxDuration = 60;

const ALL_TOPICS: Topic[] = [
  "heartbeat",
  "gps",
  "battery",
  "detections",
  "qa_flags",
  "advisory",
  "dock",
  "alert",
];

/**
 * SSE demo mock-Pi feed (synthetic, never a live aircraft). Prefer SSE over WS for Vercel.
 * Emits topic frames every ~2s. Read-only — no arm/mode/mission writes.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const topicsParam = url.searchParams.get("topics");
  const wanted = new Set<Topic>(
    topicsParam
      ? (topicsParam
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean) as Topic[])
      : ALL_TOPICS,
  );

  const encoder = new TextEncoder();
  let closed = false;
  let interval: ReturnType<typeof setInterval> | null = null;

  const stream = new ReadableStream({
    start(controller) {
      const send = (frame: { topic: string }) => {
        if (closed) return;
        if (!wanted.has(frame.topic as Topic) && frame.topic !== "snapshot") {
          return;
        }
        const payload = `event: ${frame.topic}\ndata: ${JSON.stringify(frame)}\n\n`;
        try {
          controller.enqueue(encoder.encode(payload));
        } catch {
          cleanup();
        }
      };

      const cleanup = () => {
        if (closed) return;
        closed = true;
        if (interval) clearInterval(interval);
        interval = null;
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      // Initial snapshot as a convenience bootstrap event
      const snap = getStatusSnapshot();
      try {
        controller.enqueue(
          encoder.encode(
            `event: snapshot\ndata: ${JSON.stringify(snap)}\n\n`,
          ),
        );
      } catch {
        cleanup();
        return;
      }

      // Comment keep-alive + first tick soon
      interval = setInterval(() => {
        if (closed) return;
        if (request.signal.aborted) {
          cleanup();
          return;
        }
        try {
          const frames = nextStreamFrames();
          for (const f of frames) send(f);
          // SSE comment keep-alive
          controller.enqueue(encoder.encode(`: ping ${Date.now()}\n\n`));
        } catch {
          cleanup();
        }
      }, 2000);

      request.signal.addEventListener("abort", cleanup);
    },
    cancel() {
      closed = true;
      if (interval) clearInterval(interval);
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
      "X-Agri-Edge-Demo": "mock-pi",
    },
  });
}

/**
 * Reject WS-style command posts. Only subscribe/ping semantics would be
 * allowed on a real WS; here we refuse all writes on the stream path.
 */
export async function POST(request: Request) {
  let op: string | undefined;
  try {
    const body = (await request.json()) as { op?: string };
    op = typeof body.op === "string" ? body.op.toLowerCase() : undefined;
  } catch {
    /* ignore */
  }

  if (op && (FORBIDDEN_OPS as readonly string[]).includes(op)) {
    return Response.json(
      {
        error: "forbidden_op",
        message:
          "Companion stream is read-only. Arm/mode/mission/MAVLink write ops are rejected.",
        op,
        demo: true,
      },
      { status: 403 },
    );
  }

  return Response.json(
    {
      error: "unknown_op",
      message:
        "SSE stream is GET-only. Allowed companion verbs elsewhere: subscribe (via ?topics=), ping (SSE comments), ack_alert (POST /api/v1/alerts/{id}/ack).",
      op: op ?? null,
      demo: true,
    },
    { status: 400 },
  );
}
