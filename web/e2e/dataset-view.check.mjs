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


// --- Phase 4: visuals, disclosure, accessibility -----------------------------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });

  for (const scenario of SCENARIOS) {
    await page.goto(`${BASE}/?view=dataset&scenario=${scenario}`, { waitUntil: "networkidle" });
    await page.waitForSelector("svg[role=img]", { timeout: 15000 });

    // Overlay: the payload's disrupted lane count must match what is drawn amber.
    const payload = await page.evaluate(async (name) => {
      const r = await fetch(`/api/dataset/overview?scenario=${name}`);
      const j = await r.json();
      return j.data.dataset_overview;
    }, scenario);
    const drawnDisrupted = await page.locator('svg[role="img"] path[stroke="#a15c07"]').count();
    const nodeRects = await page.locator('svg[role="img"] rect').count();
    // The overlay is the point of the map: every disrupted lane in the payload must
    // be drawn, which also proves its endpoints survived the per-tier row cap.
    const overlayOk = drawnDisrupted === payload.lanes.disrupted_lane_count;
    const nodesOk = nodeRects > 0 && nodeRects <= payload.network.node_list.length + 4;

    // Level 3: expanders are real buttons and toggle.
    const expanders = page.locator('button[aria-expanded]');
    const expanderCount = await expanders.count();
    let toggleOk = false;
    if (expanderCount) {
      const first = expanders.first();
      const before = await first.getAttribute("aria-expanded");
      await first.focus();
      await page.keyboard.press("Enter");           // keyboard-only, no mouse
      await page.waitForTimeout(200);
      const after = await first.getAttribute("aria-expanded");
      toggleOk = before !== after;
    }

    const ok = overlayOk && nodesOk && expanderCount > 0 && toggleOk && errs.length === 0;
    if (!ok) failures++;
    console.log(
      `${ok ? "PASS" : "FAIL"} visuals ${scenario.padEnd(26)} ` +
      `mapNodes=${nodeRects}/${payload.network.node_list.length} ` +
      `disruptedDrawn=${drawnDisrupted}/${payload.lanes.disrupted_lane_count} ` +
      `expanders=${expanderCount} keyboardToggle=${toggleOk} errors=${errs.length}`
    );
    if (errs.length) console.log("   errors:", errs.slice(0, 3));

    await page.screenshot({ path: `${SHOT_DIR}/full-${scenario}.png`, fullPage: true });
    errs.length = 0;
  }

  // CSV download path works through the proxy.
  const csv = await page.evaluate(async () => {
    const r = await fetch("/api/dataset/table?scenario=baseline&table=lanes");
    return { status: r.status, type: r.headers.get("content-type"), head: (await r.text()).slice(0, 8) };
  });
  const csvOk = csv.status === 200 && (csv.type || "").includes("text/csv") && csv.head.startsWith("lane_id");
  if (!csvOk) failures++;
  console.log(`${csvOk ? "PASS" : "FAIL"} csv download status=${csv.status} type=${csv.type}`);

  await context.close();
}


// --- Phase 5: replay parity (recorded demo must need no backend at all) -------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    const t = m.text();
    // ERR_FAILED is the abort below, not a defect.
    if (m.type() === "error" && !t.includes("ERR_FAILED")) errs.push(t);
  });
  // Simulate a dead backend — the exact situation the recorded demo exists for.
  await page.route("**/api/**", (route) => route.abort());

  await page.goto(`${BASE}/?view=dataset&replay=true`, { waitUntil: "networkidle" });
  await page.waitForSelector("svg[role=img]", { timeout: 15000 }).catch(() => {});
  const summary = await page.locator("section p.text-lg").first().innerText().catch(() => "");
  const badge = await page.locator("text=not customer data").count();
  const chip = await page.locator("text=Recorded snapshot").count();
  const locked = await page.locator("select").first().isDisabled().catch(() => false);
  const disrupted = await page.locator('svg[role="img"] path[stroke="#a15c07"]').count();
  const okDataset =
    summary.includes("manufacturing network") && badge > 0 && chip > 0 && locked &&
    disrupted === 2 && errs.length === 0;
  if (!okDataset) failures++;
  console.log(
    `${okDataset ? "PASS" : "FAIL"} replay dataset (API blocked) badge=${badge} ` +
    `snapshotChip=${chip} selectorLocked=${locked} disrupted=${disrupted} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));

  errs.length = 0;
  await page.goto(`${BASE}/?replay=true`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Why this plan", { timeout: 20000 }).catch(() => {});
  const banner = await page.locator("text=Scenario list failed").count();
  const winner = await page.locator("text=Winner:").first().innerText().catch(() => "");
  await page.click("text=View the dataset").catch(() => {});
  await page.waitForTimeout(1200);
  const stayed = (await page.locator("text=Recorded snapshot").count()) > 0;
  const okResults =
    winner.toLowerCase().includes("classical") && stayed && banner === 0 && errs.length === 0;
  if (!okResults) failures++;
  console.log(
    `${okResults ? "PASS" : "FAIL"} replay results->dataset winner="${winner}" ` +
    `stayedInReplay=${stayed} errorBanner=${banner} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));

  await context.close();
}

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
