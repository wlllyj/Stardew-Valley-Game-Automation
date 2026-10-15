r"""task-92 对抗脚本（第二批）：窗口口径的两条 fail-open 补测。

C7b：窗口里有一株**浇过水的死苗**（farm.dryDeadCrops=0）+ 活苗都浇好 ⇒ 收尾理由是 no_work，
     死苗还杵在地里，但 `dry_dead=0` ⇒ 新闸门抓不到 ⇒ 工具会不会照样 VERIFIED？
C8b：干活的**活苗在观测窗口外**（窗口只剩一格空耕地）+ farm 证据不可用（complete=false）
     ⇒ 窗口 dry=0 ⇒ watered_outdoor=true ⇒ 会不会 no_work + VERIFIED（**不需要任何谎报**）？
用法：`python scratch/_t92_adv2.py`
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t92_adv import VR, TV, TL, add, run_day, brief, as_ledger, HideFakeWorld  # noqa: E402


def main():
    print("=" * 78)
    print("C7b  窗口里一株『浇过水的死苗』（dry_dead=0）+ 活苗都浇好 ⇒ 死苗还在，理由却是 no_work")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
    add(w, (60, 10), dead=True, watered=True)      # 死苗已浇 ⇒ Mod 的 dryDeadCrops = 0
    add(w, (61, 10), dead=False, watered=True)     # 活苗也浇好
    w.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 0, "dryDeadCrops": 0,
              "deadCrops": 1, "unwateredCrops": 0, "hoeDirt": 2, "dryTiles": []}
    run, rep, end = brief("C7b", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("C8b  干活苗在窗口外 + 窗口还剩一格空耕地 + farm 证据不可用（无谎报）")
    w = HideFakeWorld({(63, 12)}, weeds=0, seeds=0, money=0)
    add(w, (63, 12), dead=False, watered=False)    # 真·没浇的活苗（被窗口藏起来）
    add(w, (64, 12), dead=False, watered=False)
    w.crops.pop((64, 12))                          # 只留一格空耕地，让窗口覆盖 1 格
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    run, rep, end = brief("C8b", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("C8c  同 C8b 但 farm 块整个缺失（旧 Mod 形态）")
    w = HideFakeWorld({(63, 12)}, weeds=0, seeds=0, money=0)
    add(w, (63, 12), dead=False, watered=False)
    add(w, (64, 12), dead=False, watered=False)
    w.crops.pop((64, 12))
    w.farm = None
    run, rep, end = brief("C8c", *run_day(w))
    as_ledger(run, end)

    print("\nALL DONE")


if __name__ == "__main__":
    main()
