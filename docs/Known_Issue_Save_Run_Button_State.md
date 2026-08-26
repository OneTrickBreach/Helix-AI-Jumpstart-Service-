# Known issue — Save / Save & run button state in the custom panel

**From:** Ishan (AI Intern)
**Date:** 2026-08-26
**Status:** 🔴 **OPEN — the one piece of work outstanding on this project.** Found live, in front of
the sponsor, during the 2026-08-26 demo. Branch: `fix/custom-panel-save-run-state`.
**Severity:** Cosmetic-to-moderate. **No data is lost, no result is wrong, nothing is corrupted.**
The refusal is the storage layer behaving exactly as designed; the panel is asking it the wrong
question.
**Scope of fix:** **Frontend only.** Every backend piece this needs already exists and is already
tested.

---

## The symptom, as it happened

Building a custom scenario in the panel, then clicking **Save**, and *then* clicking **Save & run**,
produces:

> A scenario named 'custom-test1' already exists. Delete it first, or save under a different name.

The planner has done nothing wrong. They saved their work, then asked to run it. The panel treated
the second click as a brand-new save of a name that — because of their own first click — now exists.

**Reproduction, 15 seconds:**

1. Open the Scenario dropdown → **Build your own** → either door.
2. Type a name. Change any control.
3. Click **Save**. It succeeds: *"Saved as custom-test1."*
4. Click **Save & run**. It fails with the message above.

---

## Root cause

**The panel has no concept of "already saved".** There is no dirty-state tracking anywhere in
[`CustomScenarioPanel.tsx`](../web/src/custom/CustomScenarioPanel.tsx), so nothing distinguishes
*"this form has unsaved changes"* from *"this form is exactly what is already on disk."*

Two lines do the damage:

| Where | What it does | Why it bites |
|---|---|---|
| [`CustomScenarioPanel.tsx:192`](../web/src/custom/CustomScenarioPanel.tsx#L192) — `request()` | Builds the save body and **never sets `overwrite`** | Every save is a first save |
| [`CustomScenarioPanel.tsx:177`](../web/src/custom/CustomScenarioPanel.tsx#L177) — `canSave` | `Boolean(name.trim()) && validation.ok && !busy` | Never consults whether this exact state was already saved, so **both buttons stay fully enabled after a successful save** |

Downstream, the storage layer then does precisely what it promises:

```
store.save()            src/scenario/store.py:296   if already and not overwrite: raise ScenarioExists
```

🔴 **This is not a backend bug and the guard should not be removed.** `overwrite` is already plumbed
end to end, and the reason it defaults to `False` is written down in
[`src/api/pipeline.py:170-173`](../src/api/pipeline.py#L170-L173):

> *"Overwriting is explicit rather than implied: a silent overwrite of a scenario someone else on the
> box built is not a behaviour worth defaulting to (decision 14 — storage is box-global)."*

That decision is still correct. The fix must honour it, not undo it.

---

## The fix

### The state machine

| Form state | **Save** | Primary button | On click |
|---|---|---|---|
| **Dirty** — never saved, or edited since the last save | enabled | **Save & run** | save, then run |
| **Clean** — matches what was last saved from this panel | **disabled (greyed)** | **Run** | run only; no save call, so no collision is even possible |
| Any edit while Clean | re-enables | reverts to **Save & run** | — |

### The one subtlety that keeps decision 14 intact

Send `overwrite: true` **only when the target name is the one this panel session saved.** Track the
last-saved name in component state and compare. Then:

- Re-saving your own just-saved scenario after an edit → **overwrites silently.** Correct: it is
  yours, from seconds ago, in this sitting.
- Saving over a name you did *not* create in this session → **still refused**, exactly as today.
  Decision 14 is preserved, not weakened.

The guard's job simply narrows from *"protect every name"* to *"protect names this session did not
create."*

### Already in place — no backend work required

| Piece | Location | State |
|---|---|---|
| `overwrite` on the store | [`store.py:275`](../src/scenario/store.py#L275) | ✅ exists, tested |
| `overwrite` on the API request model | [`pipeline.py:177`](../src/api/pipeline.py#L177) | ✅ exists, wired at [`pipeline.py:416`](../src/api/pipeline.py#L416) |
| `overwrite` on the TypeScript request type | [`customApi.ts:48`](../web/src/lib/customApi.ts#L48) | ✅ exists, **never set by any caller** |
| `CustomScenarioConflict` error class | [`customApi.ts`](../web/src/lib/customApi.ts) | ✅ exists, already caught at [`CustomScenarioPanel.tsx:203`](../web/src/custom/CustomScenarioPanel.tsx#L203) |

The whole feature was built and then left unused by the one component that needed it.

---

## 🔴 Why every automated check passed

**638 pytest, 118 Vitest and 50 browser checks were green when this shipped.** They still are. None
of them failed, and none of them were wrong.

The tests cover *"saving works"* and *"saving a duplicate name is refused."* Both behaviours are
correct and both are asserted. What no test covers is **the sequence a person actually performs** —
Save, then Save & run — because every test saves once and then asserts the outcome.

This is the second time in three days that the same class of gap has surfaced:

| Date | What was missed | What the tests proved instead |
|---|---|---|
| 2026-08-24 | Every label said "scenario", so nobody could tell the custom **dataset** had been built | That the feature *worked* |
| **2026-08-26** | Save-then-run, the most obvious two-click sequence in the panel, errors | That each click *works in isolation* |

**The lesson, stated once:** this suite tests that features work. It does not test that a human
moving through them in a natural order has a coherent experience. A browser check that performs a
realistic multi-step session — rather than one action per test — would have caught both. That is the
single most valuable test-suite improvement available to whoever picks this up.

---

## Definition of done

- [ ] Dirty-state tracking in the panel; `Save` greys out when clean
- [ ] Primary button reads **Run** when clean, **Save & run** when dirty
- [ ] Editing any field after a save restores both buttons
- [ ] `overwrite: true` sent **only** for a name saved in this session
- [ ] A name saved in a *previous* session is still refused (decision 14 regression test)
- [ ] 🔴 A browser check that performs the **full realistic sequence**: build → Save → Run → edit →
      Save & run → delete
- [ ] `make test`, `make web-test`, `make web-check` green; `make bench-all` bit-identical
      (this touches no optimizer code, so all 12 objectives must not move)

---

*Found during the live sponsor demo, 2026-08-26. Everything else in the product was accepted as-is
at that meeting — see [`DEVELOPMENT_JOURNAL.md`](DEVELOPMENT_JOURNAL.md) and
[`handoff.md`](handoff.md).*
