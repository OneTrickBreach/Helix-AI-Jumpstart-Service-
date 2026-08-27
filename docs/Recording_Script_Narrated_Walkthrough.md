# Recording script — narrated walkthrough

**For:** Ishan, reading aloud from a second laptop while OBS records the screen.
**Asked for by:** Ryan, at the 2026-08-26 demo.
**Audience:** anyone — assume no supply-chain knowledge at all.
**Length:** ~1,400 spoken words. **≈10½ minutes** at a natural pace, or **≈9½** if you cut Shot 4.

---

## How to use this page

Everything alternates. **▶ DO** is what your hands do. **🎙 SAY** is what you read out loud, word for
word. Never do both at once — finish the click, *then* start the sentence, unless a step says
otherwise.

- **Blockquoted text is the script.** Read it as written. It is written to be *said*, not read
  silently, so the sentences are short and there is nothing to trip over.
- *(Italics in round brackets)* are stage directions to you. **Never read those out.**
- Timecodes are targets, not rules. A minute either way is fine.

### The shot list at a glance

| # | Shot | Tab | Words | Ends |
|---|---|---|---:|---:|
| 1 | Cold open — what this even is | A | 118 | 0:55 |
| 2 | What the tool actually produced | A | 193 | 2:15 |
| 3 | But what data is this? | A | 203 | 3:50 |
| 4 | Ask it a question 🔴 *cuttable* | A | 131 | 4:45 |
| 5 | Go live — build your own | **B** | 187 | 6:20 |
| 6 | The two buttons | B | 102 | 7:00 |
| 7 | "Why can't we just remove a warehouse?" | B | 89 | 7:55 |
| 8 | 🔴 **Type a zero** — the point of the video | B | 230 | 9:35 |
| 9 | Close | B | 123 | 10:20 |

**Cutting Shot 4 saves about a minute** and costs nothing later — it is the only shot nothing else
depends on.

---

## ▶ PRE-FLIGHT — before you hit record

Ten minutes, done once. Do not skip 4 or 5.

1. **Check the box is healthy.**
   ```bash
   curl -s localhost:8080/health
   ```
   It must say `"gpu_visible":true`. If not:
   `docker compose up -d --no-deps --force-recreate api`, wait, check again.

2. **Clear old custom scenarios**, so the saved list starts empty and the video is not confusing.
   Use **Delete all** in the panel. 🔴 `custom-test1` and `custom-test3` are left over from the live
   demo — get rid of those too.

3. **Two browser tabs, in this order.** You switch between them exactly once, at 4:45.
   - **Tab A** — `http://localhost:8081?replay=true`
   - **Tab B** — `http://localhost:8081`

4. **Hard-reload both tabs** — `Ctrl+Shift+R`. A cached build is the single most common cause of
   "the button isn't there".

5. **Window at 1920×1080, browser zoom ~110%.** The amber honesty blocks are the most important thing
   in this video and they must be legible on someone else's screen.

6. **Let Tab A finish animating.** `?replay=true` loads its own capture automatically — it is already
   the **component-shortage-shock** scenario, so there is nothing to select. It steps through the
   pipeline in about two seconds. Have the *finished* results screen up before you start talking.

7. **Do one silent practice pass of Shot 8** — typing the zero. It is the beat the whole video builds
   to, and you do not want to be hunting for the field on camera.

---

# THE SCRIPT

---

## SHOT 1 — Cold open · what this even is
**[0:00 – 0:55] · Tab A · the finished results screen**

▶ **DO**
1. Screen shows the **component-shortage-shock** results — already loaded from pre-flight — scrolled
   to the top, so the green **"Why This Plan"** card fills the frame.
2. Do not click anything. Just talk.

🎙 **SAY**

> Every company that makes a physical product answers the same question every week. How much do I
> order, where do I keep it, how do I move it — so I don't run out, and don't overspend.
>
> Most planners answer that with a spreadsheet and experience. This tool answers it with an
> optimizer, and then explains itself.
>
> All of it runs on one computer. This one — an NVIDIA GB10. A desktop machine, not a data centre.
> Nothing leaves the box.
>
> One thing up front. This first part is a recording of a real run on this machine. The numbers were
> measured here. I'm replaying them so you don't watch me wait three minutes. Then I'll go live.

---

## SHOT 2 — What the tool actually produced
**[0:55 – 2:15] · Tab A · results screen**

▶ **DO**
1. Point the cursor at the scenario name and the **Winner** badge on the green card.
2. Move down to the three big metrics: total cost, fill rate, days of inventory.

🎙 **SAY**

