const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function resolveApiBase(base: string, pageHostname?: string): string {
  if (!pageHostname || !LOOPBACK_HOSTS.has(pageHostname)) return base;

  let url: URL;
  try {
    url = new URL(base);
  } catch {
    return base;
  }
  if (!LOOPBACK_HOSTS.has(url.hostname) || url.hostname === pageHostname)
    return base;

  // Lax session cookies require the same site, even for local development.
  url.hostname = pageHostname;
  return url.toString().replace(/\/$/, "");
}
