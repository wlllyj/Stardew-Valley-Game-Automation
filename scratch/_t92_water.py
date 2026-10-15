r"""task-92 反向验证（卡面第 2 条）：真死苗当活苗 ⇒ 会不会又去浇死苗。

自跑（不引用作者用例）：真 `FarmWorker` + `FakeWorld`，直接调 `worker.water(死苗格)`：
  * 死苗 ⇒ `code == "skipped"`、`failed` False、`attempted` False、**一个 `use_tool` 请求都不发**；
  * 活苗（没浇）⇒ 照常浇上（`code == "ok"`、世界 `watered=True`）；
  * `farm_dry_dead_crops` 三态（字段缺失/未 complete/有值）。
用法：`T92_ROOT=<树> python scratch/_t92_water.py`（pre 树会变红 ⇒ 证明改动真实生效）
"""
import json
import os
import sys

ROOT = os.environ["T92_ROOT"]
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL                                            # noqa: E402
from agentfarm.farmwork import FarmWorker                            # noqa: E402

DEAD, LIVE = (60, 10), (61, 10)


def world():
    w = TL.FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
    w.dirt.update({DEAD, LIVE})
    w.crops[DEAD] = {"ripe": False, "watered": False, "dead": True}
    w.crops[LIVE] = {"ripe": False, "watered": False, "dead": False}
    return w


def main():
    print(f"ROOT={ROOT}")
    w = world()
    worker = FarmWorker(TL.FakeClient(w), log=lambda *_: None, pause=lambda _s: None)
    obs = w.obs()
    before = {k: dict(v) for k, v in w.crops.items()}

    r = worker.water(DEAD)
    print(f"\n[死苗] code={r.code!r} failed={r.failed} attempted={r.attempted} "
          f"skipped={r.skipped} env_block={r.env_block} inconclusive={r.inconclusive}")
    print(f"[死苗] reason={r.reason!r}")
    print(f"[死苗] 世界变了吗：{'没变' if w.crops == before else '变了'}"
          f"  water_left={w.water_left}")

    r2 = worker.water(LIVE)
    print(f"\n[活苗] code={r2.code!r} reason={r2.reason!r}")
    print(f"[活苗] watered={w.crops[LIVE]['watered']} water_left={w.water_left}")

    import agentfarm.farmwork as FW
    fn = getattr(FW, "farm_dry_dead_crops", None)
    for tag, farm in (("无 farm 块", None),
                      ("complete=false", {"loaded": True, "complete": False,
                                          "crops": 1, "dryCrops": 1}),
                      ("缺 dryDeadCrops", {"loaded": True, "complete": True, "crops": 1,
                                           "dryCrops": 1, "deadCrops": 1}),
                      ("有值 dryDeadCrops=3", {"loaded": True, "complete": True, "crops": 4,
                                               "dryCrops": 1, "dryDeadCrops": 3})):
        w2 = world()
        o2 = w2.obs()
        if farm is not None:
            o2 = dict(o2)
            o2["farm"] = dict(farm)
        got = fn(o2) if fn else "（旧树：函数不存在）"
        print(f"[farm_dry_dead_crops] {tag:>20} ⇒ {got}")
    print("\nDONE")


if __name__ == "__main__":
    main()
