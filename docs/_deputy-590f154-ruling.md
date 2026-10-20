# Deputy Ruling — Commit `590f154` (release 0.7.50 freeze review)

**Reviewer:** deputy-lean (ruler-590f154)
**Subject:** `fix(space-relief): last-resort ship one non-protected stack when slot_relief_plan finds nothing`
**Scope:** 7 failing tests in `tests/test_longrun.py` (slot_relief / backpack-pressure family)
**Constraint under review:** AGENTS.md §5 数值安全 — selling MUST use a whitelist; **tools / weapons / seeds / building-materials / bars MUST NEVER be sold.**

---

## TL;DR Verdict

**0.7.50 CANNOT freeze `590f154` as-is. The commit MUST be fixed before freeze.**

- **6 of 7 tests are Class A (assertion-expiry):** they encode the OLD "stay blocked / never ship" invariant; the new "ship one non-protected surplus stack as last resort" behavior is CORRECT per AGENTS.md §5 (only loot/junk like Hay/Moss/Mystery was shipped — none of it protected). Their assertions must be updated *after* the code fix.
- **1 of 7 tests is Class B (real §5 violation):** `test_building_materials_never_sold_under_full_bag_pressure` — `590f154` ships **Fiber `(O)771`**, a building material, because Fiber is **missing from the new `_PROTECTED` set**. This is a genuine forbidden-sale leak and requires a CODE fix, not a test change.

The single Class-B leak is sufficient to block the freeze. The fix is small and mechanical (extend the never-sell protection to cover Fiber / all building materials), but it must happen before 0.7.50 is tagged.

---

## How the new code behaves

`git show 590f154` adds (a) method `_ship_one_stack_for_space` (longrun.py:6515) and (b) a call to it inside `_slot_relief` (longrun.py:6628-6632), reached only when `free_slots <= 0` AND `slot_relief_plan` found nothing sellable (`pre_plan.get("slots")` empty).

The last-resort ships the **smallest** non-protected stack, filtering by:
- `it.get("isTool")` → skip tools/weapons
- `_bare_item_id(qid) in _PROTECTED` → skip (`_PROTECTED` = `{"330","378","380","382","384","386","388","390"}`, longrun.py:6519)
- any token of `SEED_NAME_HINTS = ("seed","seeds","种子")` in `name.lower()` → skip (farmwork.py:1210)
- `bare in SLOT_RELIEF_NEVER_SELL_IDS` → skip (`{"334","335","336","337","338","787"}`, farmwork.py:1495)

**Gap:** `_PROTECTED` covers Clay/CopperOre/IronOre/Coal/GoldOre/IridiumOre/Wood/Stone only. It **omits Fiber `(O)771`** (and e.g. Radioactive `(O)909`, per the building-material list in the test comment at test_longrun.py:14407). Those are building materials that must never be sold, yet they are not excluded by any of the four filters above → they become last-resort shippable.

---

## Per-test ruling table

