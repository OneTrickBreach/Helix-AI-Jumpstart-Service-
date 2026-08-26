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

// --- Iteration 5 Phase 4: the chat panel ("Ask the plan", BETA) --------------
//
// What these assert that a unit test cannot: that the panel opens *alongside* both
// views rather than replacing either, that provenance chips reach the screen, that
// nothing runs before the confirm card is accepted, that a what-if card carries its
// WHAT-IF/BETA labelling inside its own bounding box (so a cropped screenshot still
// carries them), that a perturbation which cannot reach the optimizer says so
// instead of reading as resilience, and that the user's own text is never rendered
// as markup.
const CHAT_PANEL = 'aside[aria-label="Ask the plan (beta)"]';
// Direct children of the live region only. The provenance chips are themselves
// <li> elements, so a plain `li` selector silently returns a chip as "the last
// message" — which is exactly how the first run of these checks failed.
const MESSAGES = `${CHAT_PANEL} ul[aria-live] > li`;
const CONFIRM_CARD = 'section[aria-label="What-if confirmation"]';
const RESULT_CARD = 'section[data-what-if="true"]';

/**
 * Screenshot one card **in full**.
 *
 * Playwright clips an element screenshot to what is on screen, and these cards are
 * taller than the 420px-wide panel's visible area — so the plain element shot lost
 * the card's own header band (the `WHAT-IF RESULT · SYNTHETIC PERTURBATION` + `BETA`
 * row) and, on the no-op card, the "Do not read this as resilience" line. Committed
 * evidence that is missing the labels the card exists to carry is worse than no
 * screenshot, so the viewport is grown for the shot and restored afterwards.
 */
async function shootCard(page, locator, path) {
  const viewport = page.viewportSize();
  const box = await locator.boundingBox();
  // Room for the card plus the panel's sticky header and composer, so that centring
  // the card leaves its own header band clear of the overlay.
  const needed = Math.ceil((box?.height ?? 0) + 420);
  const grew = needed > viewport.height;
  if (grew) await page.setViewportSize({ width: viewport.width, height: needed });
  await locator.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await page.waitForTimeout(200);
  await locator.screenshot({ path });
  if (grew) {
    await page.setViewportSize(viewport);
    await page.waitForTimeout(150);
  }
}

async function askStarter(page, question, timeout = 90000) {
  const before = await page.locator(MESSAGES).count();
  await page.click(`${CHAT_PANEL} button:text-is("${question}")`);
  await page.waitForFunction(
    ([selector, count]) => document.querySelectorAll(selector).length > count + 1,
    [MESSAGES, before],
    { timeout },
  );
}

