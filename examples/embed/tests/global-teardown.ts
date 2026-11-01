import { readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Playwright global teardown: stop every process `global-setup.ts` started.
 *
 * Mirrors `packages/app/tests/e2e/global-teardown.ts`: SIGTERM, wait for the
 * pid to disappear, SIGKILL and fail loudly if it ignored SIGTERM, so a run
 * can never leak a listener on :8080/:8081/:8090 or an orphan fixture.
 */

const EXAMPLE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const STATE_FILE = join(EXAMPLE_ROOT, "test-results", "e2e-processes.json");
const SHUTDOWN_TIMEOUT_MS = 15_000;

interface ProcessState {
  fixturePid?: number;
  proxyPid?: number;
  appServePid?: number;
  embedServePid?: number;
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function stop(label: string, pid: number | undefined): Promise<string> {
  if (pid === undefined) return `${label}: no pid recorded`;
  if (!isAlive(pid)) return `${label}: pid ${pid} already exited`;
  try {
    process.kill(pid, "SIGTERM");
  } catch (error) {
    return `${label}: SIGTERM failed (${
      error instanceof Error ? error.message : String(error)
    })`;
  }
  const deadline = Date.now() + SHUTDOWN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!isAlive(pid)) return `${label}: pid ${pid} exited after SIGTERM`;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Raced with its own exit.
  }
  throw new Error(`${label}: pid ${pid} ignored SIGTERM; sent SIGKILL`);
}

export default async function globalTeardown(): Promise<void> {
  let state: ProcessState;
  try {
    state = JSON.parse(readFileSync(STATE_FILE, "utf8")) as ProcessState;
  } catch {
    process.stdout.write("[teardown] no process state recorded; nothing to stop\n");
    return;
  }

  const results = [
    await stop("embed-serve", state.embedServePid),
    await stop("app-serve", state.appServePid),
    await stop("cors-proxy", state.proxyPid),
    await stop("fixture", state.fixturePid),
  ];
  for (const line of results) process.stdout.write(`[teardown] ${line}\n`);
  rmSync(STATE_FILE, { force: true });
}
