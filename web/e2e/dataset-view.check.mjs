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

  const labellingOk =
    /not read by the optimizer/i.test(inertHeading) &&
    dcThroughputLabelled &&
    advancedSettingCount === 59;
  if (!labellingOk) failures++;
  console.log(
    `${labellingOk ? "PASS" : "FAIL"} custom advanced labelling settings=${advancedSettingCount} ` +
    `inertHeading="${inertHeading.slice(0, 48)}" dcThroughputFlagged=${dcThroughputLabelled}`
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

  // --- delete, and confirm it leaves the dropdown ---------------------------
  const savedBefore = await page.locator('[data-testid="custom-saved-list"] li').count();
  await page.click(`[aria-label="Delete custom-${SLUG}"]`);
  await page.waitForFunction(
    (expected) =>
      document.querySelectorAll('[data-testid="custom-saved-list"] li').length < expected ||
      document.querySelectorAll('[data-testid="custom-saved-list"]').length === 0,
    savedBefore,
    { timeout: 20000 },
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

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures === 0 ? 0 : 1);
