import { createServer } from "node:http";
import { request as httpRequest } from "node:http";

/**
 * CORS shim for the e2e harness.
 *
 * FastMCP's `create_streamable_http_app` documents that `allowed_origins` is
 * only the Host/Origin request guard and that CORS must be "configured
 * separately when browser JavaScript must read cross-origin responses". The
 * python fixture binds a loopback port with no CORS middleware, so a browser
 * page on :8080 cannot read its responses at all.
 *
 * This process stands in front of the fixture and adds exactly the CORS
 * response headers a CORS-configured deployment would send, then streams the
 * body through untouched so Streamable HTTP and SSE behave normally. It is test
 * infrastructure: no production code relaxes any policy for it, the request is
 * forwarded verbatim (including `Authorization`), and nothing is logged.
 *
 * Usage: node cors-proxy.mjs <targetUrl>
 * Prints `OUBLIAI_CORS_PROXY_URL=<url>` once listening.
 */

const target = process.argv[2];
if (!target) {
  process.stderr.write("usage: node cors-proxy.mjs <targetUrl>\n");
  process.exit(2);
}
const targetUrl = new URL(target);

// `mcp-session-id` and `mcp-protocol-version` must be readable by the browser
// client; the rest mirror what the transport sends.
const EXPOSED_HEADERS = "mcp-session-id, mcp-protocol-version, www-authenticate";
const ALLOWED_HEADERS =
  "authorization, content-type, accept, mcp-method, mcp-name, mcp-session-id, mcp-protocol-version, last-event-id";

function applyCors(req, res) {
  const origin = req.headers.origin;
  if (typeof origin === "string" && origin.length > 0) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", ALLOWED_HEADERS);
  res.setHeader("Access-Control-Expose-Headers", EXPOSED_HEADERS);
  res.setHeader("Access-Control-Max-Age", "600");
}

const server = createServer((req, res) => {
  applyCors(req, res);

  if (req.method === "OPTIONS") {
    res.statusCode = 204;
    res.end();
    return;
  }

  const forwardedHeaders = { ...req.headers };
  delete forwardedHeaders.host;
  delete forwardedHeaders.origin;
  delete forwardedHeaders.referer;
  forwardedHeaders.host = targetUrl.host;

  const upstream = httpRequest(
    {
      protocol: targetUrl.protocol,
      hostname: targetUrl.hostname,
      port: targetUrl.port,
      method: req.method,
      path: targetUrl.pathname + (req.url?.includes("?") ? req.url.slice(req.url.indexOf("?")) : ""),
      headers: forwardedHeaders,
    },
    (upstreamRes) => {
      for (const [key, value] of Object.entries(upstreamRes.headers)) {
        if (value !== undefined && !key.toLowerCase().startsWith("access-control-")) {
          res.setHeader(key, value);
        }
      }
      applyCors(req, res);
      res.statusCode = upstreamRes.statusCode ?? 502;
      upstreamRes.pipe(res);
    },
  );

  upstream.on("error", (error) => {
    res.statusCode = 502;
    res.end(`upstream error: ${error.message}`);
  });

  req.pipe(upstream);
});

server.listen(0, "127.0.0.1", () => {
  const address = server.address();
  if (address === null || typeof address === "string") {
    process.stderr.write("proxy failed to bind a TCP port\n");
    process.exit(1);
  }
  process.stdout.write(
    `OUBLIAI_CORS_PROXY_URL=http://127.0.0.1:${address.port}${targetUrl.pathname}\n`,
  );
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
