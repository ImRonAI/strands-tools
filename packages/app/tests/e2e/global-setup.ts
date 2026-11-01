import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Playwright global setup for the host smoke test.
 *
 * The python fixture binds an ephemeral port and announces it on stdout as
 * `OUBLIAI_FIXTURE_URL=<url>`, so it cannot be expressed as a static
 * `webServer` entry. This setup spawns it, parses that line, then starts the
 * built two-origin server with the connection environment it needs and waits
 * for both origins to answer. `global-teardown.ts` stops both children.
 */

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const REPO_ROOT = join(PACKAGE_ROOT, "..", "..");
const FIXTURE_SCRIPT = join(
  PACKAGE_ROOT,
  "tests",
  "fixtures",
  "static_token_server.py",
);
const PYTHON = join(REPO_ROOT, ".venv", "bin", "python");
const SERVE_ENTRY = join(PACKAGE_ROOT, "dist", "serve.js");
const CORS_PROXY_SCRIPT = join(PACKAGE_ROOT, "tests", "e2e", "cors-proxy.mjs");
const FIXTURE_TOKEN = "e2e-token";
const HOST_HEALTH_URL = "http://localhost:8080/healthz";
const SANDBOX_URL = "http://localhost:8081/sandbox.html";
const STATE_FILE = join(PACKAGE_ROOT, "test-results", "e2e-processes.json");
const STARTUP_TIMEOUT_MS = 60_000;

function waitForLine(
  child: ChildProcessWithoutNullStreams,
  label: string,
  predicate: (line: string) => boolean,
  timeoutMs: number,
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    let buffered = "";
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error(`${label} did not announce readiness in ${timeoutMs}ms`));
    }, timeoutMs);

    const onStdout = (chunk: Buffer) => {
      buffered += chunk.toString("utf8");
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      for (const line of lines) {
        process.stdout.write(`[${label}] ${line}\n`);
        if (predicate(line)) {
          cleanup();
          resolve(line);
          return;
        }
      }
    };
    const onStderr = (chunk: Buffer) => {
      process.stderr.write(`[${label}] ${chunk.toString("utf8")}`);
    };
    const onExit = (code: number | null) => {
      cleanup();
      reject(new Error(`${label} exited early with code ${String(code)}`));
    };

    function cleanup(): void {
      clearTimeout(timer);
      child.stdout.off("data", onStdout);
      child.off("exit", onExit);
    }

    child.stdout.on("data", onStdout);
    child.stderr.on("data", onStderr);
    child.once("exit", onExit);
  });
}

async function waitForHttpOk(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "no attempt made";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `status ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${url} never returned 200 (${lastError})`);
}

export default async function globalSetup(): Promise<void> {
  const fixture = spawn(PYTHON, [FIXTURE_SCRIPT], {
    cwd: PACKAGE_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  }) as ChildProcessWithoutNullStreams;

  const announcement = await waitForLine(
    fixture,
    "fixture",
    (line) => line.startsWith("OUBLIAI_FIXTURE_URL="),
    STARTUP_TIMEOUT_MS,
  );
  const fixtureUrl = announcement.slice("OUBLIAI_FIXTURE_URL=".length).trim();
  if (!fixtureUrl) {
    fixture.kill("SIGTERM");
    throw new Error("fixture announced an empty OUBLIAI_FIXTURE_URL");
  }

  // FastMCP's `create_streamable_http_app` documents that `allowed_origins` is
  // only the Host/Origin request guard and that CORS must be configured
  // separately for browser JavaScript to read cross-origin responses. The
  // fixture has no CORS middleware, so the harness fronts it with a shim that
  // adds exactly those response headers and streams the body through unchanged.
  const proxy = spawn(process.execPath, [CORS_PROXY_SCRIPT, fixtureUrl], {
    cwd: PACKAGE_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  }) as ChildProcessWithoutNullStreams;
  let proxyUrl: string;
  try {
    const proxyAnnouncement = await waitForLine(
      proxy,
      "cors-proxy",
      (line) => line.startsWith("OUBLIAI_CORS_PROXY_URL="),
      STARTUP_TIMEOUT_MS,
    );
    proxyUrl = proxyAnnouncement
      .slice("OUBLIAI_CORS_PROXY_URL=".length)
      .trim();
  } catch (error) {
    proxy.kill("SIGTERM");
    fixture.kill("SIGTERM");
    throw error;
  }

  const serve = spawn(process.execPath, [SERVE_ENTRY], {
    cwd: PACKAGE_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      OUBLIAI_DEV_CONNECTION: "1",
      OUBLIAI_MCP_URL: proxyUrl,
      OUBLIAI_USER_TOKEN: FIXTURE_TOKEN,
      DENO_NO_PACKAGE_JSON: "1",
    },
  }) as ChildProcessWithoutNullStreams;
  serve.stdout.on("data", (chunk: Buffer) => {
    process.stdout.write(`[serve] ${chunk.toString("utf8")}`);
  });
  serve.stderr.on("data", (chunk: Buffer) => {
    process.stderr.write(`[serve] ${chunk.toString("utf8")}`);
  });

  try {
    await waitForHttpOk(HOST_HEALTH_URL, STARTUP_TIMEOUT_MS);
    await waitForHttpOk(SANDBOX_URL, STARTUP_TIMEOUT_MS);
  } catch (error) {
    serve.kill("SIGTERM");
    proxy.kill("SIGTERM");
    fixture.kill("SIGTERM");
    throw error;
  }

  mkdirSync(dirname(STATE_FILE), { recursive: true });
  writeFileSync(
    STATE_FILE,
    JSON.stringify({
      fixturePid: fixture.pid,
      proxyPid: proxy.pid,
      servePid: serve.pid,
    }),
    "utf8",
  );
  fixture.unref();
  proxy.unref();
  serve.unref();
  process.stdout.write(
    `[setup] fixture ready, host :8080 and sandbox :8081 responding\n`,
  );
}
