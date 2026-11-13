/**
 * Where to send someone after they log in: only a path on this site.
 *
 * An open redirect on a login page is how phishing hands a victim back to a
 * lookalike. Checking for a leading "/" is not enough: browsers read "/\evil"
 * as "//evil", another host. So the value is resolved as a URL against a
 * placeholder origin and kept only if it stays on that origin.
 */
export const DEFAULT_NEXT = "/ops/recommendations";

export function safeNext(value: string | null | undefined, fallback: string = DEFAULT_NEXT): string {
  if (!value || !value.startsWith("/") || /[\\\u0000-\u001f]/.test(value)) return fallback;
  try {
    const base = "http://same.invalid";
    const url = new URL(value, base);
    if (url.origin !== base) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