> So: a week in the life of a factory network. This scenario is called "component shortage shock". A
> supplier stops delivering a part. That's the whole story.
>
> The tool planned around it. Three numbers.
>
> Cost — what the plan costs to run. Fill rate — the share of customer orders you meet on time,
> higher is better. And days of inventory — how long you could keep selling if deliveries stopped
> tomorrow.

▶ **DO**
3. Scroll slowly to the **Before vs After** cards. Let them sit on screen.

🎙 **SAY**

> And here's what matters. Every number is shown twice. Before, and after.
>
> Before is the ordinary way: reorder when stock drops below a line, ship by the shortest route.
> That's not a strawman — that's how a lot of planning actually gets done.
>
> After is the optimizer. Seven point two percent cheaper, and it fills more orders while doing it.
> Eighty-two and a half percent, up from just under eighty. Cheaper and better service at the same
> time.

▶ **DO**
4. Scroll to the **Approaches** table. Point at the **PPO** row.

🎙 **SAY**

> Now, this row. We also trained a reinforcement-learning agent, because that's what everyone asks
> about. It lost — more expensive, and it fills fewer orders.
>
> We left it on screen anyway. If we'd deleted it, you'd have no way of knowing we tried.

---

## SHOT 3 — But what data is this?
**[2:15 – 3:50] · Tab A · dataset view**

▶ **DO**
1. Click **View the dataset** in the header.
2. Point at the **amber badge, top right**.

🎙 **SAY**

> The first thing anyone sensible asks is: what data is this?
>
> Before anything else — that badge. This is synthetic data, generated on this device from a seed. It
> is not anybody's customer data. The badge stays on screen so nobody forgets.

▶ **DO**
3. Point at the one-sentence summary near the top. Say it as your own sentence — do not say
   "it says here".

🎙 **SAY**

> And here's the whole business in one sentence. Five suppliers ship parts to two factories running
> six production lines. Those send finished goods through two warehouses out to eight customers.
> Twenty-eight products, fifty-two weeks of order history.
>
> That sentence isn't typed by hand. It's assembled from the files on disk.

▶ **DO**
4. Move down to the six tiles. Rest the cursor on **seed 12345**.

🎙 **SAY**

> Six numbers underneath. Seventeen locations, twenty-eight products, thirty shipping lanes,
> fifty-two weeks, nearly three thousand order records — and a seed.
>
> The seed matters. Generate it again with one-two-three-four-five and you get the identical dataset,
> byte for byte.

▶ **DO**
5. Scroll to the **network map**. Pause — let it breathe for two full seconds before speaking.

🎙 **SAY**

> And this is the network. Suppliers on the left, factories, warehouses, customers on the right.
> Every box is a real location. Every line is a real shipping lane.

▶ **DO**
6. Point at the **amber lines** on the map.

🎙 **SAY**

> And that is the shortage. Two lanes out of one supplier drop to zero for ten weeks, and their
> delivery times triple.
>
> That's not a caption someone typed. It's read out of the generated files — so the picture can't
> drift away from the data.

---

## SHOT 4 — Ask it a question
**[3:50 – 4:45] · Tab A · chat panel**
🔴 *(This is the shot to cut if you are running long. Nothing later depends on it.)*

▶ **DO**
1. Click the **Ask the plan** button, bottom right. Note the **BETA** chip on it.
2. In the suggested questions, click **"What if warehouse 4 is completely depleted?"**
3. The answer appears instantly — no model runs for this one.

🎙 **SAY**

> There's also a chat panel. It's marked beta — deliberately, and I'll come back to that.
>
> I'm going to ask it a trick question. I'm asking about warehouse 4. There is no warehouse 4 here.
> There are two.

▶ **DO**
4. Let the answer sit on screen. Point at it.

🎙 **SAY**

> And it doesn't invent one. It says warehouse 4 doesn't exist, names the two that do, and offers the
> one scenario that really does have four.
>
> That's the behaviour worth having. The language model reads and explains — it never calculates a
> number. Every figure it quotes comes from a file on this disk or a real optimizer run, and that's
> checked before it reaches the screen.
>
> It says beta because the sponsor hasn't signed it off. Not because it's broken — because nobody has
> approved it, and the label should say so.

---

## SHOT 5 — Now go live. Build your own.
**[4:45 – 6:20] · SWITCH TO TAB B**

▶ **DO**
1. **Switch to Tab B** — the live system.
2. Open the **Scenario** dropdown. Let the three groups show for a moment: the recorded scenarios,
   your saved ones, and **Build your own**.
3. Choose **"Custom scenario — the conditions…"**. The panel opens beside the page.

🎙 **SAY**

