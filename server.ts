import express from "express";
import cors from "cors";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import type { McpUiResourceCsp } from "@modelcontextprotocol/ext-apps";
import {
  createChatRouter,
  devConnectionFromEnv,
} from "./packages/app/dist/route.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORT = Number.parseInt(
  process.env.PORT || process.env.HOST_PORT || "3000",
  10,
);
const SANDBOX_PORT = Number.parseInt(process.env.SANDBOX_PORT || "8081", 10);

const HOST_DIST = join(__dirname, "packages", "app", "dist", "host");
const SANDBOX_DIST = join(__dirname, "packages", "app", "dist", "sandbox");
const EMBED_DIST = join(__dirname, "examples", "embed", "dist");

const DEFAULT_STRANDS_MCP_URL = "http://127.0.0.1:8000/mcp";

function resolveMcpUrl(): string {
  if (process.env.STRANDS_MCP_URL) return process.env.STRANDS_MCP_URL;
  if (process.env.OUBLIAI_MCP_URL) return process.env.OUBLIAI_MCP_URL;
  const base = process.env.STRANDS_BASE_URL || process.env.OUBLIAI_BASE_URL;
  if (base && !base.includes("example.com")) {
    return `${base.replace(/\/+$/, "")}/mcp`;
  }
  return DEFAULT_STRANDS_MCP_URL;
}

function resolveUserToken(): string | undefined {
  return (
    process.env.STRANDS_USER_TOKEN ||
    process.env.STRANDS_ACCESS_TOKEN ||
    process.env.OUBLIAI_USER_TOKEN ||
    process.env.OUBLIAI_TOKEN ||
    process.env.OUBLIAI_ACCESS_TOKEN
  );
}

const SERVERS: string[] = process.env.SERVERS
  ? JSON.parse(process.env.SERVERS)
  : [resolveMcpUrl()];

function sanitizeCspDomains(domains?: string[]): string[] {
  if (!domains) return [];
  return domains.filter((d) => typeof d === "string" && !/[;\r\n'" ]/.test(d));
}

function buildCspHeader(csp?: McpUiResourceCsp): string {
  const resourceDomains = sanitizeCspDomains(csp?.resourceDomains).join(" ");
  const connectDomains = sanitizeCspDomains(csp?.connectDomains).join(" ");
  const frameDomains = sanitizeCspDomains(csp?.frameDomains).join(" ") || null;
  const baseUriDomains =
    sanitizeCspDomains(csp?.baseUriDomains).join(" ") || null;

  const directives = [
    "default-src 'self' 'unsafe-inline'",
    `script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: data: ${resourceDomains}`.trim(),
    `style-src 'self' 'unsafe-inline' blob: data: ${resourceDomains}`.trim(),
    `img-src 'self' data: blob: ${resourceDomains}`.trim(),
    `font-src 'self' data: blob: ${resourceDomains}`.trim(),
    `media-src 'self' data: blob: ${resourceDomains}`.trim(),
    `connect-src 'self' ${connectDomains}`.trim(),
    `worker-src 'self' blob: ${resourceDomains}`.trim(),
    frameDomains ? `frame-src ${frameDomains}` : "frame-src 'none'",
    "object-src 'none'",
    baseUriDomains ? `base-uri ${baseUriDomains}` : "base-uri 'none'",
  ];

  return directives.join("; ");
}

if (!process.env.OUBLIAI_MODEL_API_KEY && process.env.GEMINI_API_KEY) {
  process.env.OUBLIAI_MODEL_BASE_URL ||=
    "https://generativelanguage.googleapis.com/v1beta/openai/";
  process.env.OUBLIAI_MODEL_API_KEY = process.env.GEMINI_API_KEY;
  process.env.OUBLIAI_MODEL_ID ||= "gemini-2.5-flash";
}

const app = express();
app.use(cors());
app.use(express.json());

app.use(
  createChatRouter({
    connectionFor: () => {
      const explicit = devConnectionFromEnv(process.env);
      if (explicit) return explicit;
      const token = resolveUserToken();
      if (!token) return null;
      return { url: resolveMcpUrl(), token };
    },
  }),
);

app.get("/api/servers", (_req, res) => {
  res.json(SERVERS);
});

app.get("/healthz", (_req, res) => {
  res.json({ status: "ok" });
});

app.get("/api/connection", (_req, res) => {
  const mcpUrl = resolveMcpUrl();
  const userToken = resolveUserToken();
  if (!mcpUrl || !userToken) {
    res.status(404).json({ error: "connection not configured" });
    return;
  }
  res.json({
    url: mcpUrl,
    token: userToken,
    headers: { Authorization: `Bearer ${userToken}` },
  });
});

app.use("/host", express.static(HOST_DIST));
app.get("/index.js", (_req, res) => {
  res.sendFile("index.js", { root: HOST_DIST });
});

app.use("/embed", express.static(EMBED_DIST));
app.get("/embed.js", (_req, res) => {
  res.sendFile("embed.js", { root: EMBED_DIST });
});

app.use(express.static(__dirname));

const sandboxApp = express();
sandboxApp.use(cors());
sandboxApp.get(["/", "/sandbox.html"], (req, res) => {
  let cspConfig: McpUiResourceCsp | undefined;
  if (typeof req.query.csp === "string") {
    try {
      cspConfig = JSON.parse(req.query.csp);
    } catch (e) {
      console.warn("[Sandbox] Invalid CSP query param:", e);
    }
  }
  res.setHeader("Content-Security-Policy", buildCspHeader(cspConfig));
  res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Expires", "0");
  res.sendFile("sandbox.html", { root: SANDBOX_DIST });
});
sandboxApp.use((_req, res) => {
  res.status(404).send("Only sandbox.html is served on this port");
});

app.listen(PORT, "0.0.0.0", (err) => {
  if (err) {
    console.error("Error starting server:", err);
    process.exit(1);
  }
  console.log(`Strands Tools host server listening on http://0.0.0.0:${PORT}`);
});

if (SANDBOX_PORT !== PORT) {
  const sandboxServer = sandboxApp.listen(SANDBOX_PORT, "0.0.0.0", (err) => {
    if (err) {
      console.warn(`Sandbox port ${SANDBOX_PORT} unavailable:`, err.message);
      return;
    }
    console.log(`Sandbox server listening on http://0.0.0.0:${SANDBOX_PORT}`);
  });
  sandboxServer.on("error", (err) => {
    console.warn(`Sandbox server warning on :${SANDBOX_PORT}:`, err.message);
  });
}
