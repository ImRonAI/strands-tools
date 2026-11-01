import { expect, test, type Browser, type Page } from "@playwright/test";

import { WORKSPACE_DOMAINS, type WorkspaceDomain } from "../../src/workspace/domains.js";

/**
 * Workspace coverage for the official AppBridge two-origin host (plan A2).
 *
 * One browser page is shared by every test in the describe so that selecting
 * the next domain exercises the host's documented teardown of the previous
 * view (`teardownResource` → `close` → iframe removal) rather than a fresh
 * page load. For each of the 14 domains the test proves:
 *   - the sandbox proxy iframe mounts on the sandbox origin with the renderer
 *     resource's CSP in its query string,
 *   - the AppBridge handshake completes and the host reports `rendered`,
 *   - the inner view shows a value that only the fixture's mocked Telnyx
 *     response for that domain can supply,
 *   - the previously mounted iframe is gone and exactly one `#app-frame`
 *     exists,
 *   - the page produced no console errors and the host recorded no error.
 *
 * The final test flips the host theme and proves the view received the
 * `ui/notifications/host-context-changed` notification through the Prefab
 * renderer's own `data-theme` application.
 */

const HOST_ORIGIN = "http://localhost:8080";
const SANDBOX_HTML = "http://localhost:8081/sandbox.html";
const SANDBOX_SRC_PATTERN = new RegExp(
  `^${SANDBOX_HTML.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\?`,
);

interface HostDebugState {
  state: "idle" | "connected" | "rendered" | "error";
  lastError?: string;
  bridgeInitialized: boolean;
}

declare global {
  interface Window {
    __oubliaiHost?: HostDebugState;
  }
}

/**
 * One value per domain that the inner view renders from the fixture's mocked
 * Telnyx list response (`tests/fixtures/telnyx_mock_responses.json`). Each
 * value sits in a column the server-side workspace declares for that domain
 * (`packages/server/src/oubliai_server/apps/<domain>.py`).
 */
const FIXTURE_VALUE: Record<WorkspaceDomain, string> = {
  numbers: "+15555550100",
  messaging: "Fixture Messaging Profile",
  fax: "+15555550150",
  verify: "Fixture Verify Profile",
  video: "fixture-room-001",
  meetings: "Fixture Meeting Bot",
  email: "Fixture welcome email",
  voice: "Fixture Call Control App",
  ai: "Fixture Assistant",
  rag: "fixture-embedding-task",
  speech: "Fixture Voice Design",
  storage: "fixture-cache",
  training: "fixture-training.jsonl",
  platform: "Fixture Business LLC",
};

test.describe("workspaces", () => {
  test.describe.configure({ mode: "serial" });

  let page: Page;
  const consoleErrors: string[] = [];

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    page = await browser.newPage();
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push(message.text());
      }
    });
    await page.goto(`${HOST_ORIGIN}/`, { waitUntil: "domcontentloaded" });
    await expect
      .poll(
        async () =>
          await page.evaluate(() => window.__oubliaiHost?.state ?? "missing"),
        { timeout: 30_000, message: "host never reached the connected state" },
      )
      .toBe("connected");
  });

  test.afterAll(async () => {
    await page?.close();
  });

  async function hostDebug(): Promise<HostDebugState | null> {
    return page.evaluate(() => window.__oubliaiHost ?? null);
  }

  async function selectAndAwaitRender(domain: WorkspaceDomain): Promise<void> {
    const previousFrame = await page.$("iframe#app-frame");

    await page.locator("#workspace-select").selectOption(domain);

    const sandboxFrame = page.locator("iframe#app-frame");
    await expect(sandboxFrame).toHaveCount(1, { timeout: 30_000 });
    await expect(sandboxFrame).toHaveAttribute("src", SANDBOX_SRC_PATTERN, {
      timeout: 30_000,
    });
    const mountedSrc = await sandboxFrame.getAttribute("src");
    expect(mountedSrc, "sandbox src must carry the resource CSP").toContain(
      "csp=",
    );

    // Documented teardown: the previous iframe is removed from the document
    // and only the new one remains.
    if (previousFrame) {
      await expect
        .poll(async () => await previousFrame.evaluate((el) => el.isConnected), {
          timeout: 30_000,
          message: "previous #app-frame was not removed by the host teardown",
        })
        .toBe(false);
      await previousFrame.dispose();
    }

    const viewFrame = page.frameLocator("iframe#app-frame").frameLocator("iframe");
    await expect(viewFrame.locator("body")).toContainText(FIXTURE_VALUE[domain], {
      timeout: 30_000,
    });

    await expect
      .poll(async () => (await hostDebug())?.bridgeInitialized ?? false, {
        timeout: 30_000,
        message: "AppBridge never reported initialization",
      })
      .toBe(true);
    const debug = await hostDebug();
    expect(debug?.state).toBe("rendered");
    expect(debug?.lastError ?? null).toBeNull();
    expect(await page.locator("iframe#app-frame").count()).toBe(1);
    expect(consoleErrors).toEqual([]);
  }

  for (const domain of WORKSPACE_DOMAINS) {
    test(`renders the ${domain} workspace from the fixture response`, async () => {
      await selectAndAwaitRender(domain);
    });
  }

  test("theme toggle reaches the rendered view as a host-context change", async () => {
    // The loop ended on `platform`; selecting `numbers` again goes through the
    // host teardown one more time and gives the screenshot a known workspace.
    await selectAndAwaitRender("numbers");

    const hostTheme = async () =>
      page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    const viewFrame = page.frameLocator("iframe#app-frame").frameLocator("iframe");
    const viewHtml = viewFrame.locator("html");

    const initialTheme = await hostTheme();
    expect(initialTheme === "light" || initialTheme === "dark").toBe(true);
    const flipped = initialTheme === "dark" ? "light" : "dark";
    // The Prefab renderer applies the initial `hostContext.theme` from the
    // `ui/initialize` result to `<html data-theme>`.
    await expect(viewHtml).toHaveAttribute("data-theme", initialTheme!, {
      timeout: 30_000,
    });
    await page.screenshot({
      path: `test-results/workspace-numbers-${initialTheme}.png`,
      fullPage: true,
    });

    await page.locator("#theme-toggle").click();

    await expect.poll(hostTheme).toBe(flipped);
    await expect(page.locator("#theme-toggle")).toHaveText(`Theme: ${flipped}`);
    // `ui/notifications/host-context-changed` delivered the new theme: the
    // renderer's own handler sets `data-theme` on its document element.
    await expect(viewHtml).toHaveAttribute("data-theme", flipped, {
      timeout: 30_000,
    });
    await expect(viewHtml).toHaveCSS("color-scheme", flipped);
    await page.screenshot({
      path: `test-results/workspace-numbers-${flipped}.png`,
      fullPage: true,
    });

    // Toggle back so the shared page leaves the run in its initial theme.
    await page.locator("#theme-toggle").click();
    await expect.poll(hostTheme).toBe(initialTheme);
    await expect(viewHtml).toHaveAttribute("data-theme", initialTheme!, {
      timeout: 30_000,
    });

    const debug = await hostDebug();
    expect(debug?.lastError ?? null).toBeNull();
    expect(consoleErrors).toEqual([]);
  });
});
