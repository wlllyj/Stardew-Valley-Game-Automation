r"""task-97 C①的边界：把"部分可用证据"钉到最小触发条件。

* C1c  dryCrops 缺失 + ripeCrops=2      ⇒ 期望 keep_working（守卫拿 ripe 否决）
* C1d  dryCrops 与 ripeCrops 都缺失      ⇒ 期望 fail-closed（`_farm_totals` 返回 None）
* C1e  dryCrops=0 + ripeCrops=0（完整证据）⇒ 对照：真的没活 ⇒ no_work+VERIFIED 是**正确**的

用法：`python scratch/_t97_c2.py`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t97_c import case, hidden_live_dry  # noqa: E402


def main():
    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": True, "crops": 2, "ripeCrops": 2}
    case("C1c dry 缺 + ripe=2", w, note="期望：ripe>0 ⇒ 守卫 keep_working ⇒ stuck、不 VERIFIED")

    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": True, "crops": 2}
    case("C1d dry 与 ripe 都缺", w, note="期望：`_farm_totals` 返回 None ⇒ fail-closed")

    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 0, "ripeCrops": 0}
    case("C1e 完整证据 dry=0/ripe=0", w, note="对照：gardens 真没活 ⇒ no_work+VERIFIED 正确")

    print("\nALL DONE")


if __name__ == "__main__":
    main()
