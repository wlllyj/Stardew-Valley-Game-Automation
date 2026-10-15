r"""task-100 B/C 段：复验 task-99（`6a6da70`，`_farm_totals` 在 `dryCrops` 缺失时改 `return None`）。

全部用**真代码**（真 FarmWorker + 真 LongRun + 真 `tools/verify-run3.py` 在进程内），只写 scratch/。

B 段（防回归，必须仍 PASS）：
  C1/C1b  我的 C1 反例（`complete=true` + **dryCrops 缺失** + `ripeCrops=0` + 窗外真·没浇活苗）
  C6c     farm 证据不可用（`complete=false`）
  C6d     `farm=None` ⇒ NIT-6 之后 = 证据不可用（obs 发 `{}`）
  C8b/C8c 窗外真·没浇活苗 + 证据不可用（task-92 的两条 fail-open 原形）

C 段（朝新修法进攻）：
  P1  正对照：证据**可用**且说还有 2 格干 ⇒ 守卫继续干、不许 VERIFIED（别把可用证据也关了）
  P2  正对照：`dryCrops=0` 真有值 + 活苗都浇好 ⇒ 该正常 no_work + VERIFIED
  P3  畸形值：`dryCrops` 为 `"0"` / `"abc"` / `-1` / 显式 `None` ⇒ 是否 fail-closed
  P4  Lead 提示①：`dryCrops` 缺失 + `ripeCrops>0`（窗内可收 / 窗外藏着）⇒ 有没有形态能骗到 VERIFIED
  N3  NIT-3 实测：窗口 `crops>0` 但全是死苗 + 证据不可用 ⇒ 是否产生假绿

用法：`python scratch/_t100_b.py`
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t92_adv import TL, add, as_ledger, brief, run_day, HideFakeWorld  # noqa: E402

HID = (63, 12)      # 被 400 格窗口藏起来的格子
VIS = (62, 12)      # 窗口里看得见的格子


def hidden_live_dry(seeds=0, money=0, till=True, vis_watered=True):
    """窗外一株真·没浇的活苗 + 窗内一株活苗（默认浇好）。"""
    w = HideFakeWorld({HID}, weeds=0, seeds=seeds, money=money)
    add(w, HID, dead=False, watered=False)
    add(w, VIS, dead=False, watered=vis_watered)
    if not till:
        w.tillable = set()
    return w


def partial_farm(**over):
    """`complete=true` 但**没有 dryCrops**（<0.7.22 的 Mod 形态，task-97 C1）。"""
    base = {"loaded": True, "complete": True, "crops": 2, "ripeCrops": 0,
            "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 1, "hoeDirt": 2}
    base.update(over)
    return base


def case(tag, w, note=""):
    print("\n" + "=" * 78)
    print(f"{tag}  {note}")
    try:
        run, rep, end = run_day(w)
    except Exception as exc:
        print(f"  !! 跑一天就抛异常：{type(exc).__name__}: {exc}")
        print("     " + traceback.format_exc().strip().splitlines()[-1])
        return None
    brief(tag, run, rep, end)
    try:
        as_ledger(run, end)
    except Exception as exc:
        print(f"  [工具] 抛异常：{type(exc).__name__}: {exc}")
    return rep


def main():
    print("################ B 段：C1 反例复跑（期望 FAIL→PASS）################")
    w = hidden_live_dry(till=False)
    w.farm = partial_farm()
    case("B/C1", w, "dryCrops 缺失 + ripeCrops=0 + 无耕地（旧代码：no_work+VERIFIED）")
    w = hidden_live_dry()
    w.farm = partial_farm()
    case("B/C1b", w, "同上但保留可耕地")

    print("\n################ B 段：task-92 防回归 ################")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, (61, 10), dead=True, watered=False)
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    case("B/C6c", w, "farm 证据不可用（complete=false）")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, (61, 10), dead=True, watered=False)
    w.farm = None
    case("B/C6d", w, "farm=None ⇒ NIT-6 后 = 证据不可用（obs 发 {}）")

    for tag, farm in (("B/C8b", {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}),
                      ("B/C8c", None)):
        w = HideFakeWorld({(63, 12)}, weeds=0, seeds=0, money=0)
        add(w, (63, 12), dead=False, watered=False)
        add(w, (64, 12), dead=False, watered=False)
        w.crops.pop((64, 12))
        w.farm = farm
        case(tag, w, "窗外真·没浇活苗 + 证据不可用")

    print("\n################ C 段：正对照 ################")
    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 2, "ripeCrops": 0,
              "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 2, "hoeDirt": 2}
    case("C/P1", w, "证据可用且说还有 2 格干 ⇒ 守卫必须继续干、不许 VERIFIED")

    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w.tillable = set()
    add(w, VIS, dead=False, watered=True)
    w.farm = {"loaded": True, "complete": True, "crops": 1, "dryCrops": 0, "ripeCrops": 0,
              "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 0, "hoeDirt": 1}
    case("C/P2", w, "dryCrops=0 真有值 + 活苗都浇好 ⇒ 该 no_work + VERIFIED")

    print("\n################ C 段：畸形 dryCrops ################")
    for tag, val in (("P3a", "0"), ("P3b", "abc"), ("P3c", -1), ("P3d", None)):
        w = hidden_live_dry(till=False)
        f = partial_farm()
        f["dryCrops"] = val
        w.farm = f
        case(f"C/{tag}", w, f"dryCrops={val!r} + 窗外真·没浇活苗")

    print("\n################ C 段：dryCrops 缺失 + ripe>0（Lead 提示①）################")
    w = HideFakeWorld({HID}, weeds=0, seeds=0, money=0, scythe=True)
    add(w, HID, dead=False, watered=True, ripe=True)      # 窗外藏着熟作物
    add(w, VIS, dead=False, watered=True)
    w.farm = partial_farm(ripeCrops=1)
    case("C/P4a", w, "ripeCrops=1（藏在窗外）+ dryCrops 缺失")

    w = TL.FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
    w.tillable = set()
    add(w, VIS, dead=False, watered=True, ripe=True)      # 窗内可收
    w.farm = partial_farm(ripeCrops=1, crops=1)
    case("C/P4b", w, "ripeCrops=1（窗内可收）+ dryCrops 缺失")

    print("\n################ NIT-3 实测：窗口全死苗 + 证据不可用 ################")
    w = HideFakeWorld({HID}, weeds=0, seeds=100, money=500, scythe=True)
    add(w, HID, dead=False, watered=False)
    add(w, VIS, dead=True, watered=False)
    w.farm = {}
    case("N3", w, "窗口只有死苗（dry_dead>0, dry==0）+ 窗外真·没浇活苗 ⇒ 会不会出假绿")

    print("\nALL DONE")


if __name__ == "__main__":
    main()
