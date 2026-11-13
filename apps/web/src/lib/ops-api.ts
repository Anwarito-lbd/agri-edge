/** Same-origin client for Ops Station proxy at /api/ops/... */

export type OpsBannerFields = {
  /** The answer came from the built-in synthetic sample data, not a live station. */
  demo?: boolean;
  simulation?: boolean;
  banner?: string | null;
  offline?: boolean;
  error?: string;
  message?: string;
};

export type OpsResult<T> =
  | { ok: true; data: T; offline: false; cachedAt?: string }
  | {
      ok: false;
      error: string;
      offline: boolean;
      data?: T & OpsBannerFields;
      /** 401: nobody is logged in and the station requires it. */
      authRequired?: boolean;
      /** 403: logged in, but this role may not do it. */
      forbidden?: boolean;
    };

/** Header the service worker adds when it answers from its cache (public/sw.js). */
export const CACHED_AT_HEADER = "x-ae-cached-at";

function isOfflinePayload(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") return false;
  const p = payload as Record<string, unknown>;
  return p.offline === true || p.error === "ops_unreachable";
}

export function isDemo(data: OpsBannerFields | null | undefined): boolean {
  return !!data && data.demo === true;
}

export function isSimulation(data: OpsBannerFields | null | undefined): boolean {
  if (!data) return false;
  if (data.offline === true) return true;
  if (data.simulation === true) return true;
  if (data.banner === "SIMULATION") return true;
  // Prefer API fields; if overview omits banner but seed left simulation_mode, still show
  return false;
}

async function parseJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return { error: "invalid_json", message: res.statusText };
  }
}

export async function opsGet<T extends OpsBannerFields>(
  path: string,
): Promise<OpsResult<T>> {
  const clean = path.replace(/^\//, "");
  try {
    const res = await fetch(`/api/ops/${clean}`, {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    const data = (await parseJson(res)) as T;
    if (!res.ok || isOfflinePayload(data)) {
      return {
        ok: false,
        offline: isOfflinePayload(data) || res.status === 503,
        error:
          (data as OpsBannerFields).message ||
          (data as OpsBannerFields).error ||
          `HTTP ${res.status}`,
        data,
        authRequired: res.status === 401,
        forbidden: res.status === 403,
      };
    }
    const cachedAt = res.headers.get(CACHED_AT_HEADER) ?? undefined;
    return { ok: true, data, offline: false, cachedAt };
  } catch (err) {
    return {
      ok: false,
      offline: true,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}

export async function opsPost<T extends OpsBannerFields>(
  path: string,
  body?: unknown,
): Promise<OpsResult<T>> {
  const clean = path.replace(/^\//, "");
  try {
    const res = await fetch(`/api/ops/${clean}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body ?? {}),
    });
    const data = (await parseJson(res)) as T;
    if (!res.ok || isOfflinePayload(data)) {
      return {
        ok: false,
        offline: isOfflinePayload(data) || res.status === 503,
        error:
          (data as OpsBannerFields).message ||
          (data as OpsBannerFields).error ||
          `HTTP ${res.status}`,
        data,
        authRequired: res.status === 401,
        forbidden: res.status === 403,
      };
    }
    const cachedAt = res.headers.get(CACHED_AT_HEADER) ?? undefined;
    return { ok: true, data, offline: false, cachedAt };
  } catch (err) {
    return {
      ok: false,
      offline: true,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}
