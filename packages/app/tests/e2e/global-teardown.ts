import { readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Playwright global teardown: stop the processes `global-setup.ts` started.
 *
 * Each child gets SIGTERM, then we wait until the pid stops responding to
 * signal 0 so the run cannot leak a listener on :8080/:8081 or an orphan
 * fixture process. A still-alive child after the grace period gets SIGKILL and
 * the teardown fails loudly rather than leaving it behind.
 */

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const STATE_FILE = join(PACKAGE_ROOT, "test-results", "e2e-processes.json");
const SHUTDOWN_TIMEOUT_MS = 15_000;

interface ProcessState {
  fixturePid?: number;
  proxyPid?: number;
  servePid?: number;
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
  if (pid === undefined) {
    return `${label}: no pid recorded`;
  }
  if (!isAlive(pid)) {
    return `${label}: pid ${pid} already exited`;
  }
  try {
    process.kill(pid, "SIGTERM");
  } catch (error) {
    return `${label}: SIGTERM failed (${
      error instanceof Error ? error.message : String(error)
    })`;
  }
  const deadline = Date.now() + SHUTDOWN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!isAlive(pid)) {
      return `${label}: pid ${pid} exited after SIGTERM`;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    // Raced with its own exit between the last check and the signal.
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
    await stop("serve", state.servePid),
    await stop("cors-proxy", state.proxyPid),
    await stop("fixture", state.fixturePid),
  ];
  for (const line of results) {
    process.stdout.write(`[teardown] ${line}\n`);
  }
  rmSync(STATE_FILE, { force: true });
}
