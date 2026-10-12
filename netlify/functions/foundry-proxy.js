"use strict";

const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]);
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

function apiOriginFromEnvironment() {
  const value = process.env.APF_API_ORIGIN;
  if (!value) return null;

  try {
    const origin = new URL(value);
    if (
      origin.protocol !== "https:" ||
      origin.username ||
      origin.password ||
      origin.pathname !== "/" ||
      origin.search ||
      origin.hash ||
      !origin.hostname ||
      origin.hostname === "localhost" ||
      origin.hostname.endsWith(".localhost") ||
      origin.hostname.endsWith(".local") ||
      /^\d{1,3}(?:\.\d{1,3}){3}$/.test(origin.hostname) ||
      origin.hostname.includes(":")
    ) {
      return null;
    }
    return origin.origin;
  } catch {
    return null;
  }
}

function requestedPath(event) {
  let value = event.queryStringParameters?.proxy_path;
  if (!value && event.rawUrl) {
    value = new URL(event.rawUrl).searchParams.get("proxy_path");
  }
  if (typeof value !== "string" || !value.startsWith("/")) return null;

  let path;
  try {
    path = decodeURIComponent(value);
  } catch {
    return null;
  }
  if (
    path.includes("\\") ||
    path.includes("//") ||
    /[\u0000-\u001f\u007f]/.test(path) ||
    path.split("/").some((part) => part === "." || part === "..")
  ) {
    return null;
  }
  if (path === "/health" || path === "/console" || path.startsWith("/console/") || path.startsWith("/v1/")) {
    return path;
  }
  return null;
}

function requestUrl(event, origin, path) {
  const upstream = new URL(path, origin);
  const query = new URL(event.rawUrl || "https://netlify-function.invalid/").searchParams;
  query.delete("proxy_path");
  upstream.search = query.toString();
  return upstream;
}

function requestHeaders(event) {
  const source = Object.fromEntries(
    Object.entries(event.headers || {}).map(([key, value]) => [key.toLowerCase(), value]),
  );
  const result = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = source[name];
    if (typeof value === "string" && value.length > 0) result.set(name, value);
  }
  return result;
}

function responseHeaders(upstream) {
  const headers = {};
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers[name] = value;
  }
  headers["cache-control"] = "no-store";
  return headers;
}

function reply(statusCode, body) {
  return {
    statusCode,
    headers: { "cache-control": "no-store", "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ error: body }),
  };
}

async function handler(event) {
  const origin = apiOriginFromEnvironment();
  if (!origin) return reply(503, "foundry_api_not_configured");

  const path = requestedPath(event);
  if (!path) return reply(404, "not_found");
  if (path === "/console/dev/session") return reply(404, "not_found");

  const method = String(event.httpMethod || "GET").toUpperCase();
  if (!ALLOWED_METHODS.has(method)) return reply(405, "method_not_allowed");

  const headers = requestHeaders(event);
  headers.set("cache-control", "no-store");
  const options = { method, headers, redirect: "manual" };
  if (!new Set(["GET", "HEAD"]).has(method) && event.body) {
    options.body = event.isBase64Encoded
      ? Buffer.from(event.body, "base64")
      : event.body;
  }

  try {
    const upstream = await fetch(requestUrl(event, origin, path), options);
    const result = {
      statusCode: upstream.status,
      headers: responseHeaders(upstream),
      body: "",
    };

    const setCookies = upstream.headers.getSetCookie?.() || [];
    if (setCookies.length) result.multiValueHeaders = { "set-cookie": setCookies };

    if (method !== "HEAD" && upstream.status !== 204 && upstream.status !== 304) {
      result.body = Buffer.from(await upstream.arrayBuffer()).toString("base64");
      result.isBase64Encoded = true;
    }
    return result;
  } catch {
    return reply(502, "foundry_api_unavailable");
  }
}

module.exports = {
  handler,
  apiOriginFromEnvironment,
  requestedPath,
};