> Right. That was a recording. From here it's live, on the box, as it happens.
>
> Everything so far was four scenarios somebody else chose. That's the obvious limitation — and it's
> what the sponsor asked for. Let me build my own.

▶ **DO**
4. Point at **THE CONTROLS** — the eight grouped controls.

🎙 **SAY**

> Eight controls, phrased the way a planner talks. How much are customers ordering. Is a spike
> coming. How tight is capacity. Is a lane disrupted. What do the costs look like. What am I
> promising on service.
>
> Notice "demand spike" is one control, not three sliders. "A surge of one-point-six times, for eight
> weeks, from week thirty" is one thing a human says — so it's one thing on screen.

▶ **DO**
5. Type `q3-surge` into **Name this scenario**.
6. Set **Demand level** to `52`. *(It starts at 44.)*
7. Point at **WHAT YOU CHANGED (1)** as it appears, then at the run estimate below it.

🎙 **SAY**

> I'll name it, and change one thing — customers ordering more. Forty-four, up to fifty-two.
>
> Two things happen. It lists exactly what I changed and nothing else, because everything I didn't
> touch is inherited.
>
> And it estimates the run, broken into steps, with where each estimate came from. It even admits
> this scenario has never been run before, so it's borrowing timings from a similar one. That's an
> estimate you can argue with. A spinner isn't.

---

## SHOT 6 — The two buttons
**[6:20 – 7:00] · Tab B · panel open**

▶ **DO**
1. Click **Save** — the left button. **Not** Save & run.
2. **Stop. Let the buttons change.** Point at them.

🎙 **SAY**

> Small thing, worth ten seconds. I just saved. Watch the buttons.
>
> Save has gone grey, and now reads "Saved" — there's nothing left to save. And the other button
> changed from "save and run" to just "Run". It knows what's on my screen is already what's on disk.

▶ **DO**
3. Click **Run**. The result appears in about a second and a half.
4. Point at the banner above the results.

🎙 **SAY**

> And there it is. About a second and a half, on the real pipeline — same optimizer, same maths as
> the recorded scenarios.
>
> And it's labelled: custom scenario, not a recorded benchmark result. I built this one, so it
> doesn't get to sit next to the four official numbers. That label is the point.

---

## SHOT 7 — "Why can't we just remove a warehouse?"
**[7:00 – 7:55] · Tab B**

▶ **DO**
1. Reopen the panel: **Scenario** dropdown → **"Custom dataset — the network…"**.
   *(That door opens the panel already scrolled to THE NETWORK.)*
2. Point at the two labelled groups.

🎙 **SAY**

> Now the second half. Everything so far changed the conditions. This changes the network itself —
> how many suppliers, factories, warehouses, customers.
>
> This came from one sentence the sponsor said: why can't we just remove a warehouse? So, let's.

▶ **DO**
3. Set **Distribution centers** to `1`. *(It starts at 2.)*
4. Name it `one-warehouse`.
5. Click **Save & run**. Wait for the result, then point at the objective number.

🎙 **SAY**

> Two warehouses, down to one. And the plan gets cheaper. Eighty-one thousand six-six-three, against
> eighty-one thousand seven-eight-nine.
>
> And the fill rate doesn't move. Not "barely" — identical, to the decimal place. Same service, less
> money.
>
> Which, taken at face value, says: close a warehouse, you're better off. Hold that thought.

---

## SHOT 8 — 🔴 Type a zero
**[7:55 – 9:35] · Tab B · THE most important shot**

▶ **DO**
1. Reopen the panel — **"Custom dataset — the network…"**.
2. Type any name, for example `zero-test`.
3. Set **Distribution centers** to **`0`**.
4. **Do not run it.** Wait for the amber block to appear *(about a third of a second)*.
5. Let it sit on screen for a full three seconds before you say anything.

🎙 **SAY**

> So let's push it. If one warehouse beats two — what about none?

▶ **DO**
6. Point at the amber block, then at the greyed-out run button.

🎙 **SAY**

> And here's the most useful thing in this entire tool. It won't run it.
>
> Read what it says. If it did run, it would tell you that closing every warehouse makes the network
> sixteen percent cheaper, with better service. Ninety-two percent of orders filled, against
> eighty-four.
>
> With zero warehouses. Where there is physically no route for a product to reach a single customer.

▶ **DO**
7. Slow right down. This is the line the video exists for.

🎙 **SAY**