{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });

  // 1. Opens from the results view, beside it — the results are still on screen.
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.click("text=Ask the plan");
  await page.waitForSelector(CHAT_PANEL, { timeout: 10000 });
  const betaInHeader = await page.locator(`${CHAT_PANEL} header >> text=Beta`).count();
  const resultsStillThere = await page.locator("text=Scenario Comparison").count();
  const chatUrl = page.url();
  const openOk = betaInHeader > 0 && resultsStillThere > 0 && chatUrl.includes("chat=true") && errs.length === 0;
  if (!openOk) failures++;
  console.log(
    `${openOk ? "PASS" : "FAIL"} chat opens beside results  beta=${betaInHeader} ` +
    `resultsVisible=${resultsStillThere} url=${chatUrl.replace(BASE, "")} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));
  errs.length = 0;

  // 2. A grounded answer arrives with its provenance chips.
  await askStarter(page, "How many distribution centers are there?");
  const answerText = await page.locator(MESSAGES).last().innerText();
  const chipLabels = await page.locator(`${CHAT_PANEL} ul[aria-label="Where this answer came from"] span`).allInnerTexts();
  const groundedOk =
    chipLabels.some((label) => /from dataset/i.test(label)) &&
    chipLabels.some((label) => /(explained by llm|deterministic template)/i.test(label)) &&
    /numbers from:/i.test(answerText) &&
    errs.length === 0;
  if (!groundedOk) failures++;
  console.log(
    `${groundedOk ? "PASS" : "FAIL"} grounded answer chips     ${JSON.stringify(chipLabels)} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));
  errs.length = 0;

  // 3. Ryan's own question: the premise is corrected and stress-large is offered.
  await askStarter(page, "What if warehouse 4 is completely depleted?");
  const premise = await page.locator(MESSAGES).last().innerText();
  const premiseOk =
    /no warehouse 4/i.test(premise) && /DC-001/.test(premise) && /stress-large/.test(premise) &&
    (await page.locator(RESULT_CARD).count()) === 0;
  if (!premiseOk) failures++;
  console.log(`${premiseOk ? "PASS" : "FAIL"} warehouse-4 premise      names DC-001/DC-002 and offers stress-large`);

  // 4. Confirm-before-run: the card appears and NOTHING has run yet.
  await askStarter(page, "What if DC-001 goes down?");
  await page.waitForSelector(CONFIRM_CARD, { timeout: 20000 });
  const confirmText = await page.locator(CONFIRM_CARD).last().innerText();
  const resultsBeforeConfirm = await page.locator(RESULT_CARD).count();
  const confirmOk =
    resultsBeforeConfirm === 0 &&
    /DC-001 unable to ship or receive/i.test(confirmText) &&
    /Beta/i.test(confirmText) &&
    /seed 12345/i.test(confirmText) &&
    /Run it on the optimizer/i.test(confirmText);
  if (!confirmOk) failures++;
  console.log(
    `${confirmOk ? "PASS" : "FAIL"} confirm before run       resultCardsBefore=${resultsBeforeConfirm} ` +
    `reading+seed+beta present=${confirmOk}`
  );
  await shootCard(page, page.locator(CONFIRM_CARD).last(), `${SHOT_DIR}/chat-confirm-card.png`);

  // 5. Run it for real and check the card cannot be read as a benchmark result.
  await page.click(`${CONFIRM_CARD} >> text=Run it on the optimizer`);
  await page.waitForSelector(RESULT_CARD, { timeout: 120000 });
  const cardText = await page.locator(RESULT_CARD).last().innerText();
  // $81,789.36 is the recorded classical objective for `baseline`, which is the
  // scenario the results screen opens on and therefore the base side of this run.
  // Asserting it ties the number on screen to the recorded benchmark.
  const cardOk =
    /WHAT-IF/i.test(cardText) &&
    /Beta/i.test(cardText) &&
    /not the recorded benchmark result/i.test(cardText) &&
    /CVaR-75/i.test(cardText) &&
    /\$81,789\.36/.test(cardText) &&
    /seed 12345/i.test(cardText) &&
    /synthetic perturbation of seeded demo data/i.test(cardText) &&
    errs.length === 0;
  if (!cardOk) failures++;
  console.log(
    `${cardOk ? "PASS" : "FAIL"} what-if card labelling   whatIfChip=${/WHAT-IF/i.test(cardText)} ` +
    `beta=${/Beta/i.test(cardText)} disclaimer=${/not the recorded benchmark/i.test(cardText)} ` +
    `cvar=${/CVaR-75/i.test(cardText)} baseObjective=${/\$81,789\.36/.test(cardText)} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));
  errs.length = 0;
  await shootCard(page, page.locator(RESULT_CARD).last(), `${SHOT_DIR}/chat-whatif-card.png`);
  await page.screenshot({ path: `${SHOT_DIR}/chat-results-view.png` });

  // 6. A window that misses the one period the optimizer reads must say so.
  await page.fill(`${CHAT_PANEL} textarea`, "What if DC-001 goes down from period 3 to period 6?");
  const beforeNoop = await page.locator(MESSAGES).count();
  await page.press(`${CHAT_PANEL} textarea`, "Enter");
  await page.waitForFunction(
    ([selector, count]) =>
      document.querySelectorAll("section[aria-label='What-if confirmation']").length > 1 &&
      document.querySelectorAll(selector).length > count + 1,
    [MESSAGES, beforeNoop],
    { timeout: 90000 },
  );
  const noopCard = page.locator(CONFIRM_CARD).last();
  const noopWarned = /would not change the plan/i.test(await noopCard.innerText());
  await noopCard.locator("text=Run it anyway").click();
  await page.waitForFunction(
    (selector) => {
      const cards = document.querySelectorAll(selector);
      return cards.length > 1;
    },
    RESULT_CARD,
    { timeout: 120000 },
  );
  const noopResult = await page.locator(RESULT_CARD).last().innerText();
  const noopOk =
    noopWarned &&
    /Do not read this as resilience/i.test(noopResult) &&
    /No change/i.test(noopResult) &&
    /period 52 only/i.test(noopResult);
  if (!noopOk) failures++;
  console.log(
    `${noopOk ? "PASS" : "FAIL"} no-op is honest          warnedBeforeRun=${noopWarned} ` +
    `resilienceWarning=${/Do not read this as resilience/i.test(noopResult)}`
  );
  await shootCard(page, page.locator(RESULT_CARD).last(), `${SHOT_DIR}/chat-whatif-noop-card.png`);

  // 7. The user's own text is text, never markup.
  await page.fill(`${CHAT_PANEL} textarea`, '<img src=x onerror="window.__injected=1"> what is a lane?');
  const beforeInjection = await page.locator(MESSAGES).count();
  await page.press(`${CHAT_PANEL} textarea`, "Enter");
  await page.waitForFunction(
    ([selector, count]) => document.querySelectorAll(selector).length > count,
    [MESSAGES, beforeInjection],
    { timeout: 90000 },
  );
  const injectedElements = await page.locator(`${CHAT_PANEL} img`).count();
  const injectedGlobal = await page.evaluate(() => window.__injected ?? null);
  const echoed = await page.locator(MESSAGES).nth(beforeInjection).innerText();
  const escapeOk = injectedElements === 0 && injectedGlobal === null && echoed.includes("<img");
  if (!escapeOk) failures++;
  console.log(
    `${escapeOk ? "PASS" : "FAIL"} question rendered as text imgElements=${injectedElements} ` +
    `globalSet=${injectedGlobal} echoedLiterally=${echoed.includes("<img")}`
  );

  // 7b. Switching scenario must not leave answers about the old dataset on screen.
  const messagesBeforeSwitch = await page.locator(MESSAGES).count();
  await page.selectOption("select", "demand-surge");
  await page.waitForFunction(
    ([selector, count]) => document.querySelectorAll(selector).length < count,
    [MESSAGES, messagesBeforeSwitch],
    { timeout: 15000 },
  );
  const afterSwitch = await page.locator(MESSAGES).allInnerTexts();
  const groundedIn = await page.locator(`${CHAT_PANEL} header`).innerText();
  const switchOk =
    afterSwitch.length === 1 &&
    /Scenario changed to demand-surge/i.test(afterSwitch[0]) &&
    /demand-surge/.test(groundedIn) &&
    (await page.locator(RESULT_CARD).count()) === 0;
  if (!switchOk) failures++;
  console.log(
    `${switchOk ? "PASS" : "FAIL"} scenario switch resets   messages=${afterSwitch.length} ` +
    `headerNamesScenario=${/demand-surge/.test(groundedIn)} staleCards=${await page.locator(RESULT_CARD).count()}`
  );

  // 8. Opens beside the dataset view too, without pushing Level 1 off screen at 1080p.
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    await page.setViewportSize(viewport);
    await page.goto(`${BASE}/?view=dataset&scenario=component-shortage-shock&chat=true`, { waitUntil: "networkidle" });
    await page.waitForSelector(CHAT_PANEL, { timeout: 10000 });
    await page.waitForSelector("svg[role=img]", { timeout: 15000 });
    const badge = await page.locator("text=not customer data").count();
    const foldBottom = await page.evaluate(() => {
      const strip = Array.from(document.querySelectorAll("h2")).find((h) =>
        h.textContent?.includes("How the network is laid out"),
      );
      const section = strip?.closest("section");
      return section ? Math.round(section.getBoundingClientRect().bottom + window.scrollY) : null;
    });
    const bothOk = badge > 0 && foldBottom !== null && errs.length === 0;
    if (!bothOk) failures++;
    console.log(
      `${bothOk ? "PASS" : "FAIL"} chat beside dataset ${vpName.padEnd(7)} badge=${badge} ` +
      `errors=${errs.length}`
    );
    // Informational, deliberately NOT a gate: the Iteration 4 "Level 1 above the
    // fold" guarantee is about the shipped default, which is chat closed (asserted
    // above). Opening the panel narrows the page, and on a 1440x900 laptop that
    // pushes the bottom of the network map just below the fold. Measured and
    // recorded rather than glossed over or quietly re-defined.
    console.log(
      `INFO chat beside dataset ${vpName.padEnd(7)} level1BottomWithChatOpen=${foldBottom}px/` +
      `${viewport.height}px stillAboveFold=${foldBottom <= viewport.height}`
    );
    if (errs.length) console.log("   errors:", errs.slice(0, 3));
    errs.length = 0;
    if (vpName === "desktop") await page.screenshot({ path: `${SHOT_DIR}/chat-dataset-view.png` });
  }

  await context.close();
}

// --- Iteration 5 Phase 4: chat replay parity (no backend at all) --------------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    const t = m.text();
    if (m.type() === "error" && !t.includes("ERR_FAILED")) errs.push(t);
  });
  let apiCalls = 0;
  await page.route("**/api/**", (route) => { apiCalls++; return route.abort(); });

  await page.goto(`${BASE}/?replay=true&chat=true`, { waitUntil: "networkidle" });
  await page.waitForSelector(CHAT_PANEL, { timeout: 15000 });
  await page.waitForSelector(`${CHAT_PANEL} >> text=Recorded transcript`, { timeout: 15000 });
  const callsAfterLoad = apiCalls;

  await askStarter(page, "What if warehouse 4 is completely depleted?", 20000);
  const recordedPremise = await page.locator(MESSAGES).last().innerText();

  await askStarter(page, "What if DC-001 goes down?", 20000);
  await page.waitForSelector(CONFIRM_CARD, { timeout: 15000 });
  await page.click(`${CONFIRM_CARD} >> text=Run it on the optimizer`);
  await page.waitForSelector(RESULT_CARD, { timeout: 15000 });
  const recordedCard = await page.locator(RESULT_CARD).last().innerText();
  const composerLocked = await page.locator(`${CHAT_PANEL} textarea`).isDisabled();
  // With the API blocked the scenario list never loads, so the panel must take the
  // scenario from the recording itself rather than claiming "no scenario selected"
  // above answers that are plainly about one.
  const replayHeader = await page.locator(`${CHAT_PANEL} header`).innerText();

  const replayOk =
    /component-shortage-shock/.test(replayHeader) &&
    /stress-large/.test(recordedPremise) &&
    /WHAT-IF/i.test(recordedCard) &&
    /\$95,445\.45/.test(recordedCard) &&
    /CVaR-75/i.test(recordedCard) &&
    composerLocked &&
    apiCalls === callsAfterLoad &&
    errs.length === 0;
  if (!replayOk) failures++;
  console.log(
    `${replayOk ? "PASS" : "FAIL"} replay chat (API blocked) recordedWhatIf=${/WHAT-IF/i.test(recordedCard)} ` +
    `baseObjective=${/\$95,445\.45/.test(recordedCard)} composerLocked=${composerLocked} ` +
    `headerScenario=${/component-shortage-shock/.test(replayHeader)} ` +
    `apiCallsWhileChatting=${apiCalls - callsAfterLoad} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));
  // Let the recorded results finish rendering before the shot: a screenshot of the
  // panel beside a still-animating stepper is weak evidence for "the panel opens
  // beside the results and does not cover them".
  await page.waitForSelector("text=Why this plan", { timeout: 20000 }).catch(() => {});
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${SHOT_DIR}/chat-replay.png` });

  await context.close();
}

// --- Iteration 6a Phase 4: build your own scenario ---------------------------
// The full loop a planner does, in a real browser: open the panel from the fifth
// dropdown entry, move controls, read the change list, save, run, read a result
// that is labelled as custom, then delete it. Plus the two things that are
// correctness rather than feature (plan §0.6): the inert-settings labelling and
// the capacity no-op warning.
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });

  const SLUG = `webcheck-${Date.now().toString(36)}`;
  const PANEL = '[data-testid="custom-panel"]';

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });

  // The fifth dropdown entry, grouped away from the recorded four.
  const optionGroups = await page.locator("[data-testid='scenario-select'] optgroup").allInnerTexts();
  const hasBuildEntry = await page.locator("[data-testid='scenario-select'] option[value='__custom__']").count();
  await page.selectOption("[data-testid='scenario-select']", "__custom__");
  await page.waitForSelector(PANEL, { timeout: 15000 });

  // Pre-filled from baseline, and it says so.
  const panelIntro = await page.locator(PANEL).innerText();

  // Delete has to be findable WITHOUT scrolling, measured the moment the panel
  // opens and before anything else scrolls it. It previously sat at the bottom of
  // the panel's scroll area as a bare icon, and a reviewer could not find it.
  // The bound is two-sided on purpose: a negative y would mean the section had
  // been scrolled off the top, which a `y < height` check alone would let pass.
  const savedBox = await page.locator('[data-testid="custom-saved"]').boundingBox();
  const savedText = await page.locator('[data-testid="custom-saved"]').innerText();
  const deleteVisible =
    Boolean(savedBox) && savedBox.y >= 0 && savedBox.y < VIEWPORTS.desktop.height;
  const deleteNamed = /delete/i.test(savedText);
  if (!(deleteVisible && deleteNamed)) failures++;
  console.log(
    `${deleteVisible && deleteNamed ? "PASS" : "FAIL"} delete is discoverable without scrolling ` +
    `sectionY=${savedBox ? Math.round(savedBox.y) : "none"}/${VIEWPORTS.desktop.height} ` +
    `namesDelete=${deleteNamed}`
  );

  await page.fill('[data-testid="custom-name"]', SLUG);
  const targetName = await page.locator('[data-testid="custom-target-name"]').innerText();

  // A Simple-tier control that reaches the optimizer.
  await page.fill('[data-testid="simple-demand_level"] input', "52");
  await page.waitForSelector('[data-testid="custom-changes"]', { timeout: 15000 });
  const changesText = await page.locator('[data-testid="custom-changes"]').innerText();
  const estimateText = await page.locator('[data-testid="custom-estimate"]').innerText();

  // Advanced: all settings, with the inert ones under their own heading.
  await page.click('[data-testid="custom-advanced-toggle"]');
  await page.waitForSelector('[data-testid="custom-inert-settings"]', { timeout: 15000 });
  const inertHeading = await page.locator('[data-testid="custom-inert-heading"]').innerText();
  const inertBlock = await page.locator('[data-testid="custom-inert-settings"]').innerText();
  // The single most misleading control in the iteration, explicitly labelled.
  const dcThroughputLabelled =
    (await page.locator('[data-testid="reach-capacity.dc_throughput_units_per_period"]').count()) > 0;
  const advancedSettingCount = await page.locator('[data-testid^="setting-"]').count();

  // Iteration 6b: 59 scenario settings + the 8 network counts. And the inert
  // network count has to land in THIS block, not among the live controls.
  const linesPerPlantInert = /lines_per_plant/.test(inertBlock);
  // 🔴 Guardrail 3 on the ADVANCED path too. A planner can reach network.customers
  // here without ever opening the Network group, so the not-comparable caveat has
  // to travel with the control, or Advanced becomes the dishonest route to the
  // same edit.
  const resizesFlaggedInAdvanced =
    (await page.locator('[data-testid="not-comparable-network.customers"]').count()) > 0;
  const shapeNotFlagged =
    (await page.locator('[data-testid="not-comparable-network.distribution_centers"]').count()) === 0;
  const labellingOk =
    /not read by the optimizer/i.test(inertHeading) &&
    dcThroughputLabelled &&
    linesPerPlantInert &&
    resizesFlaggedInAdvanced &&
    shapeNotFlagged &&
    advancedSettingCount === 67;
  if (!labellingOk) failures++;
  console.log(
    `${labellingOk ? "PASS" : "FAIL"} custom advanced labelling settings=${advancedSettingCount} ` +
    `inertHeading="${inertHeading.slice(0, 48)}" dcThroughputFlagged=${dcThroughputLabelled} ` +
    `linesPerPlantInert=${linesPerPlantInert} resizesFlagged=${resizesFlaggedInAdvanced} ` +
    `shapeNotFalselyFlagged=${shapeNotFlagged}`
  );

  // Decision 8's opt-ins have to be visible, or "PPO timesteps" and "Top K" are
  // controls a custom run silently ignores.
  const runOptions = await page.locator('[data-testid="custom-run-options"]').innerText();
  const ppoBox = await page.locator('[data-testid="run-include-ppo"]').count();
  const ratBox = await page.locator('[data-testid="run-include-rationale"]').count();
  const optionsOk = ppoBox === 1 && ratBox === 1 && /off by default/i.test(runOptions);
  if (!optionsOk) failures++;
  console.log(
    `${optionsOk ? "PASS" : "FAIL"} custom run opt-ins are visible and explained ` +
    `ppoBox=${ppoBox} rationaleBox=${ratBox} explains=${/off by default/i.test(runOptions)}`
  );

  // Save and run it for real.
  await page.click('[data-testid="custom-save-run"]');
  await page.waitForSelector('[data-testid="custom-result-banner"]', { timeout: 120000 });
  const banner = await page.locator('[data-testid="custom-result-banner"]').innerText();
  const winner = await page.locator("text=Winner:").first().innerText().catch(() => "");
  const selectValue = await page.locator("[data-testid='scenario-select']").inputValue();

  const runOk =
    /not a recorded benchmark result/i.test(banner) &&
    banner.includes(`custom-${SLUG}`) &&
    /Winner:/.test(winner) &&
    selectValue === `custom-${SLUG}` &&
    errs.length === 0;
  if (!runOk) failures++;
  console.log(
    `${runOk ? "PASS" : "FAIL"} custom created -> run -> results name=custom-${SLUG} ` +
    `labelled=${/not a recorded benchmark result/i.test(banner)} winner="${winner}" ` +
    `dropdownFollowed=${selectValue === `custom-${SLUG}`} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));

  const createOk =
    hasBuildEntry === 1 &&
    optionGroups.length >= 1 &&
    /Starts from/.test(panelIntro) &&
    targetName.includes(`custom-${SLUG}`) &&
    /demand/i.test(changesText) &&
    /A run should take/.test(estimateText);
  if (!createOk) failures++;
  console.log(
    `${createOk ? "PASS" : "FAIL"} custom panel opens from the dropdown fifthEntry=${hasBuildEntry === 1} ` +
    `groups=${optionGroups.length} targetName="${targetName.replace(/\s+/g, " ").slice(0, 40)}" ` +
    `changeListed=${/demand/i.test(changesText)} estimateShown=${/A run should take/.test(estimateText)}`
  );
  await page.screenshot({ path: `${SHOT_DIR}/custom-scenario-result.png` });

  // --- the capacity no-op warning, before the run ---------------------------
  await page.selectOption("[data-testid='scenario-select']", "__custom__");
  await page.waitForSelector(PANEL, { timeout: 15000 });
  await page.fill('[data-testid="custom-name"]', `${SLUG}-noop`);
  await page.click('[data-testid="simple-lane_disruption"] input[type="checkbox"]');
  const fields = page.locator('[data-testid="simple-lane_disruption"] input.control');
  await fields.nth(0).fill("inbound_raw");
  await fields.nth(1).fill("2");
  await fields.nth(2).fill("18");
  await fields.nth(3).fill("10");
  await fields.nth(4).fill("0");
  await page.waitForSelector('[data-testid="custom-capacity-warning"]', { timeout: 20000 });
  const warningBlock = page.locator('[data-testid="custom-capacity-warning"]');
  const warning = await warningBlock.innerText();
  // Assert on the strings *this UI* renders, not just on the API's sentence: the
  // API message already contains "not change the answer", so a looser match would
  // pass even if the amber block and its resilience caveat never rendered.
  const heading = await warningBlock.locator("text=This disruption will not change the answer").count();
  const caveat = await warningBlock.locator("text=Do not read an unchanged result as resilience").count();
  const amber = await warningBlock.evaluate((el) => getComputedStyle(el).backgroundColor);

  const noopOk =
    heading === 1 &&
    caveat === 1 &&
    /period 52/.test(warning) &&
    amber !== "rgba(0, 0, 0, 0)";
  if (!noopOk) failures++;
  console.log(
    `${noopOk ? "PASS" : "FAIL"} custom no-op window warned BEFORE the run heading=${heading === 1} ` +
    `namesReadPeriod=${/period 52/.test(warning)} resilienceCaveat=${caveat === 1} amber="${amber}"`
  );
  // The Iteration 5 screenshot lesson: committed evidence that omits the label it
  // exists to carry is worse than no screenshot. The panel scrolls, so the warning
  // sits below a 1080px fold — scroll it into view before shooting.
  await warningBlock.scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOT_DIR}/custom-scenario-noop-warning.png` });

  // The opt-ins must NOT appear for a recorded scenario: those always run
  // everything, so a switch there would be a lie.
  await page.selectOption("[data-testid='scenario-select']", "baseline");
  const optionsOnRecorded = await page.locator('[data-testid="custom-run-options"]').count();
  if (optionsOnRecorded !== 0) failures++;
  console.log(
    `${optionsOnRecorded === 0 ? "PASS" : "FAIL"} run opt-ins are hidden for a recorded scenario ` +
    `count=${optionsOnRecorded}`
  );

  // Delete has to be reachable from the scenario you are LOOKING AT, not only from
  // inside the panel. A reviewer with custom-test selected reported no delete
  // option at all, because finding it meant switching the dropdown away from it.
  await page.selectOption("[data-testid='scenario-select']", `custom-${SLUG}`);
  const headerDelete = await page.locator('[data-testid="delete-selected-scenario"]').count();
  await page.selectOption("[data-testid='scenario-select']", "baseline");
  const deleteOnRecorded = await page.locator('[data-testid="delete-selected-scenario"]').count();

  // Two-step: deleting is not undoable, so it must not happen on one stray click.
  await page.selectOption("[data-testid='scenario-select']", `custom-${SLUG}`);
  await page.click('[data-testid="delete-selected-scenario"]');
  const confirmShown = await page.locator('[data-testid="delete-confirm-yes"]').count();
  await page.click('[data-testid="delete-confirm-no"]');
  const cancelled = await page.locator('[data-testid="delete-selected-scenario"]').count();

  const headerDeleteOk =
    headerDelete === 1 && deleteOnRecorded === 0 && confirmShown === 1 && cancelled === 1;
  if (!headerDeleteOk) failures++;
  console.log(
    `${headerDeleteOk ? "PASS" : "FAIL"} delete is on the selected scenario's own header ` +
    `presentForCustom=${headerDelete === 1} hiddenForRecorded=${deleteOnRecorded === 0} ` +
    `twoStep=${confirmShown === 1} cancellable=${cancelled === 1}`
  );

  // --- delete, and confirm it leaves the dropdown ---------------------------
  await page.selectOption("[data-testid='scenario-select']", "__custom__");
  await page.waitForSelector(PANEL, { timeout: 15000 });
  const savedBefore = await page.locator('[data-testid="custom-saved-list"] li').count();
  await page.click(`[aria-label="Delete custom-${SLUG}"]`);
  // 60s, not 20s: observed timing out here exactly once, on the run immediately
  // after `make web` recreated the `api` container, and passing on three other runs
  // against a warm one. A delete removes the config, the generated data, the
  // recorded artifact AND the vector-store collection, so a cold container has real
  // work to do on its first call. Widening the tolerance for a slow-but-correct
  // delete — this is not masking a failed assertion; the assertions below still run
  // unchanged and still have to hold.
  await page.waitForFunction(
    (expected) =>
      document.querySelectorAll('[data-testid="custom-saved-list"] li').length < expected ||
      document.querySelectorAll('[data-testid="custom-saved-list"]').length === 0,
    savedBefore,
    { timeout: 60000 },
  );
  const notice = await page.locator('[data-testid="custom-notice"]').innerText().catch(() => "");
  await page.click(`${PANEL} [aria-label="Close custom scenario panel"]`);
  const optionsAfter = await page.locator("[data-testid='scenario-select'] option").allInnerTexts();

  const deleteOk =
    /Deleted/.test(notice) &&
    !optionsAfter.some((text) => text.includes(SLUG)) &&
    optionsAfter.some((text) => text.trim() === "baseline");
  if (!deleteOk) failures++;
  console.log(
    `${deleteOk ? "PASS" : "FAIL"} custom deleted and gone from the dropdown ` +
    `notice="${notice.slice(0, 40)}" stillListed=${optionsAfter.some((t) => t.includes(SLUG))} ` +
    `recordedFourIntact=${optionsAfter.filter((t) => !t.includes("custom")).length >= 4}`
  );

  await context.close();
}

