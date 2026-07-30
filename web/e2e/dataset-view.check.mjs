/**
 * Headless browser verification for the dataset view (Iteration 4).
 *
 * Checks what a screenshot alone cannot assert and a unit test cannot reach:
 * that Level 1 genuinely fits above the fold at 1080p and on a laptop, that the
 * provenance badge is present on every scenario, that the console is clean, that
 * `?view=dataset` round-trips through the back button, and that an unknown
 * scenario shows an honest error instead of silently rendering other data.
 *
 * Run with `make web-check` (see Makefile) — needs the stack up.
 */
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://web:80";
const SCENARIOS = ["baseline", "component-shortage-shock", "demand-surge", "stress-large"];
const VIEWPORTS = { desktop: { width: 1920, height: 1080 }, laptop: { width: 1440, height: 900 } };
const SHOT_DIR = process.env.SHOT_DIR ?? "/shots";

const browser = await chromium.launch();
let failures = 0;

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  for (const scenario of SCENARIOS) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
    page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

    await page.goto(`${BASE}/?view=dataset&scenario=${scenario}`, { waitUntil: "networkidle" });
    await page.waitForSelector("text=How the network is laid out", { timeout: 15000 }).catch(() => {});

    const heroText = await page.locator("h1").first().innerText().catch(() => "");
    const summary = await page.locator("section p.text-lg, section p.sm\\:text-xl").first().innerText().catch(() => "");
    const badgeCount = await page.locator("text=not customer data").count();
    const tiles = await page.locator("article").count();

    // Where does Level 1 end? Bottom of the network strip must be within the fold.
    const foldBottom = await page.evaluate(() => {
      const headings = Array.from(document.querySelectorAll("h2"));
      const strip = headings.find((h) => h.textContent?.includes("How the network is laid out"));
      if (!strip) return null;
      const section = strip.closest("section");
      return section ? Math.round(section.getBoundingClientRect().bottom + window.scrollY) : null;
    });

    const shot = `${SHOT_DIR}/${vpName}-${scenario}.png`;
    await page.screenshot({ path: shot });

    const level1Fits = foldBottom !== null && foldBottom <= viewport.height;
    const ok = badgeCount > 0 && tiles >= 6 && consoleErrors.length === 0 && level1Fits;
    if (!ok) failures++;
    console.log(
      `${ok ? "PASS" : "FAIL"} ${vpName.padEnd(7)} ${scenario.padEnd(26)} ` +
      `badge=${badgeCount} tiles=${tiles} level1Bottom=${foldBottom}px/${viewport.height}px ` +
      `fits=${level1Fits} consoleErrors=${consoleErrors.length}`
    );
    if (consoleErrors.length) console.log("   errors:", consoleErrors.slice(0, 3));
    if (vpName === "desktop" && scenario === "baseline") {
      console.log("   h1:", JSON.stringify(heroText));
      console.log("   summary:", JSON.stringify(summary.slice(0, 120)));
    }
    await context.close();
  }
}

// Error/empty states and navigation.
const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
const page = await context.newPage();
const navErrors = [];
page.on("pageerror", (e) => navErrors.push(e.message));

await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
await page.click("text=View the dataset");
await page.waitForSelector("text=Know your data", { timeout: 10000 });
const urlAfter = page.url();
await page.click("text=Back to results");
await page.waitForSelector("text=Scenario Comparison", { timeout: 10000 });
const urlBack = page.url();
console.log(`NAV  button->dataset url=${urlAfter}`);
console.log(`NAV  back->results  url=${urlBack}`);
console.log(`NAV  pageerrors=${navErrors.length}`);
if (!urlAfter.includes("view=dataset")) failures++;
if (urlBack.includes("view=dataset")) failures++;

await page.goto(`${BASE}/?view=dataset&scenario=not-a-real-scenario`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
const errorShown = await page.locator("text=Could not load the dataset").count();
console.log(`ERR  unknown scenario shows error state: ${errorShown > 0}`);
await page.screenshot({ path: `${SHOT_DIR}/error-state.png` });
if (errorShown === 0) failures++;

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
