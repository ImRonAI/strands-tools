import { spawn, type ChildProcess } from "node:child_process";
import process from "node:process";
import type { TestProject } from "vitest/node";

const PYTHON_EXECUTABLE = "/Users/tims-stuff/Desktop/strands-tools/.venv/bin/python";
const FIXTURE_SCRIPT = "tests/fixtures/static_token_server.py";
const FIXTURE_TOKEN = "e2e-token";
const URL_PREFIX = "OUBLIAI_FIXTURE_URL=";
const STARTUP_TIMEOUT_MS = 120_000;
const SHUTDOWN_TIMEOUT_MS = 10_000;

declare module "vitest" {
  interface ProvidedContext {
    mcpUrl: string;
    e2eToken: string;
  }
}

function waitForExit(child: ChildProcess, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolve();
    }, timeoutMs);
    child.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

async function spawnFixture(): Promise<{ child: ChildProcess; url: string }> {
  const child = spawn(PYTHON_EXECUTABLE, [FIXTURE_SCRIPT], {
    env: { ...process.env, DENO_NO_PACKAGE_JSON: "1" },
    stdio: ["ignore", "pipe", "inherit"],
  });

  let buffer = "";
  const url = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(
        new Error(
          `${FIXTURE_SCRIPT} did not print ${URL_PREFIX.trim()} within ${STARTUP_TIMEOUT_MS}ms; stdout so far: ${JSON.stringify(buffer)}`,
        ),
      );
    }, STARTUP_TIMEOUT_MS);

    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(
        new Error(
          `${FIXTURE_SCRIPT} exited with code ${code ?? "null"} before printing ${URL_PREFIX.trim()}; stdout: ${JSON.stringify(buffer)}`,
        ),
      );
    });
    child.stdout?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => {
      buffer += chunk;
      const line = buffer
        .split("\n")
        .find((candidate) => candidate.startsWith(URL_PREFIX));
      if (line) {
        clearTimeout(timer);
        resolve(line.slice(URL_PREFIX.length).trim());
      }
    });
  });

  return { child, url };
}

export default async function globalSetup(project: TestProject): Promise<() => Promise<void>> {
  const { child, url } = await spawnFixture();
  // Surface the fixture URL line on the parent stdout so CI logs prove birth.
  console.log(`${URL_PREFIX}${url}`);
  // Prove the fixture answers before any test runs: unauthenticated calls must be 401.
  const probe = await fetch(url, { method: "POST" });
  if (probe.status !== 401) {
    child.kill("SIGTERM");
    await waitForExit(child, SHUTDOWN_TIMEOUT_MS);
    throw new Error(`fixture at ${url} returned ${probe.status}, expected 401`);
  }

  project.provide("mcpUrl", url);
  project.provide("e2eToken", FIXTURE_TOKEN);
  process.env.OUBLIAI_TEST_MCP_URL = url;
  process.env.OUBLIAI_TEST_TOKEN = FIXTURE_TOKEN;

  return async () => {
    child.kill("SIGTERM");
    await waitForExit(child, SHUTDOWN_TIMEOUT_MS);
  };
}


