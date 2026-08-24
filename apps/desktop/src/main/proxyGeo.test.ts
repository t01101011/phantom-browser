import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { fetchJsonWithAbsoluteDeadline, probeProxyGeo } from "./proxyGeo.ts";

const proxy = { type: "http", host: "127.0.0.1", port: 8080 } as const;

test("multi-provider geo fallback shares one overall deadline", async () => {
  let now = 1_000;
  const budgets: number[] = [];
  await assert.rejects(
    probeProxyGeo(proxy, {
      timeoutMs: 100,
      now: () => now,
      fetchJson: async (_url, _proxy, timeoutMs) => {
        budgets.push(timeoutMs);
        now += 60;
        throw new Error("down");
      },
    }),
    /All geo-IP providers failed/,
  );
  assert.deepEqual(budgets, [100, 40]);
});

test("geo fallback stops once its overall deadline is exhausted", async () => {
  let now = 2_000;
  let calls = 0;
  await assert.rejects(
    probeProxyGeo(proxy, {
      timeoutMs: 100,
      now: () => now,
      fetchJson: async () => {
        calls += 1;
        now += 100;
        throw new Error("timed out");
      },
    }),
    /deadline reached/,
  );
  assert.equal(calls, 1);
});

test("proxy geo HTTP read enforces an absolute deadline against slow-drip bodies", async () => {
  const server = createServer((_req, res) => {
    res.writeHead(200, { "content-type": "application/json" });
    const interval = setInterval(() => res.write(" "), 15);
    res.on("close", () => clearInterval(interval));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  const started = Date.now();
  try {
    await assert.rejects(
      fetchJsonWithAbsoluteDeadline(`http://127.0.0.1:${address.port}/`, undefined, 60),
      /timed out/,
    );
    assert(Date.now() - started < 500);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("proxy geo HTTP read rejects oversized response bodies", async () => {
  const server = createServer((_req, res) => {
    res.end(`{"value":"${"x".repeat(128)}"}`);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  try {
    await assert.rejects(
      fetchJsonWithAbsoluteDeadline(`http://127.0.0.1:${address.port}/`, undefined, 500, 64),
      /response too large/,
    );
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("proxy geo HTTP error destroys a slow-drip response without leaving a socket alive", async () => {
  let responseClosed = false;
  const server = createServer((_req, res) => {
    res.writeHead(500, { "content-type": "text/plain" });
    const interval = setInterval(() => res.write("error "), 15);
    res.on("close", () => {
      responseClosed = true;
      clearInterval(interval);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  try {
    await assert.rejects(
      fetchJsonWithAbsoluteDeadline(`http://127.0.0.1:${address.port}/`, undefined, 500),
      /HTTP 500/,
    );
    await new Promise((resolve) => setTimeout(resolve, 50));
    assert.equal(responseClosed, true);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
