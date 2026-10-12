import assert from "node:assert/strict";
import test from "node:test";
import { handler, config } from "../netlify/functions/foundry-proxy.mjs";

function request(path, { method = "GET", query = "", headers = {}, body } = {}) {
  const url = new URL(path + (query ? `?${query}` : ""), "https://arkaonfoundry.netlify.app");
  return new Request(url, { method, headers, body });
}

test("function binds API paths and requires a public HTTPS API origin", async () => {
  const previous = process.env.APF_API_ORIGIN;
  delete process.env.APF_API_ORIGIN;
  assert.deepEqual(config.path, ["/health", "/console", "/console/*", "/v1/console/*"]);
  assert.equal((await handler(request("/health"))).status, 503);
  process.env.APF_API_ORIGIN = "http://api.example.test";
  assert.equal((await handler(request("/health"))).status, 503);
  process.env.APF_API_ORIGIN = "https://localhost:8443";
  assert.equal((await handler(request("/health"))).status, 503);
  if (previous === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previous;
});

test("proxy forwards session and CSRF headers without CORS", async () => {
  const previousOrigin = process.env.APF_API_ORIGIN;
  const previousFetch = globalThis.fetch;
  process.env.APF_API_ORIGIN = "https://api.example.test";
  let requested;
  globalThis.fetch = async (url, options) => {
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
  const response = await handler(request("/console", {
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
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "<h1>Foundry</h1>");
  assert.equal(response.headers.get("content-security-policy"), "default-src 'none'");
  assert.match(response.headers.get("set-cookie"), /HttpOnly; Secure; SameSite=Strict/);
  assert.equal(response.headers.get("access-control-allow-origin"), null);
  assert.equal(response.headers.get("cache-control"), "no-store");
  globalThis.fetch = previousFetch;
  if (previousOrigin === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previousOrigin;
});

test("public proxy blocks the development session endpoint", async () => {
  const previousOrigin = process.env.APF_API_ORIGIN;
  const previousFetch = globalThis.fetch;
  process.env.APF_API_ORIGIN = "https://api.example.test";
  globalThis.fetch = async () => { throw new Error("must not call upstream"); };
  assert.equal((await handler(request("/console/dev/session", { method: "POST", body: "{}" }))).status, 404);
  globalThis.fetch = previousFetch;
  if (previousOrigin === undefined) delete process.env.APF_API_ORIGIN;
  else process.env.APF_API_ORIGIN = previousOrigin;
});

test("proxy rejects traversal and unapproved routes", async () => {
  process.env.APF_API_ORIGIN = "https://api.example.test";
  assert.equal((await handler(request("/v1/../console/dev/session"))).status, 404);
  assert.equal((await handler(request("/admin"))).status, 404);
  assert.equal((await handler(request("/v1/targets", { method: "GET" }))).status, 404);
});
