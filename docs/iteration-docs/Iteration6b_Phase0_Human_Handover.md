# Iteration 6b, Phase 0 — the two items that need a human

**From:** Ishan (AI Intern) / agent session, 2026-08-21
**Status:** 🔴 **OPEN. Both items are unstarted and neither can be done from an agent session.**
**Why this document exists:** Phase 0's definition of done includes two items an agent cannot
legitimately mark complete. They are written up here with everything needed to do them quickly, so
they do not quietly become the thing that got skipped.

**Deadline reality:** the Ryan demo is **Wednesday 2026-08-26**. Both items below should be done
**this weekend (Sat 22 – Sun 23)**, not Tuesday night. Together they are about **80 minutes**.

---

## Item 1 — Record the Option E walkthrough *(~20 minutes)*

### Why a recording and not a replay build

Options A (results), C (dataset) and D (chat) each have a real GPU-free replay path. **Option E — the
custom scenario, the entire subject of Wednesday's meeting — has none.** The dropdown entry is
deliberately hidden in `?replay=true` ([`web/src/App.tsx:447`](../../web/src/App.tsx#L447)), correctly,
because building a scenario needs the API.

NVML has now detached from these containers **four times** (2026-07-10, 2026-07-30, 2026-08-20, and
again **2026-08-21** — see the journal entry for today; the `api` container had been up only 19 hours
when it went stale again). So the failure is not hypothetical: the box wobbles Wednesday morning and
the one thing Ryan came to see cannot be shown at all.

Building a true replay path for Option E is **UI work, not a capture** — the panel makes several round
trips (settings → preview → save → run → delete) and each needs a recorded response plus a read-only
mode. That is half a day. **A screen recording costs twenty minutes and covers the same failure**,
which is *"the box is down and I still need to show Ryan what this does."* A fallback does not have to
be interactive; it has to exist. This was a deliberate timeline decision, recorded in the plan under
§Deferred so the next person knows it was not an oversight.

### Where to record from

🔴 **Record on your laptop, not on the box.** This session confirmed the GB10 has no graphical session
(`XDG_SESSION_TYPE=tty`, no `DISPLAY`) and no `ffmpeg`. Follow the **Remote Access** section of
[`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) (SSH local port-forward keeps the `localhost:8081` URLs working),
then record the browser window with whatever your laptop already has — QuickTime, OBS, Win+Alt+R.

**Before you hit record:**

1. `curl -s localhost:8080/health` → must read **`gpu_visible:true`**. If not:
   `docker compose up -d --no-deps --force-recreate api`, then re-check.
2. Hard-reload the browser (Ctrl/Cmd+Shift+R). A cached build is the #1 cause of "the entry is
   missing".
3. Delete any leftover `custom-*` scenarios so the saved list starts clean.
4. Window at 1920×1080 if you can. Zoom the browser to ~110% — the amber honesty blocks are the point
   of the recording and they need to be legible when played back on a projector.
5. **Narrate it.** A silent screen capture loses the honesty beats, which are the most valuable part.
   Talk over it exactly as you would live.

### Shot list — follow Option E's five-step talk track verbatim

The full script is [`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) **Option E** (lines 619–800). Do not
improvise a shorter version; the two honesty beats are the reason this recording is worth having.

| # | Beat | Exactly what to do | Must be visible on screen |
|---|---|---|---|
| 1 | The dropdown | Open **Scenario** on the results screen. Show all three groups | The fifth entry, **"Custom scenario…"** |
| 2 | The eight controls | Open the panel. Pause on the grouped controls | The panel opens *beside* the view, not over it |
| 3 | Name + one change | Type `q3-surge`. Set **Demand level** `44 → 52` | **"Will be saved as `custom-q3-surge`"**, **WHAT YOU CHANGED (1)**, and the estimate *with its per-step basis lines* |
| 4 | Save & run | Click **Save & run** | The **CUSTOM SCENARIO · NOT A RECORDED BENCHMARK RESULT** banner, `Winner: Classical`, PPO/Rag greyed, `PPO outcome: not_evaluated` |
| 5 | The run opt-ins | Point at **"A custom run will include:"** | Both tick boxes with their costs (**+~2.7 s**, **+~20 s**) |
| 6 | 🔴 **Honesty beat 1** | **"Show all 59 settings"** → scroll to the boxed section | The heading *"recorded in the dataset, not read by the optimizer"* and **`capacity.dc_throughput_units_per_period`** tagged **"no effect on the result"** |
| 7 | 🔴 **Honesty beat 2** | Reopen panel, tick **Lane disruption**: `inbound_raw`, count `2`, start `18`, duration `10`, multiplier `0` | The amber **"This disruption will not change the answer"** block, *before* running. Then run it and show the objective come back at **81,789.36** — baseline exactly |
| 8 | Delete, both ways | Delete via the button beside the dropdown, then via the panel's saved list | The confirm prompt, and the name gone from the dropdown |

**Optional, worth 30 extra seconds:** with `custom-q3-surge` selected, click **View the dataset** to
show the network map and *"What makes this scenario different"* working on a custom scenario.

### Where to put the file

- **Name it** `iteration6a-option-e-walkthrough.mp4`.
- **If it compresses under ~25 MB:** commit it to
  `docs/iteration-docs/recordings/`. There is no git-lfs here and `.git` is currently only 17 MB, so
  keep it small. 1280×720 is plenty.
- **If it is larger:** do **not** commit it. Put it on the box at
  `/home/ishan/projects/Helix-AI-Jumpstart-Service-/docs/iteration-docs/recordings/` (add the folder
  to `.gitignore`) **and** keep a second copy off the box — 🔴 the internship ends **Friday
  2026-08-28**, and a fallback that lives only in a home directory nobody else opens is not a
  fallback.
- Either way, **add one line to `DEMO_GUIDE.md` Option E** pointing at it, so a cold reader finds it
  under "If something goes wrong".

### How to know it is done

Play it back **with the stack down** (`docker compose stop`) on a machine that cannot reach the box.
If you can talk Ryan through the custom scenario from the video alone, Phase 0's real objective is met.

> **Note on the DoD wording.** The plan's Phase 0 DoD says the fallback should be *"verified with the
> API blocked"* — that phrasing was written for a replay build, where blocking the API is the actual
> test. A video file has no API dependency, so the equivalent check is the playback-with-the-box-down
> test above. Flagging the difference rather than silently reinterpreting it.

---

## Item 2 — Read the Option E talk track out loud, end to end, once *(~60 minutes)*

### Why this is still open

🔴 **This has been carried as a definition-of-done item since Iteration 3 and has never once been
closed.** It has survived four iterations. It is the cheapest quality check in the whole project and
it is the one that keeps getting deferred.

Reading aloud finds a specific class of defect that no test and no browser check can: a sentence that
is accurate on the page but unsayable in a meeting, a beat that needs a number you do not have to
hand, a transition that assumes a click you did not make, and a claim that sounds stronger out loud
than the evidence supports.

### How to do it

Sit with [`../DEMO_GUIDE.md`](../DEMO_GUIDE.md) **Option E** (lines 619–800) open **and the live stack
in front of you**, and actually say every *"Say:"* block out loud while doing the clicks. Not a
skim — out loud, in order, once through without stopping.

**Keep a pen. Write down every place where:**

- you could not say the sentence as written without rephrasing it;
- you needed a number that is not on the screen or in the guide;
- the click you had to make was not the click the guide implies;
- what you said out loud overclaimed what the prototype actually does;
- Ryan would obviously interrupt with a question the guide does not answer.

**Then fix the guide in the same sitting** and note it in the journal. A list of problems you did not
fix is not a closed item.

### 🔴 The one thing to listen for hardest

**Honesty beat 2, step 7.** Out loud, the line *"two supplier lanes go to zero for ten weeks and the
answer does not move"* has to land as *"the model cannot see this"* and **never** as *"the network
absorbed it."* If it can be misheard as resilience, rewrite it until it cannot. That sentence is now
directly connected to the biggest finding of the week —
[`Modelling_Finding_The_Optimizer_Has_No_Node.md`](Modelling_Finding_The_Optimizer_Has_No_Node.md) —
and Wednesday's pitch rests on getting it right.

### When Phase 4 comes round

Phase 4's DoD requires reading the talk track aloud **again**, with the 6b material in it. This
sitting is not that one. Doing this one now is what makes that one quick.

---

## Checklist

- [ ] **Item 1** — Option E walkthrough recorded, narrated, stored, linked from `DEMO_GUIDE.md`,
      and played back with the stack down
- [ ] **Item 2** — Option E talk track read aloud end to end, problems written down **and fixed**,
      journal updated

Neither box is ticked by an agent. When they are done, say so and the Phase 0 DoD closes.

---

*Iteration 6b, Phase 0. Written 2026-08-21 on `feat/iteration6b-custom-dataset`. Plan:
[`../Iteration6b_Plan_of_Action.md`](../Iteration6b_Plan_of_Action.md) §0.2, §5 Phase 0.*