// --- Iteration 6a: the recorded walkthrough must not offer a control that needs
// the API. `?replay=true` blocks every /api/ call by design, so a "Custom
// scenario…" entry there could only ever produce "Failed to fetch".
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  await page.route("**/api/**", (route) => route.abort());
  await page.goto(`${BASE}/?replay=true`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=Why this plan", { timeout: 25000 }).catch(() => {});

  const offered = await page
    .locator("[data-testid='scenario-select'] option[value='__custom__']")
    .count();
  const noPanel = (await page.locator('[data-testid="custom-panel"]').count()) === 0;
  const replayOk = offered === 0 && noPanel && errs.length === 0;
  if (!replayOk) failures++;
  console.log(
    `${replayOk ? "PASS" : "FAIL"} replay offers no custom-scenario control ` +
    `entryOffered=${offered} panelAbsent=${noPanel} errors=${errs.length}`
  );

  await context.close();
}

// --- Iteration 6a: the entry has to be on the dataset view too -----------------
// The plan's Phase 4 objective is "the control panel Ryan asked for, ON THE SCREEN
// HE LIKED" — and the screen he singled out is the dataset view, not the results
// screen. It was initially wired only into the results dropdown, and a reviewer
// looking at the dataset view could not find it at all.
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });

  await page.goto(`${BASE}/?view=dataset&scenario=baseline`, { waitUntil: "networkidle" });
  await page.waitForSelector("text=How the network is laid out", { timeout: 20000 }).catch(() => {});

  const SELECT = "[data-testid='dataset-scenario-select']";
  const offered = await page.locator(`${SELECT} option[value='__custom__']`).count();
  const grouped = await page
    .locator(`${SELECT} optgroup`)
    .evaluateAll((groups) => groups.map((group) => group.label));

  await page.selectOption(SELECT, "__custom__");
  const panelOpened = await page
    .waitForSelector('[data-testid="custom-panel"]', { timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  // Beside, not over: the map Ryan likes has to stay on screen.
  const mapStillVisible = await page.locator("text=How the network is laid out").isVisible();

  // The same control on this screen, since this is where a planner is looking.
  await page.goto(`${BASE}/?view=dataset&scenario=baseline`, { waitUntil: "networkidle" });
  const datasetDeleteOnRecorded = await page
    .locator('[data-testid="delete-selected-scenario"]')
    .count();

  const datasetOk =
    datasetDeleteOnRecorded === 0 &&
    offered === 1 &&
    grouped.includes("Recorded benchmark scenarios") &&
    panelOpened &&
    mapStillVisible &&
    errs.length === 0;
  if (!datasetOk) failures++;
  console.log(
    `${datasetOk ? "PASS" : "FAIL"} custom panel opens from the DATASET view ` +
    `entryOffered=${offered === 1} grouped=${grouped.length} panelOpened=${panelOpened} ` +
    `mapStillVisible=${mapStillVisible} deleteHiddenForRecorded=${datasetDeleteOnRecorded === 0} ` +
    `errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));

  await context.close();
}

// --- Iteration 6a: a new build must actually reach a returning viewer ----------
// index.html is not fingerprinted — it is the file that names the current asset
// hashes — so if it is cacheable, someone who has visited before keeps loading the
// previous build and simply does not see new features. That happened during Phase 5
// review: the panel was live in the container and invisible in the browser.
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();

  const indexResponse = await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  const indexCache = (indexResponse?.headers()["cache-control"] ?? "").toLowerCase();

  const assetHref = await page.evaluate(() => {
    const script = Array.from(document.querySelectorAll("script[src]")).find((s) =>
      s.getAttribute("src")?.includes("/assets/"),
    );
    return script?.getAttribute("src") ?? null;
  });
  let assetCache = "";
  if (assetHref) {
    const assetResponse = await page.request.get(new URL(assetHref, `${BASE}/`).toString());
    assetCache = (assetResponse.headers()["cache-control"] ?? "").toLowerCase();
  }

  const cacheOk =
    /no-store/.test(indexCache) &&
    /immutable/.test(assetCache) &&
    Boolean(assetHref);
  if (!cacheOk) failures++;
  console.log(
    `${cacheOk ? "PASS" : "FAIL"} a new build reaches a returning viewer ` +
    `indexCacheControl="${indexCache}" assetCacheControl="${assetCache}"`
  );

  await context.close();
}

// ---------------------------------------------------------------------------
// Iteration 6b Phase 2 — a network-edited dataset, end to end in a real browser.
//
// The network controls are deliberately NOT in the form yet (Phase 3 renders their
// honesty labels), so these datasets are created over the API — which is exactly
// what Phase 2 claims works: a custom dataset is still just a config, so the
// dataset view, the change list and the network map carry it with no changes.
// ---------------------------------------------------------------------------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });

  const api = (path, body) =>
    page.evaluate(
      async ([p, b]) => {
        const r = await fetch(p, b ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(b),
        } : {});
        return { status: r.status, json: await r.json().catch(() => null) };
      },
      [path, body ?? null],
    );

  const del = (name) =>
    page.evaluate(async (n) => {
      const r = await fetch(`/api/scenarios/custom/${n}`, { method: "DELETE" });
      return r.status;
    }, name);

  // Clean slate, in case a previous run died mid-way. These 404 when there is
  // nothing to delete, and the browser logs a failed request as a console error —
  // so reset the collector afterwards or the setup fails the console-clean check.
  await del("custom-e2e-onedc");
  await del("custom-e2e-seven");
  errs.length = 0;

  // --- 1. Reducing a warehouse: Ryan's actual sentence ---------------------
  const savedDc = await api("/api/scenarios/custom", {
    name: "e2e-onedc",
    overrides: { "network.distribution_centers": 1 },
  });

  // Baseline's own node count first, so the redraw is a comparison and not a guess.
  const nodeCountFor = async (scenario) => {
    await page.goto(`${BASE}/?view=dataset&scenario=${scenario}`, { waitUntil: "networkidle" });
    await page.waitForSelector("text=How the network is laid out", { timeout: 20000 }).catch(() => {});
    return page.evaluate(async (s) => {
      const r = await fetch(`/api/dataset/overview?scenario=${s}`);
      const d = await r.json();
      return d.data.dataset_overview.network.node_count;
    }, scenario);
  };

  const baselineNodes = await nodeCountFor("baseline");
  const customNodes = await nodeCountFor("custom-e2e-onedc");
  const summary = await page
    .locator("section p.text-lg, section p.sm\\:text-xl").first().innerText().catch(() => "");
  const diffText = await page.locator("body").innerText();

  // NetworkMap.tsx is untouched by this iteration; a network-count change is the
  // one edit that makes it redraw on its own, which is the free demo beat.
  const mapRedrew = customNodes === 16 && baselineNodes === 17;
  const summaryOk = /1 distribution center\b/.test(summary) && !/1 distribution centers/.test(summary);
  const diffOk = diffText.includes("distribution_centers") || /network size/i.test(diffText);
  const dcOk = savedDc.status === 200 && mapRedrew && summaryOk && diffOk && errs.length === 0;
  if (!dcOk) failures++;
  console.log(
    `${dcOk ? "PASS" : "FAIL"} a 1-DC dataset renders on the dataset view and the map redraws ` +
    `saved=${savedDc.status} baselineNodes=${baselineNodes} customNodes=${customNodes} ` +
    `summarySingular=${summaryOk} changeListed=${diffOk} errors=${errs.length}`
  );
  await page.screenshot({ path: `${SHOT_DIR}/network-onedc-dataset-view.png`, fullPage: false });

  // --- 2. A resized network must NOT be comparable, on screen -------------
  await api("/api/scenarios/custom", {
    name: "e2e-seven",
    overrides: { "network.customers": 7 },
  });
  const run = await api("/api/scenario-comparison", { scenario: "custom-e2e-seven", horizon: 8 });
  const codes = (run.json?.data?.warnings ?? []).map((w) => w.code);
  const comparable = run.json?.data?.network_comparability?.comparable_to_baseline;
  const objective = run.json?.data?.benchmark?.winner?.objective;
  const resizedOk =
    run.status === 200 &&
    comparable === false &&
    codes.includes("resized_network_not_comparable") &&
    Math.abs(objective - 66548.241282) < 1e-6;
  if (!resizedOk) failures++;
  console.log(
    `${resizedOk ? "PASS" : "FAIL"} a resized network runs and is labelled NOT comparable ` +
    `objective=${objective} comparable=${comparable} warnings=[${codes.join(",")}]`
  );

  // ...and the caveat is actually rendered beside the number, not just in the payload.
  // Loading `?scenario=` does not run anything — the results screen is empty until
  // Run is pressed — so drive the real control rather than assuming a URL runs it.
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.selectOption('[data-testid="scenario-select"]', "custom-e2e-seven");
  await page.click('[data-testid="run-scenario"]');
  await page.waitForSelector('[data-testid="custom-result-banner"]', { timeout: 180000 }).catch(() => {});
  const notComparableBlock = await page
    .locator('[data-testid="custom-result-not-comparable"]').count();
  const bannerText = await page
    .locator('[data-testid="custom-result-banner"]').innerText().catch(() => "");
  const renderedOk =
    notComparableBlock === 1 &&
    /not comparable to the recorded baseline/i.test(bannerText) &&
    /81,789\.36/.test(bannerText);
  if (!renderedOk) failures++;
  console.log(
    `${renderedOk ? "PASS" : "FAIL"} the not-comparable caveat is rendered next to the objective ` +
    `block=${notComparableBlock} namesBaseline=${/81,789\.36/.test(bannerText)}`
  );
  await page.screenshot({ path: `${SHOT_DIR}/network-resized-not-comparable.png`, fullPage: false });

  // --- 3. A comparable network gets no false caveat ------------------------
  await page.selectOption('[data-testid="scenario-select"]', "custom-e2e-onedc");
  await page.click('[data-testid="run-scenario"]');
  await page.waitForSelector('[data-testid="custom-result-banner"]', { timeout: 180000 }).catch(() => {});
  await page.waitForTimeout(500);
  const falseCaveat = await page.locator('[data-testid="custom-result-not-comparable"]').count();
  const noCryWolf = falseCaveat === 0;
  if (!noCryWolf) failures++;
  console.log(
    `${noCryWolf ? "PASS" : "FAIL"} reducing a warehouse gets NO not-comparable caveat ` +
    `block=${falseCaveat}`
  );

  // --- 4. Delete leaves nothing behind ------------------------------------
  const d1 = await del("custom-e2e-onedc");
  const d2 = await del("custom-e2e-seven");
  const list = await api("/api/scenarios/custom");
  const remaining = (list.json?.data?.scenarios ?? []).map((s) => s.scenario);
  const gone =
    d1 === 200 && d2 === 200 &&
    !remaining.includes("custom-e2e-onedc") && !remaining.includes("custom-e2e-seven");
  if (!gone) failures++;
  console.log(
    `${gone ? "PASS" : "FAIL"} both network datasets deleted and gone from the list ` +
    `statuses=${d1}/${d2} remaining=${remaining.length}`
  );

  await context.close();
}

// ---------------------------------------------------------------------------
// Iteration 6b Phase 3 — the Network group, driven the way Ryan will drive it.
// Phase 2 created its datasets over the API because the controls did not exist
// yet. These go through the panel.
// ---------------------------------------------------------------------------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));

  const SLUG = `net${Math.random().toString(36).slice(2, 8)}`;
  const PANEL = '[data-testid="custom-panel"]';

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });

  // --- 0. 🔴 Two doors for two asks ---------------------------------------
  // Ryan asked for a custom scenario AND a custom dataset. Until this was added,
  // every label said "scenario" and the dataset ask looked undelivered.
  const entries = await page
    .locator("[data-testid='scenario-select'] option")
    .allInnerTexts();
  const hasScenarioDoor = entries.some((t) => /Custom scenario — the conditions/.test(t));
  const hasDatasetDoor = entries.some((t) => /Custom dataset — the network/.test(t));

  // The dataset door opens the SAME panel, at the network tier.
  await page.selectOption('[data-testid="scenario-select"]', "__custom_dataset__");
  await page.waitForSelector('[data-testid="custom-network"]', { timeout: 20000 });
  const tiersLine = await page
    .locator('[data-testid="custom-panel-tiers"]').innerText().catch(() => "");
  const onePanel = (await page.locator('[data-testid="custom-panel"]').count()) === 1;
  const doorsOk =
    hasScenarioDoor && hasDatasetDoor && onePanel &&
    /conditions/i.test(tiersLine) && /network/i.test(tiersLine);
  if (!doorsOk) failures++;
  console.log(
    `${doorsOk ? "PASS" : "FAIL"} both asks have a door and both open ONE panel ` +
    `scenarioDoor=${hasScenarioDoor} datasetDoor=${hasDatasetDoor} panels=${onePanel ? 1 : "!=1"} ` +
    `headerNamesBothTiers=${/conditions/i.test(tiersLine) && /network/i.test(tiersLine)}`
  );

  // --- 1. The three label classes are rendered distinctly ------------------
  const shapeLabel = await page
    .locator('[data-testid="network-class-label-changes_network_shape"]').innerText().catch(() => "");
  const sizeLabel = await page
    .locator('[data-testid="network-class-label-changes_problem_size"]').innerText().catch(() => "");
  const shapeCounts = await page
    .locator('[data-testid="network-class-changes_network_shape"] input').count();
  const sizeCounts = await page
    .locator('[data-testid="network-class-changes_problem_size"] input').count();
  // The inert count must NOT be a live network control (decision 7).
  const inertAsLive = await page.locator('[data-testid="network-network.lines_per_plant"]').count();

  const labelsOk =
    /NOT a resilience test/.test(shapeLabel) &&
    /never against the recorded baseline/.test(sizeLabel) &&
    shapeCounts === 3 && sizeCounts === 4 && inertAsLive === 0;
  if (!labelsOk) failures++;
  console.log(
    `${labelsOk ? "PASS" : "FAIL"} the network group renders both honesty classes distinctly ` +
    `shapeCounts=${shapeCounts} sizeCounts=${sizeCounts} inertOfferedAsLive=${inertAsLive} ` +
    `notResilience=${/NOT a resilience test/.test(shapeLabel)} ` +
    `notComparable=${/never against the recorded baseline/.test(sizeLabel)}`
  );

  // A clean capture of the group as a planner first meets it, before anything is
  // typed. Kept in `web-check` so the committed 6b screenshot set is fully
  // reproducible — which is the claim the 6a set could not make.
  await page.locator('[data-testid="custom-network"]')
    .screenshot({ path: `${SHOT_DIR}/network-group.png` });

  // --- 2. 🔴 Decision 4: typing 0 must REACH the measured refusal ----------
  await page.fill('[data-testid="custom-name"]', `${SLUG}-zero`);
  await page.fill('[data-testid="network-network.distribution_centers"] input', "0");
  await page.waitForFunction(
    () => document.body.innerText.includes("68,565.25"),
    null,
    { timeout: 20000 },
  ).catch(() => {});
  const panelText = await page.locator(PANEL).innerText();
  const saveDisabled = await page.locator('[data-testid="custom-save-run"]').isDisabled()
    .catch(() => false);
  const teachesOk =
    panelText.includes("68,565.25") &&
    panelText.includes("92.01%") &&
    /limit of the model/.test(panelText) &&
    saveDisabled;
  if (!teachesOk) failures++;
  console.log(
    `${teachesOk ? "PASS" : "FAIL"} zero warehouses is refused with the MEASURED reason, not clamped ` +
    `quotes68565=${panelText.includes("68,565.25")} quotes9201=${panelText.includes("92.01%")} ` +
    `saysModelLimit=${/limit of the model/.test(panelText)} saveDisabled=${saveDisabled}`
  );
  await page.locator(PANEL).screenshot({ path: `${SHOT_DIR}/network-zero-dc-refusal.png` });

  // --- 3. Ryan's sentence: reduce a warehouse, run it ---------------------
  await page.fill('[data-testid="network-network.distribution_centers"] input', "1");
  await page.fill('[data-testid="custom-name"]', SLUG);
  // Assert the SPECIFIC transition, and wait for the debounced preview to catch up.
  // A looser check (/distribution_centers/ plus a stray "2") passed against the
  // stale "2 -> 0" text from the refusal step above — a check that goes green on
  // the wrong displayed value is worse than no check.
  await page.waitForSelector('[data-testid="custom-changes"]', { timeout: 20000 });
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="custom-changes"]');
      return Boolean(el && /distribution_centers\s*2\s*\u2192\s*1/.test(el.textContent ?? ""));
    },
    null,
    { timeout: 20000 },
  ).catch(() => {});
  const changesText = await page.locator('[data-testid="custom-changes"]').innerText();
  const changeOk =
    /distribution_centers/.test(changesText) &&
    /2\s*\u2192\s*1/.test(changesText) &&
    !/\u2192\s*0/.test(changesText);
  if (!changeOk) failures++;
  console.log(
    `${changeOk ? "PASS" : "FAIL"} the change list names the network edit 2 -> 1 ` +
    `changes="${changesText.replace(/\s+/g, " ").slice(0, 90)}"`
  );

  await page.click('[data-testid="custom-save-run"]');
  await page.waitForSelector('[data-testid="custom-result-banner"]', { timeout: 180000 });
  const bannerText = await page.locator('[data-testid="custom-result-banner"]').innerText();
  const falseCaveat = await page.locator('[data-testid="custom-result-not-comparable"]').count();
  const bodyText = await page.locator("body").innerText();
  // 🔴 The banner must call this a DATASET, because the network was changed. This
  // is the sentence that answers "did you build my second ask".
  const kindText = await page.locator('[data-testid="custom-result-kind"]').innerText().catch(() => "");
  const ranOk =
    bannerText.includes(`custom-${SLUG}`) &&
    /81,663/.test(bodyText) &&
    /custom dataset/i.test(kindText) &&
    falseCaveat === 0 &&
    errs.length === 0;
  if (!ranOk) failures++;
  console.log(
    `${ranOk ? "PASS" : "FAIL"} a 1-DC dataset built IN THE PANEL runs to 81,663, labelled DATASET ` +
    `named=${bannerText.includes(`custom-${SLUG}`)} objective81663=${/81,663/.test(bodyText)} ` +
    `kind="${kindText.replace(/\s+/g, " ").slice(0, 40)}" falseCaveat=${falseCaveat} errors=${errs.length}`
  );
  await page.screenshot({ path: `${SHOT_DIR}/network-group-result.png` });

  // --- 4. A resized network built in the panel IS caveated ----------------
  await page.selectOption('[data-testid="scenario-select"]', "__custom__");
  await page.waitForSelector('[data-testid="custom-network"]', { timeout: 20000 });
  await page.fill('[data-testid="custom-name"]', `${SLUG}-sized`);
  await page.fill('[data-testid="network-network.customers"] input', "7");
  await page.click('[data-testid="custom-save-run"]');
  await page.waitForSelector('[data-testid="custom-result-not-comparable"]', { timeout: 180000 })
    .catch(() => {});
  const caveat = await page.locator('[data-testid="custom-result-not-comparable"]').count();
  const caveatText = await page
    .locator('[data-testid="custom-result-not-comparable"]').innerText().catch(() => "");
  const sizedBody = await page.locator("body").innerText();
  const caveatOk =
    caveat === 1 && /81,789\.36/.test(caveatText) && /66,548/.test(sizedBody);
  if (!caveatOk) failures++;
  console.log(
    `${caveatOk ? "PASS" : "FAIL"} a resized network built IN THE PANEL is caveated beside 66,548 ` +
    `block=${caveat} namesBaseline=${/81,789\.36/.test(caveatText)}`
  );

  // --- 5. Reopen and delete both, through the UI --------------------------
  await page.selectOption('[data-testid="scenario-select"]', "__custom__");
  await page.waitForSelector('[data-testid="custom-saved-list"]', { timeout: 20000 });
  const savedBefore = await page.locator('[data-testid="custom-saved-list"] li').count();
  for (const name of [`custom-${SLUG}`, `custom-${SLUG}-sized`]) {
    await page.click(`[aria-label="Delete ${name}"]`);
    await page.waitForTimeout(1200);
  }
  const savedAfter = await page.locator('[data-testid="custom-saved-list"] li').count();
  const options = await page.locator("[data-testid='scenario-select'] option").allInnerTexts();
  const deletedOk =
    savedAfter === savedBefore - 2 &&
    !options.some((t) => t.includes(SLUG)) &&
    options.filter((t) => !t.includes("custom")).length >= 4;
  if (!deletedOk) failures++;
  console.log(
    `${deletedOk ? "PASS" : "FAIL"} both panel-built network datasets deleted, recorded four intact ` +
    `saved=${savedBefore}->${savedAfter} recordedIntact=${options.filter((t) => !t.includes("custom")).length >= 4}`
  );

  await context.close();
}

// ---------------------------------------------------------------------------
// 🔴 The realistic multi-step session — Save / Save & run button state.
//
// This check exists because the defect it covers was found by the sponsor during
// a live demo, not by this suite. Every other custom-scenario check here performs
// ONE action and asserts the outcome, so all of them passed while the most obvious
// two-click sequence in the panel — Save, then Save & run — errored with
// "already exists": the panel had no idea it had just saved.
//
// Rule for anyone extending this file: at least one check must move through the
// panel the way a person does, several steps deep, not one action at a time.
// ---------------------------------------------------------------------------
{
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));

  const SLUG = `seq${Math.random().toString(36).slice(2, 8)}`;
  const NAME = `custom-${SLUG}`;
  const PANEL = '[data-testid="custom-panel"]';

  const state = async () => ({
    saveEnabled: await page.locator('[data-testid="custom-save"]').isEnabled().catch(() => false),
    saveLabel: (await page.locator('[data-testid="custom-save"]').innerText().catch(() => "")).trim(),
    saveRun: await page.locator('[data-testid="custom-save-run"]').count(),
    run: await page.locator('[data-testid="custom-run"]').count(),
  });
  const panelSays = async (re) =>
    re.test(await page.locator(PANEL).innerText().catch(() => ""));

  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.selectOption('[data-testid="scenario-select"]', "__custom__");
  await page.waitForSelector(PANEL, { timeout: 20000 });

  // --- 1. Unsaved edits: Save is offered, and the primary saves AND runs ----
  await page.fill('[data-testid="custom-name"]', SLUG);
  await page.fill('[data-testid="simple-demand_level"] input', "52");
  await page.waitForFunction(
    () => {
      const b = document.querySelector('[data-testid="custom-save"]');
      return b && !b.disabled;
    },
    null,
    { timeout: 30000 },
  ).catch(() => {});
  const dirty = await state();
  const dirtyOk = dirty.saveEnabled && dirty.saveRun === 1 && dirty.run === 0;
  if (!dirtyOk) failures++;
  console.log(
    `${dirtyOk ? "PASS" : "FAIL"} unsaved edits offer Save and Save & run ` +
    `saveEnabled=${dirty.saveEnabled} saveRunShown=${dirty.saveRun === 1} runShown=${dirty.run === 1}`
  );

  // --- 2. 🔴 Click SAVE ONLY. This is the click that used to poison the next
  //         one. Save must grey out and the primary must become a plain Run.
  await page.click('[data-testid="custom-save"]');
  await page.waitForSelector('[data-testid="custom-run"]', { timeout: 60000 }).catch(() => {});
  const clean = await state();
  const cleanOk =
    !clean.saveEnabled && /saved/i.test(clean.saveLabel) &&
    clean.run === 1 && clean.saveRun === 0 && !(await panelSays(/already exists/i));
  if (!cleanOk) failures++;
  console.log(
    `${cleanOk ? "PASS" : "FAIL"} after Save the pair flips: Save greys out, primary becomes Run ` +
    `saveDisabled=${!clean.saveEnabled} saveLabel="${clean.saveLabel}" ` +
    `runShown=${clean.run === 1} saveRunGone=${clean.saveRun === 0}`
  );

  // --- 3. Edit again: the pair must flip BACK ------------------------------
  await page.fill('[data-testid="simple-demand_level"] input', "48");
  await page.waitForFunction(
    () => document.querySelector('[data-testid="custom-save-run"]') !== null,
    null,
    { timeout: 30000 },
  ).catch(() => {});
  const redirty = await state();
  const redirtyOk = redirty.saveEnabled && redirty.saveRun === 1 && redirty.run === 0;
  if (!redirtyOk) failures++;
  console.log(
    `${redirtyOk ? "PASS" : "FAIL"} editing after a save re-enables Save and restores Save & run ` +
    `saveEnabled=${redirty.saveEnabled} saveRunBack=${redirty.saveRun === 1} runGone=${redirty.run === 0}`
  );

  // --- 4. 🔴 THE REPORTED SEQUENCE. Save & run under the SAME name, after an
  //         edit. Must overwrite this session's own scenario, not collide.
  await page.click('[data-testid="custom-save-run"]');
  await page.waitForSelector('[data-testid="custom-result-banner"]', { timeout: 180000 })
    .catch(() => {});
  const banner = await page.locator('[data-testid="custom-result-banner"]').innerText()
    .catch(() => "");
  const body = await page.locator("body").innerText();
  const overwriteOk =
    banner.includes(NAME) && !/already exists/i.test(body) && errs.length === 0;
  if (!overwriteOk) failures++;
  console.log(
    `${overwriteOk ? "PASS" : "FAIL"} Save & run after an edit overwrites its own scenario ` +
    `named=${banner.includes(NAME)} noCollision=${!/already exists/i.test(body)} errors=${errs.length}`
  );
  if (errs.length) console.log("   errors:", errs.slice(0, 3));

  // --- 5. 🔴 Decision 14 regression. Closing the panel ends the session, so the
  //         next one has no claim on that name and must still be refused. This is
  //         the guard the fix NARROWS rather than removes: it protects names this
  //         session did not create.
  await page.selectOption('[data-testid="scenario-select"]', "__custom__");
  await page.waitForSelector(PANEL, { timeout: 20000 });
  await page.fill('[data-testid="custom-name"]', SLUG);
  await page.fill('[data-testid="simple-demand_level"] input', "44");
  await page.waitForFunction(
    () => {
      const b = document.querySelector('[data-testid="custom-save"]');
      return b && !b.disabled;
    },
    null,
    { timeout: 30000 },
  ).catch(() => {});
  await page.click('[data-testid="custom-save"]');
  await page.waitForFunction(
    () => /already exists/i.test(document.body.innerText),
    null,
    { timeout: 30000 },
  ).catch(() => {});
  const refusedOk = await panelSays(/already exists/i);
  if (!refusedOk) failures++;
  console.log(
    `${refusedOk ? "PASS" : "FAIL"} a name THIS session did not create is still refused (decision 14) ` +
    `refused=${refusedOk}`
  );

  // Clean up after ourselves: this check saves for real, on a box-global store.
  const cleanup = await page.evaluate(async (n) => {
    const r = await fetch(`/api/scenarios/custom/${n}`, { method: "DELETE" });
    return r.status;
  }, SLUG);
  console.log(`     (cleanup: deleted ${NAME} -> ${cleanup})`);

  await context.close();
}

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