| # | Test | Class | Root cause | file:line evidence | Recommended action |
|---|------|-------|-----------|--------------------|--------------------|
| 1 | `test_day_end_traces_loot_lost_without_touching_checks` | **A** | Bag = 3 tools + Wheat Seeds + 8×Hay `(O)178`. Last-resort ships **Hay** (non-protected). Test asserts `free_slots_last == 0` (test_longrun.py:13667) and `ended_by != inventory_blocked` (13677); shipping Hay frees a slot, so those invariants are now outdated. No protected item leaks. | longrun.py:6628-6632 (call site), 6519 (`_PROTECTED` does not contain 178), test_longrun.py:13463-13473 (`_full_with_seeds`), 13667/13677 (failing asserts) | Update assertions to the new invariant: last-resort MAY ship non-protected Hay; assert `sell` event carries Hay qid, `free_slots_last >= 0`, protected (seeds/tools) never in `sell_calls`. Keep `loot_lost_steps == 0` and clear_gate trace checks. |
| 2 | `test_full_bag_with_many_ripe_ends_inventory_blocked_not_stuck` | **A** | Bag = 2 tools + 10×Mystery Thing `(O)999` (stack 99). Last-resort ships **Mystery Thing** (non-protected junk). Test asserts `ended_by == "inventory_blocked"` (10800), `len(w.crops) == 8` (10815), `inventory_blocked events == 1` (10816); freeing one slot can change the day's harvest outcome. No protected item leaks. | longrun.py:6628-6632, 6519 (999 not protected), test_longrun.py:10768-10790 (`_day` fills `(O)999`), 10815/10816 (failing asserts) | Update to the new invariant: assert last-resort shipped a non-protected `(O)999` stack, protected categories never sold, and re-tune the "honestly blocked" expectations (day may now free ≥1 slot). |
| 3 | `test_space_pressure_cannot_free_is_bounded_and_not_failure` | **A** | Bag = 3 tools + 9×Hay `(O)178`. Last-resort ships **Hay** → `run._slot_relief` returns `True` on the first loop iteration, breaking `assertFalse` (13584) and `assertEquals(worker.sell_calls, [])` (13585). Hay is non-protected → §5 compliant. | longrun.py:6628-6632, 6519, test_longrun.py:13443-13451 (`_full_unsellable`), 13583-13585 (failing asserts) | Update: assert that under a full Hay bag the last-resort ships exactly one non-protected Hay stack and `slot_relief` returns `True` once, then `False`; keep "not a failure" (`inventory_blocked_today == False`) check. |
| 4 | `test_no_known_surplus_stays_honestly_blocked` | **A** | Bag = tools + Hay/Moss/Mystery + Wheat Seeds. Last-resort ships **Mystery/Moss** (non-protected); Wheat Seeds skipped via `SEED_NAME_HINTS`. Test asserts `assertFalse(_slot_relief)` (12443) and `sell_calls == []` (12444); now returns `True` with one non-protected sell. No protected item leaks. | longrun.py:6628-6632, 6519, farmwork.py:1210 (seed hint), test_longrun.py:12319-12329 (`surplus=False` world), 12443-12444 (failing asserts) | Update: assert protected categories (seeds/tools) never sold, but one non-protected stack MAY be shipped as last resort; keep `inventory_blocked_today == True` and `reason` contains "没有可卖的盈余叠" checks. |
| 5 | `test_tools_seeds_and_upgrade_bars_are_never_sold` | **A** | Bag = Axe/Pickaxe, Wheat Seeds `(O)472`, 2×Copper Bar `(O)334`, Hay/Moss/Mystery. Last-resort ships **Mystery/Moss** (non-protected). Tools skipped (`isTool`), Seeds skipped (`SEED_NAME_HINTS`), **Copper Bar skipped via `SLOT_RELIEF_NEVER_SELL_IDS`** (farmwork.py:1495). The test's TITLE invariant (tools/seeds/bars never sold) HOLDS; only the over-strict "never sell ANYTHING" assertion `assertFalse(_slot_relief)` (12472) is outdated. | longrun.py:6519, 6628-6632, farmwork.py:1495/1210, test_longrun.py:12454-12473, 12472 (failing assert) | Update: relax "nothing is ever sold" to "protected categories never in `sell_calls`" — assert `sell_calls` qids ⊆ {Hay, Moss, Mystery} and never ⊆ {tools, seeds, bars}. Keep `inventory_blocked_today == True`. |
| 6 | `test_building_materials_never_sold_under_full_bag_pressure` | **B** | Bag = 3 tools + 9 building materials **including Fiber `(O)771`** (test_longrun.py:14424-14427), `free_slots == 0`. `slot_relief_plan` finds no sellable (all off whitelist) → no-plan branch → `_ship_one_stack_for_space` ships **Fiber 771** — the ONLY non-protected item in the bag. Fiber is a **building material**, explicitly in the §5 never-sell set (test_longrun.py:14407 lists "Fiber 771" among building materials). `assertEqual(worker.sell_calls, [])` (14479) FAILS because Fiber was shipped. **This is a real AGENTS.md §5 violation.** | longrun.py:6519 (`_PROTECTED` omits `771`), 6628-6632 (call site ships it), farmwork.py:1495 (`771` also absent from `SLOT_RELIEF_NEVER_SELL_IDS`), test_longrun.py:14423-14427 (`MATERIAL_ROWS` includes Fiber), 14471-14479 (failing asserts, esp. 14479) | **CODE FIX REQUIRED.** Add Fiber `771` (and audit Radioactive `909` + remaining building materials) to the never-sell protection consumed by `_ship_one_stack_for_space`. Best fix: stop hand-maintaining local `_PROTECTED`; reuse `SLOT_RELIEF_NEVER_SELL_IDS` / an authoritative building-material set so the two lists cannot drift. Then keep this test's `sell_calls == []` assertion. |
| 7 | `test_pressure_stuck_channel_carries_task237_fields` | **A** | Bag = 3 tools + 9×Hay `(O)178`. Last-resort ships **Hay** → `run._slot_relief` returns `True` on first iteration (13802 `assertFalse` loop fails); the `slot_relief` event's task-237 fields may also differ because the function returns early after shipping. Hay is non-protected → §5 compliant. | longrun.py:6628-6632, 6519, test_longrun.py:13728-13736 (`_full_unsellable`), 13801-13806 (failing asserts) | Update: assert the pressure-stuck path still emits the task-237 `slot_relief` note with `trigger="none"`/`reached=False`, AND that the last-resort MAY ship one non-protected Hay stack (so the loop's first call returns `True`). |

