r"""task-97 C 段：朝 task-96 的新修法（farm 证据不可用 ⇒ fail-closed）本身进攻。

全部用**真代码**（真 FarmWorker + 真 LongRun），只写 scratch/。
B 段复跑：把 task-92 的 C6d/C8c 用**真正不可用**的 farm 块重建（注意：task-96 把夹具的
`w.farm = None` 改成了"按世界状态自动生成 farm_scan()"，所以旧脚本的 C6d/C8c 已经不表示
"没有 farm 块"了 —— 这正是 Lead 要我查的"夹具是否掩盖了什么"）。
C 段进攻：部分可用证据 / 真没活的日子有界性 / 全死苗窗口 / 窗口与 farm 打架 / 畸形 complete。

用法：`python scratch/_t97_c.py`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _t92_adv import TL, add, as_ledger, brief, HideFakeWorld, run_day  # noqa: E402

HID = (63, 12)                              # 被 400 格窗口藏起来的格子
VIS = (62, 12)                              # 窗口里看得见的格子


class NoFarmWorld(HideFakeWorld):
    """连 `farm` 键都不发的旧桥（obs 里根本没有 farm）。"""

    def obs(self):
        o = super().obs()
        o.pop("farm", None)
        return o


def case(tag: str, w, note: str = ""):
    run, rep, end = brief(tag, *run_day(w))
    acts = getattr(run, "_actions", None)
    print(f"  有界性证据：entries={len(run.entries)} actions={acts} {note}")
    as_ledger(run, end)
    return run, rep, end


def hidden_live_dry(seeds: int = 0, money: int = 0, till: bool = True):
    """窗外一株真·没浇的活苗 + 窗内一株浇好的活苗（可选：把可耕地清空以隔离路径）。"""
    w = HideFakeWorld({HID}, weeds=0, seeds=seeds, money=money)
    add(w, HID, dead=False, watered=False)
    add(w, VIS, dead=False, watered=True)
    if not till:
        w.tillable = set()
    return w


def main():
    print("=" * 78)
    print("B1  task-92 C8c 重建：farm 块 = {} （旧 Mod/证据不可用）+ 窗外没浇的活苗")
    w = hidden_live_dry()
    w.farm = {}
    case("B1", w)

    print("\n" + "=" * 78)
    print("B2  task-92 C6d 重建：obs 里**没有** farm 键 + 窗外没浇的活苗")
    w = NoFarmWorld({HID}, weeds=0, seeds=0, money=0)
    add(w, HID, dead=False, watered=False)
    add(w, VIS, dead=False, watered=True)
    case("B2", w)

    print("\n" + "=" * 78)
    print("C1  部分可用证据：complete=true、**dryCrops 缺失**、ripeCrops=0 + 窗外没浇的活苗（无耕地）")
    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": True, "crops": 2, "ripeCrops": 0,
              "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 1, "hoeDirt": 2}
    case("C1", w, note="期望：证据不可用 ⇒ 不许 no_work/VERIFIED")

    print("\n" + "=" * 78)
    print("C1b 同 C1 但保留可耕地（看会不会靠 till 干活把一天做完、末尾仍 no_work+VERIFIED）")
    w = hidden_live_dry()
    w.farm = {"loaded": True, "complete": True, "crops": 2, "ripeCrops": 0,
              "deadCrops": 0, "dryDeadCrops": 0, "unwateredCrops": 1, "hoeDirt": 2}
    case("C1b", w)

    print("\n" + "=" * 78)
    print("C2  真的没活 + farm 证据不可用（`{}`）+ 空世界 ⇒ 会不会死循环烧整天？（期望：有界、不许 VERIFIED）")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w.tillable = set()
    w.farm = {}
    case("C2", w, note="重点看 entries/actions 是否有界、ended_by 是否为 stuck")

    print("\n" + "=" * 78)
    print("C3  窗口里**只有死苗**（dry_dead>0, dry==0）+ farm 证据不可用 + 窗外没浇的活苗")
    w = HideFakeWorld({HID}, weeds=0, seeds=100, money=500, scythe=True)
    add(w, HID, dead=False, watered=False)
    add(w, VIS, dead=True, watered=False)
    w.farm = {}
    case("C3", w, note="看点：watered_outdoor 该不该是 True（活苗的干无法证明）")

    print("\n" + "=" * 78)
    print("C4  窗口 dry==0（看得见的活苗都浇了）但 farm 口径 dryCrops=2（两边打架）")
    w = HiddenFarm2()
    case("C4", w, note="期望：farm 口径优先，不许 VERIFIED")

    print("\n" + "=" * 78)
    print("C5  畸形 complete 值：complete='true'（字符串）+ dryCrops=0 + 窗外没浇的活苗")
    w = hidden_live_dry(till=False)
    w.farm = {"loaded": True, "complete": "true", "crops": 2, "dryCrops": 0, "ripeCrops": 0}
    case("C5", w, note="期望：fail-closed（不是 True ⇒ 证据不可用）")

    print("\n" + "=" * 78)
    print("C6  loaded=False（未加载）+ dryCrops=0 + 窗外没浇的活苗")
    w = hidden_live_dry(till=False)
    w.farm = {"loaded": False, "complete": True, "crops": 0, "dryCrops": 0, "ripeCrops": 0}
    case("C6", w, note="期望：fail-closed")

    print("\nALL DONE")


class HiddenFarm2(HideFakeWorld):
    """窗口里活苗都浇好，但 farm 口径说还有 2 格干作物（窗口/农场打架）。"""

    def __init__(self, **kw):
        super().__init__({HID}, weeds=0, seeds=0, money=0, **kw)
        add(self, HID, dead=False, watered=False)
        add(self, VIS, dead=False, watered=True)
        self.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 2,
                     "ripeCrops": 0, "deadCrops": 0, "dryDeadCrops": 0,
                     "unwateredCrops": 2, "hoeDirt": 2}


if __name__ == "__main__":
    main()
