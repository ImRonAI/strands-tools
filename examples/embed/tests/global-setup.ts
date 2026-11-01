import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Playwright global setup for the embed example.
 *
 * Same shape as `packages/app/tests/e2e/global-setup.ts`: the python fixture
 * (the real Oubliai server over a mocked Telnyx transport) binds an ephemeral
 * port and announces it on stdout, so nothing here can be a static
 * `webServer` entry. This setup spawns, in order:
 *
 *   1. the fixture                      -> OUBLIAI_FIXTURE_URL=<url>
 *   2. the CORS shim in front of it     -> OUBLIAI_CORS_PROXY_URL=<url>
 *   3. `packages/app/dist/serve.js`     -> sandbox origin http://localhost:8081
 *      (its host origin :8080 is started too but the embed never uses it; no
 *      connection environment is given to it on purpose)
 *   4. `examples/embed/serve.mjs`       -> embed origin http://localhost:8090,
 *      with the fixture connection exposed through its dev-only
 *      `/api/connection` so the page can prefill the form.
 *
 * The proxy URL is exported to the tests as `OUBLIAI_EMBED_MCP_URL`.
 * `global-teardown.ts` stops every child from the recorded pid file.
 */

type PipedChild = ChildProcessByStdio<null, Readable, Readable>;

const EXAMPLE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = join(EXAMPLE_ROOT, "..", "..");
const APP_ROOT = join(REPO_ROOT, "packages", "app");
const PYTHON = join(REPO_ROOT, ".venv", "bin", "python");
const FIXTURE_SCRIPT = join(APP_ROOT, "tests", "fixtures", "static_token_server.py");
const CORS_PROXY_SCRIPT = join(APP_ROOT, "tests", "e2e", "cors-proxy.mjs");
const APP_SERVE_ENTRY = join(APP_ROOT, "dist", "serve.js");
const EMBED_SERVE_ENTRY = join(EXAMPLE_ROOT, "serve.mjs");
const EMBED_BUNDLE = join(EXAMPLE_ROOT, "dist", "index.html");
const FIXTURE_TOKEN = "e2e-token";
const EMBED_PORT = "8090";
const SANDBOX_URL = "http://localhost:8081/sandbox.html";
const EMBED_HEALTH_URL = `http://localhost:${EMBED_PORT}/healthz`;
const STATE_FILE = join(EXAMPLE_ROOT, "test-results", "e2e-processes.json");
const STARTUP_TIMEOUT_MS = 60_000;

function waitForLine(
  child: PipedChild,
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
      if (response.ok) return;
      lastError = `status ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${url} never returned 200 (${lastError})`);
}

function pipeOutput(child: PipedChild, label: string): void {
  child.stdout.on("data", (chunk: Buffer) => {
    process.stdout.write(`[${label}] ${chunk.toString("utf8")}`);
  });
  child.stderr.on("data", (chunk: Buffer) => {
    process.stderr.write(`[${label}] ${chunk.toString("utf8")}`);
  });
}

export default async function globalSetup(): Promise<void> {
  if (!existsSync(APP_SERVE_ENTRY)) {
    throw new Error(
      `${APP_SERVE_ENTRY} is missing; run \`pnpm build\` in packages/app first`,
    );
  }
  if (!existsSync(EMBED_BUNDLE)) {
    throw new Error(
      `${EMBED_BUNDLE} is missing; run \`pnpm build\` in examples/embed first`,
    );
  }

  const children: PipedChild[] = [];
  const killAll = () => {
    for (const child of children) child.kill("SIGTERM");
  };

  try {
    const fixture = spawn(PYTHON, [FIXTURE_SCRIPT], {
      cwd: APP_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    children.push(fixture);
    const fixtureLine = await waitForLine(
      fixture,
      "fixture",
      (line) => line.startsWith("OUBLIAI_FIXTURE_URL="),
      STARTUP_TIMEOUT_MS,
    );
    const fixtureUrl = fixtureLine.slice("OUBLIAI_FIXTURE_URL=".length).trim();
    if (!fixtureUrl) throw new Error("fixture announced an empty OUBLIAI_FIXTURE_URL");

    const proxy = spawn(process.execPath, [CORS_PROXY_SCRIPT, fixtureUrl], {
      cwd: APP_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
    });
    children.push(proxy);
    const proxyLine = await waitForLine(
      proxy,
      "cors-proxy",
      (line) => line.startsWith("OUBLIAI_CORS_PROXY_URL="),
      STARTUP_TIMEOUT_MS,
    );
    const proxyUrl = proxyLine.slice("OUBLIAI_CORS_PROXY_URL=".length).trim();
    if (!proxyUrl) throw new Error("cors-proxy announced an empty OUBLIAI_CORS_PROXY_URL");

    // The packages/app two-origin server supplies the sandbox origin. It gets
    // no connection environment: the embed page brings the user's own.
    const appServe = spawn(process.execPath, [APP_SERVE_ENTRY], {
      cwd: APP_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, DENO_NO_PACKAGE_JSON: "1" },
    });
    children.push(appServe);
    pipeOutput(appServe, "app-serve");

    const embedServe = spawn(process.execPath, [EMBED_SERVE_ENTRY], {
      cwd: EXAMPLE_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        EMBED_PORT,
        OUBLIAI_DEV_CONNECTION: "1",
        OUBLIAI_MCP_URL: proxyUrl,
        OUBLIAI_TOKEN: FIXTURE_TOKEN,
      },
    });
    children.push(embedServe);
    pipeOutput(embedServe, "embed-serve");

    await waitForHttpOk(SANDBOX_URL, STARTUP_TIMEOUT_MS);
    await waitForHttpOk(EMBED_HEALTH_URL, STARTUP_TIMEOUT_MS);

    mkdirSync(dirname(STATE_FILE), { recursive: true });
    writeFileSync(
      STATE_FILE,
      JSON.stringify({
        fixturePid: fixture.pid,
        proxyPid: proxy.pid,
        appServePid: appServe.pid,
        embedServePid: embedServe.pid,
      }),
      "utf8",
    );
    for (const child of children) child.unref();
    process.env.OUBLIAI_EMBED_MCP_URL = proxyUrl;
    process.stdout.write(
      `[setup] fixture ready, sandbox :8081 and embed :${EMBED_PORT} responding\n`,
    );
  } catch (error) {
    killAll();
    throw error;
  }
}
