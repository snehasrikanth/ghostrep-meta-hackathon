import assert from "node:assert/strict";
import test from "node:test";
import { resolveApiBase } from "./apiBase.ts";

test("local API requests share the page hostname so profile cookies survive", () => {
  for (const hostname of ["localhost", "127.0.0.1", "[::1]"]) {
    const base = resolveApiBase("http://localhost:8000", hostname);
    assert.equal(new URL(base).hostname, hostname);
    assert.equal(new URL(base).port, "8000");
  }
  assert.equal(
    resolveApiBase("http://127.0.0.1:8000", "localhost"),
    "http://localhost:8000",
  );
});

test("local hostname changes preserve the configured protocol, port, and API path", () => {
  assert.equal(
    resolveApiBase("https://localhost:8443/api/v1", "127.0.0.1"),
    "https://127.0.0.1:8443/api/v1",
  );
});

test("remote, relative, and server-side API addresses keep their configuration", () => {
  for (const base of ["https://api.ghostrep.example/v1", "/api"]) {
    assert.equal(resolveApiBase(base, "127.0.0.1"), base);
  }
  assert.equal(
    resolveApiBase("http://localhost:8000", "ghostrep.example"),
    "http://localhost:8000",
  );
  assert.equal(
    resolveApiBase("http://localhost:8000"),
    "http://localhost:8000",
  );
});
