/**
 * The map basemap, in one place.
 *
 * OpenStreetMap standard tiles: no API key, loads straight from the browser.
 * The Esri World_Dark_Gray tiles this replaced failed in browsers
 * (ERR_FAILED) and left the maps blank.
 *
 * OSM's tile usage policy (https://operations.osmfoundation.org/policies/tiles/)
 * allows light use with attribution and a valid Referer, which this site's
 * Referrer-Policy (strict-origin-when-cross-origin) sends. It is fine for a
 * prototype and a pitch; a deployment with real traffic should move to a paid
 * or self-hosted tile provider and change only this file, the CSP host in
 * next.config.ts (which imports it) and TILE_HOST in public/sw.js.
 */

export const BASEMAP_HOST = "https://tile.openstreetmap.org";
export const BASEMAP_URL = `${BASEMAP_HOST}/{z}/{x}/{y}.png`;
export const BASEMAP_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';
export const BASEMAP_MAX_ZOOM = 19;

/** How many failed tiles, with none loaded, before the map says the basemap is down. */
export const TILE_FAILURE_THRESHOLD = 4;
