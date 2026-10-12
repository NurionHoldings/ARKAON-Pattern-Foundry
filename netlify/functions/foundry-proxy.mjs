const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "if-match",
  "idempotency-key",
  "x-csrf-token",
  "x-tenant-id",
];
const FORWARDED_RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-security-policy",
  "content-type",
  "location",
  "referrer-policy",
  "www-authenticate",
  "x-content-type-options",
];

function configuredOrigin() {
  const value = globalThis.Netlify?.env?.get?.("APF_API_ORIGIN") ?? process.env.APF_API_ORIGIN;
  if (!value) return null;
  try {
    const origin = new URL(value);
    if (
      origin.protocol !== "https:" || origin.username || origin.password ||
      origin.pathname !== "/" || origin.search || origin.hash || !origin.hostname ||
      origin.hostname === "localhost" || origin.hostname.endsWith(".localhost") ||
      origin.hostname.endsWith(".local") || /^\d{1,3}(?:\.\d{1,3}){3}$/.test(origin.hostname) ||
      origin.hostname.includes(":")
    ) return null;
    return origin.origin;
  } catch {
    return null;
  }
}

function validPath(path) {
  if (
    !path.startsWith("/") || path.includes("\\") || path.includes("//") ||
    /[\u0000-\u001f\u007f]/.test(path) ||
    path.split("/").some((part) => part === "." || part === "..")
  ) return false;
  return path === "/health" || path === "/console" || path.startsWith("/console/") || path.startsWith("/v1/console/");
}

function requestHeaders(source) {
  const result = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = source.get(name);
    if (value) result.set(name, value);
  }
  result.set("cache-control", "no-store");
  return result;
}

function responseHeaders(source) {
  const result = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = source.get(name);
    if (value) result.set(name, value);
  }
  result.set("cache-control", "no-store");
  for (const cookie of source.getSetCookie?.() || []) result.append("set-cookie", cookie);
  return result;
}

function errorResponse(status, code) {
  return Response.json({ error: code }, { status, headers: { "cache-control": "no-store" } });
}

export async function handler(request) {
  const origin = configuredOrigin();
  if (!origin) return errorResponse(503, "foundry_api_not_configured");
  const incoming = new URL(request.url);
  const path = incoming.pathname;
  if (!validPath(path) || path === "/console/dev/session") return errorResponse(404, "not_found");
  const method = request.method.toUpperCase();
  if (!ALLOWED_METHODS.has(method)) return errorResponse(405, "method_not_allowed");

  const upstreamUrl = new URL(`${path}${incoming.search}`, origin);
  const options = { method, headers: requestHeaders(request.headers), redirect: "manual" };
  if (method !== "GET" && method !== "HEAD") options.body = await request.arrayBuffer();
  try {
    const upstream = await fetch(upstreamUrl, options);
    const body = method === "HEAD" || upstream.status === 204 || upstream.status === 304
      ? null : await upstream.arrayBuffer();
    return new Response(body, { status: upstream.status, headers: responseHeaders(upstream.headers) });
  } catch {
    return errorResponse(502, "foundry_api_unavailable");
  }
}

export const config = { path: ["/health", "/console", "/console/*", "/v1/console/*"] };
export default handler;
