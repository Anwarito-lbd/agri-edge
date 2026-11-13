/*
 * agri-edge service worker: the ops screens keep working in a field with no
 * signal, showing the last data this device saw.
 *
 * Rules:
 *  - Only GET is ever cached. POSTs (acknowledge, approve, ...) go straight to
 *    the network and fail visibly offline: an approval must never be queued
 *    and replayed later without the person seeing it happen.
 *  - /api/ops/* reads: network first; a successful answer is kept, stamped
 *    with x-ae-cached-at; offline, the kept answer is served with that stamp
 *    so the page can say how old it is.
 *  - /api/auth/* and prescription exports: network only.
 *  - Map tiles: cache first, bounded.
 *  - Pages: network first, falling back to the cached page or the ops shell.
 *  - On logout the page posts {type: "logout"} and the API cache is dropped.
 */

const VERSION = "v2"; // v2: basemap moved from Esri to OpenStreetMap; drops the old tile cache
const SHELL_CACHE = `ae-shell-${VERSION}`;
const API_CACHE = `ae-api-${VERSION}`;
const TILE_CACHE = `ae-tiles-${VERSION}`;
const MAX_TILES = 800;
const SHELL = ["/ops", "/ops/recommendations", "/ops/alerts", "/ops/map", "/login", "/manifest.webmanifest"];
const TILE_HOST = "tile.openstreetmap.org"; // keep in step with src/lib/basemap.ts
const CACHED_AT = "x-ae-cached-at";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((c) => Promise.all(SHELL.map((u) => c.add(u).catch(() => undefined)))),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k.startsWith("ae-") && ![SHELL_CACHE, API_CACHE, TILE_CACHE].includes(k))
          .map((k) => caches.delete(k)),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "logout") {
    event.waitUntil(caches.delete(API_CACHE));
  }
});

function classify(request) {
  if (request.method !== "GET") return "network";
  const url = new URL(request.url);
  if (url.hostname === TILE_HOST) return "tile";
  if (url.origin !== self.location.origin) return "network";
  if (url.pathname.startsWith("/api/auth/")) return "network";
  if (url.pathname.startsWith("/api/ops/")) {
    return url.pathname.endsWith("/export") ? "network" : "api";
  }
  if (url.pathname.startsWith("/_next/static/")) return "static";
  if (request.mode === "navigate") return "page";
  return "network";
}

async function stamp(response) {
  const headers = new Headers(response.headers);
  headers.set(CACHED_AT, new Date().toISOString());
  const body = await response.clone().arrayBuffer();
  return new Response(body, { status: response.status, statusText: response.statusText, headers });
}

async function apiRead(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const fresh = await fetch(request);
    if (fresh.ok) await cache.put(request, await stamp(fresh));
    return fresh;
  } catch {
    const kept = await cache.match(request);
    if (kept) return kept;
    return new Response(JSON.stringify({ error: "ops_unreachable", offline: true, simulation: true }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function tile(request) {
  const cache = await caches.open(TILE_CACHE);
  const kept = await cache.match(request);
  if (kept) return kept;
  let fresh;
  try {
    fresh = await fetch(request);
  } catch {
    return Response.error(); // offline and not cached: the map shows its own note
  }
  if (fresh.ok || fresh.type === "opaque") {
    await cache.put(request, fresh.clone());
    const keys = await cache.keys();
    for (const k of keys.slice(0, Math.max(0, keys.length - MAX_TILES))) await cache.delete(k);
  }
  return fresh;
}

async function staticAsset(request) {
  const cache = await caches.open(SHELL_CACHE);
  const kept = await cache.match(request);
  if (kept) return kept;
  const fresh = await fetch(request);
  if (fresh.ok) await cache.put(request, fresh.clone());
  return fresh;
}

async function page(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const fresh = await fetch(request);
    if (fresh.ok) await cache.put(request, fresh.clone());
    return fresh;
  } catch {
    return (await cache.match(request)) || (await cache.match("/ops")) || Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const kind = classify(event.request);
  if (kind === "network") return;           // the browser handles it; nothing cached
  const handler = { api: apiRead, tile, static: staticAsset, page }[kind];
  event.respondWith(handler(event.request));
});

if (typeof module !== "undefined") module.exports = { classify, CACHED_AT };