> That is not a bug in the arithmetic. The arithmetic is right. It's a statement about how deep the
> model goes.
>
> Underneath, this optimizer moves volume between lanes — between routes. It has no concept of a
> place. A warehouse isn't a thing with a size and a limit. It's a label on the end of a line. So
> removing one costs nothing, and having none is the cheapest answer of all.
>
> Once you know that, other odd things make sense. It's why a setting called "warehouse throughput"
> does nothing at all. It's why a ten-week supplier outage doesn't move the answer. Those aren't
> separate problems — they're one problem, showing up three times.
>
> We only found it by building the thing that was asked for. And rather than quietly snap that zero
> back to one, the tool stops and says: this is a limit of the model, not a fact about your network.

---

## SHOT 9 — Close
**[9:35 – 10:20] · Tab B · leave the amber block on screen**

▶ **DO**
1. Do not click anything. Let the honesty message stay visible while you close.

🎙 **SAY**

> So that's the tool. It plans a factory network on one desktop machine, with nothing leaving the
> box. It beats the ordinary way on both cost and service. It shows you the data it used. And it lets
> you build your own scenario, reshape the network, and run the real thing in about a second.
>
> And when it reaches the edge of what it can honestly model, it tells you — instead of handing you a
> confident number that happens to be meaningless.
>
> That's the part I'd want you to remember. It's a prototype, not a finished product, and there's a
> list of things it doesn't do yet. But everything it does claim, it can show you the evidence for.
>
> Thanks for watching.

▶ **DO**
2. Stop recording — but count two seconds of silence first, so the cut isn't tight on your last word.

---

# Reference — every number you say out loud

If you fluff a number, this is the truth. All measured on this device.

| Where | Number |
|---|---:|
| Shortage scenario — ordinary way | **102,834.79** |
| Shortage scenario — optimizer | **95,445.45** *(−7.2%)* |
| Shortage scenario — fill rate, before → after | **79.87% → 82.47%** |
| The one sentence | 5 suppliers · 2 factories · 6 lines · 2 warehouses · 8 customers · 28 products · 52 weeks |
| The six tiles | 17 locations · 28 products · 30 lanes · 52 weeks · 2,912 records · seed **12345** |
| The shortage itself | 2 lanes from one supplier → **zero for 10 weeks** (periods 18–27), lead times triple |
| Demand level, baseline → yours | **44 → 52** |
| Baseline network (2 warehouses) | **81,789.36** at **83.66%** fill |
| One warehouse | **81,663.11** at **83.66%** fill — *identical service* |
| Zero warehouses *(refused)* | **68,565.25** at **92.01%** fill — 16% cheaper, better service |
| A custom run | ~**1.2 s**; the save itself 0.04–0.07 s |

---

# If something goes wrong mid-take

| What you see | What to do |
|---|---|
| **"Build your own" is missing from the dropdown** | You are on **Tab A** (`?replay=true`). Building needs the live system — switch to Tab B. |
| **The panel says "Failed to fetch"** | The API is down. Stop recording. `docker compose ps`, then `make up`. |
| **A control or section isn't there** | Cached build. `Ctrl+Shift+R`, then restart the shot. |
| **"A scenario named … already exists"** | That name is already on the box from an earlier take. Use **Delete all** in the panel, or pick a new name. |
| **The zero-warehouse message doesn't appear** | Give it a moment — the check is debounced by about a third of a second. If it still doesn't, confirm the field really contains `0` and is not just empty. |
| **You fluff a line** | Stop talking. Count three seconds in silence. Start that sentence again from the beginning. The silence gives you a clean cut point in OBS. |

---

# Notes on delivery

- **The numbers are the punchline, so slow down for them.** Say "eighty-one thousand six-six-three",
  not "eighty-one thousand, six hundred and sixty-three point one one". Digits read out are much
  easier to follow than long spoken numerals.
- **Shot 8 is the reason this video exists.** Everything before it is setup. Take the three-second
  pause before you speak, and do not rush the last paragraph.
- **Never say "the system thinks" or "the AI decided".** It's an optimizer — it computes. The
  language model only narrates. Saying otherwise undoes the honesty the whole demo is built on.
- **Don't call anything you build a benchmark result.** The four recorded numbers are 81,789.36 /
  95,445.45 / 94,165.36 / 2,521,615.07. Nothing made in the panel is one of them.
- If you want a safety net, record **Shot 8 twice** — once as scripted, once slower. Pick in the edit.

---

*Written 2026-08-26 for the recording Ryan asked for at that day's demo. Every figure is cross-checked
against [`DEMO_GUIDE.md`](DEMO_GUIDE.md), `benchmark/suite-summary.md`, and the two captured payloads
the replay actually serves. The modelling limit narrated in Shot 8 is written up in full at
[`iteration-docs/Modelling_Finding_The_Optimizer_Has_No_Node.md`](iteration-docs/Modelling_Finding_The_Optimizer_Has_No_Node.md).*
