import express from "express";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Static server for the customer page — the *embedding* origin.
 *
 * It only serves `dist/` (the built page) and two tiny endpoints:
 *
 *   GET /healthz          liveness for the e2e harness
 *   GET /api/connection   development-only connection descriptor. The
 *                         customer's trusted backend owns the user's token; it
 *                         is handed to the page only when
 *                         `OUBLIAI_DEV_CONNECTION=1`, `OUBLIAI_MCP_URL` and
 *                         `OUBLIAI_TOKEN` are all set, and 404s otherwise.
 *
 * The sandbox origin is NOT served here. The page points its iframe at the
 * `packages/app` sandbox server (`http://localhost:8081/sandbox.html`), which
 * keeps host and sandbox on different origins as the MCP Apps spec requires
 * and lets that server's referrer allowlist and CSP header stay in force.
 */

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, "dist");
const PORT = Number.parseInt(process.env.EMBED_PORT ?? "8090", 10);

const app = express();

app.get("/healthz", (_req, res) => {
  res.json({ status: "ok" });
});

app.get("/api/connection", (_req, res) => {
  const url = process.env.OUBLIAI_MCP_URL;
  const token = process.env.OUBLIAI_TOKEN;
  if (
    process.env.NODE_ENV === "production" ||
    process.env.OUBLIAI_DEV_CONNECTION !== "1" ||
    !url ||
    !token
  ) {
    res.status(404).json({ error: "connection not configured" });
    return;
  }
  res.json({ url, token });
});

app.use(express.static(DIST));

const server = app.listen(PORT, "localhost", (error) => {
  if (error) {
    console.error("Error starting embed server:", error);
    process.exit(1);
  }
  console.log(`Embed page: http://localhost:${PORT}`);
});

for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
