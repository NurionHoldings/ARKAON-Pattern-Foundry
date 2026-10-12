"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const proxy = require("../netlify/functions/foundry-proxy");

function event(path, { method = "GET", query = "", headers = {}, body } = {}) {
  const params = new URLSearchParams(query);
  params.set("proxy_path", path);
  return {
    httpMethod: method,
    rawUrl: `https://arkaonfoundry.netlify.app/.netlify/functions/foundry-proxy?${params}`,
    queryStringParameters: Object.fromEntries(params.entries()),
    headers,
    body,
  };
}

test("proxy requires a public HTTPS API origin", async () => {
  const previous = process.env.APF_API_ORIGIN;
  delete process.env.APF_API_ORIGIN;
  assert.equal((await proxy.handler(event("/health"))).statusCode, 503);
  process.env.APF_API_ORIGIN = "http://api.example.test";
  assert.equal((await proxy.handler(event("/health"))).statusCode, 503);
  process.env.APF_API_ORIGIN = "https://localhost:8443";
  assert.equal((await proxy.handler(event("/health"))).statusCode, 503);
  if (previous === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previous;
});

test("proxy forwards same-origin session and CSRF headers without CORS", async () => {
  const previousOrigin = process.env.APF_API_ORIGIN;
  const previousFetch = global.fetch;
  process.env.APF_API_ORIGIN = "https://api.example.test";
  let requested;
  global.fetch = async (url, options) => {
    requested = { url: String(url), options };
    return new Response("<h1>Foundry</h1>", {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "content-security-policy": "default-src 'none'",
        "set-cookie": "apf_console_session=secret; HttpOnly; Secure; SameSite=Strict",
      },
    });
  };

  const result = await proxy.handler(event("/console", {
    query: "tab=reviews",
    headers: {
      cookie: "apf_console_session=secret; apf_console_csrf=csrf",
      "x-csrf-token": "csrf",
      origin: "https://attacker.invalid",
    },
  }));

  assert.equal(requested.url, "https://api.example.test/console?tab=reviews");
  assert.equal(requested.options.headers.get("cookie"), "apf_console_session=secret; apf_console_csrf=csrf");
  assert.equal(requested.options.headers.get("x-csrf-token"), "csrf");
  assert.equal(requested.options.headers.get("origin"), null);
  assert.equal(result.statusCode, 200);
  assert.equal(Buffer.from(result.body, "base64").toString(), "<h1>Foundry</h1>");
  assert.equal(result.headers["content-security-policy"], "default-src 'none'");
  assert.equal(result.headers["cache-control"], "no-store");

  global.fetch = previousFetch;
  if (previousOrigin === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previousOrigin;
});

test("development session endpoint is blocked at the public proxy", async () => {
  const previousOrigin = process.env.APF_API_ORIGIN;
  process.env.APF_API_ORIGIN = "https://api.example.test";
  const previousFetch = global.fetch;
  global.fetch = async () => { throw new Error("must not call upstream"); };
  assert.equal((await proxy.handler(event("/console/dev/session", { method: "POST" }))).statusCode, 404);
  global.fetch = previousFetch;
  if (previousOrigin === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previousOrigin;
});

test("proxy rejects traversal and unapproved route paths", () => {
  assert.equal(proxy.requestedPath(event("/v1/../console/dev/session")), null);
  assert.equal(proxy.requestedPath(event("/admin")), null);
});
