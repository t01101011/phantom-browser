import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { fetchJsonWithAbsoluteDeadline, probeProxyGeo } from "./proxyGeo.ts";

const proxy = { type: "http", host: "127.0.0.1", port: 8080 } as const;

test("multi-provider geo fallback gives each provider a fresh deadline", async () => {
  const budgets: number[] = [];
  await assert.rejects(
    probeProxyGeo(proxy, {
      timeoutMs: 100,
      fetchJson: async (_url, _proxy, timeoutMs) => {
        budgets.push(timeoutMs);
        throw new Error("down");
      },
    }),
    /All geo-IP providers failed/,
  );
  assert.deepEqual(budgets, [100, 100, 100, 100]);
});

test("geo fallback still tries the next provider after the first provider uses its deadline", async () => {
  let calls = 0;
  const result = await probeProxyGeo(proxy, {
    timeoutMs: 100,
    fetchJson: async () => {
      calls += 1;
      if (calls === 1) {
        throw new Error("proxy probe timed out");
      }
      return {
        ip: "203.0.113.10",
        country_code: "US",
        country_name: "United States",
        timezone: "America/New_York",
        city: "New York",
        latitude: 40.7128,
        longitude: -74.006,
      };
    },
  });
  assert.equal(calls, 2);
  assert.equal(result.country, "us");
  assert.equal(result.latitude, 40.7128);
});

test("geo fallback uses ip-api when HTTPS providers are unavailable", async () => {
  let calls = 0;
  const result = await probeProxyGeo(proxy, {
    timeoutMs: 100,
    fetchJson: async () => {
      calls += 1;
      if (calls < 3) throw new Error("HTTP 403");
      return {
        status: "success",
        query: "203.0.113.10",
        country: "United States",
        countryCode: "US",
        timezone: "America/New_York",
        city: "New York",
        lat: 40.7128,
        lon: -74.006,
      };
    },
  });
  assert.equal(calls, 3);
  assert.equal(result.country, "us");
  assert.equal(result.longitude, -74.006);
});

test("geo fallback uses ipapi.is after the existing providers are unavailable", async () => {
  let calls = 0;
  const result = await probeProxyGeo(proxy, {
    timeoutMs: 100,
    fetchJson: async () => {
      calls += 1;
      if (calls < 4) throw new Error("HTTP 403");
      return {
        ip: "203.0.113.10",
        location: {
          country: "United States",
          country_code: "US",
          city: "New York",
          timezone: "America/New_York",
          latitude: 40.7128,
          longitude: -74.006,
        },
      };
    },
  });
  assert.equal(calls, 4);
  assert.equal(result.country, "us");
  assert.equal(result.latitude, 40.7128);
});

test("ip-api fallback rejects out-of-range coordinates", async () => {
  await assert.rejects(
    probeProxyGeo(proxy, {
      fetchJson: async () => ({
        status: "success",
        query: "203.0.113.10",
        country: "United States",
        countryCode: "US",
        timezone: "America/New_York",
        lat: 123,
        lon: -74.006,
      }),
    }),
    /All geo-IP providers failed/,
  );
});

test("fallback skips malformed coordinates from every provider", async () => {
  let calls = 0;
  const result = await probeProxyGeo(proxy, {
    fetchJson: async () => {
      calls += 1;
      if (calls === 1) {
        return {
          success: true,
          ip: "203.0.113.10",
          country_code: "US",
          country: "United States",
          timezone: { id: "America/New_York" },
          latitude: Number.NaN,
          longitude: -74,
        };
      }
      if (calls === 2) {
        return {
          ip: "203.0.113.10",
          country_code: "US",
          country_name: "United States",
          timezone: "America/New_York",
          latitude: 123,
          longitude: -74,
        };
      }
      return {
        status: "success",
        query: "203.0.113.10",
        country: "United States",
        countryCode: "US",
        timezone: "America/New_York",
        lat: 40.7128,
        lon: -74.006,
      };
    },
  });
  assert.equal(calls, 3);
  assert.equal(result.latitude, 40.7128);
});

test("provider-controlled failures are reduced to bounded categories", async () => {
  await assert.rejects(
    probeProxyGeo(proxy, {
      fetchJson: async () => {
        throw new Error("evil\nsecret-user:secret-password@proxy.invalid");
      },
    }),
    (error: Error) => {
      assert.match(error.message, /ipwho\.is: unavailable/);
      assert.doesNotMatch(error.message, /evil|secret-user|secret-password|proxy\.invalid|\n/);
      return true;
    },
  );
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