---

## Code-path trace for the Class-B leak (test 6)

1. `run._slot_relief(obs, rep)` called with `free_slots == 0`, `need == 0` (no crops in `_full(rows=MATERIAL_ROWS)`).
2. `space_pressure = True`; `slot_relief_plan(...)` returns no `slots` (every `MATERIAL_ROWS` qid is off the sellable whitelist) → `pre_plan.get("slots")` empty, `harvested_now` empty.
3. Enters the `else` (pressure) branch: `_note_slot_pressure_stuck(...)` (emits one `slot_relief` event, `trigger="none"`).
4. **New code (longrun.py:6629-6632):** `if int(free_slots) <= 0: _shipped = self._ship_one_stack_for_space(obs, rep)`.
5. `_ship_one_stack_for_space` (longrun.py:6515): iterates inventory. 8 of 9 materials are in `_PROTECTED` (skipped). **Fiber `(O)771` is not** in `_PROTECTED`, not a seed, not in `SLOT_RELIEF_NEVER_SELL_IDS` → becomes the sole candidate → `worker.sell(slot, whitelist=["(O)771"])` executes, Fiber removed from bag.
6. Returns `True` ⇒ `assertFalse(_slot_relief)` fails AND `sell_calls == []` fails. **Building material sold against §5.**

The same drift would leak **Radioactive `(O)909`** and any other building material absent from the local `_PROTECTED` copy in real play (not just in this test).

---

## Overall verdict (decisive)

**MUST fix `590f154` before 0.7.50 freeze — do NOT ship as-is, and do NOT "just update the tests."**

- The commit's *intent* (ship only non-protected surplus as a last resort) is sound and §5-compliant for 6 of the 7 tests.
- But the local `_PROTECTED` set (longrun.py:6519) is an incomplete, hand-maintained copy of the never-sell policy. It omits **Fiber `(O)771`** (and likely **Radioactive `(O)909`**), so the new last-resort path sells a **building material** — a hard AGENTS.md §5 violation proven by test 6.

**Required actions before freeze:**
1. **Code fix (blocking):** extend the never-sell protection used by `_ship_one_stack_for_space` to cover Fiber `771` and the full building-material set. Preferred: replace the local `_PROTECTED` with the authoritative set (`SLOT_RELIEF_NEVER_SELL_IDS` ∪ building-material ids) so the brain's two never-sell lists cannot drift apart again.
2. **Test updates (non-blocking, after fix):** convert the 6 Class-A tests' expired "never ship" assertions into "ship non-protected surplus as last resort, protected categories (tools/weapons/seeds/building-materials/bars) never" assertions, per the Recommended action column above.
3. Re-run `tests/test_longrun.py` after the fix; all 7 should pass (test 6 with `sell_calls == []` preserved).

**No protected-category leak occurs in tests 1-5 or 7** (only Hay/Moss/Mystery/junk, all non-protected, were shipped), so those regressions are purely assertion-expiry.
