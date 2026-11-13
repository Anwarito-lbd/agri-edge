import { advanceClock, getDetectionsGeoJson } from "@/lib/mock-pi/state";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Current mission detections as GeoJSON FeatureCollection (DEMO). */
export async function GET() {
  // Light tick so geojson reflects live-ish positions without requiring SSE
  advanceClock();
  const fc = getDetectionsGeoJson();
  return Response.json(fc, {
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/geo+json; charset=utf-8",
      "X-Agri-Edge-Demo": "mock-pi",
    },
  });
}
