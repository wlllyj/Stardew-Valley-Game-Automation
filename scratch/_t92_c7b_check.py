r"""核对 C7b 的 `dead_crops=1` 到底是不是夹具工件：跑完那天后，世界里的死苗还在不在？

C7b 的输出里 `stages=[('clear_dead', 1, 0, 0)]`（脑认为清掉了），但 `dead_crops=1`（来自我静态写的 farm 块）。
如果世界层面那株死苗**已经没了** ⇒ `dead_crops=1` 是我夹具写死的陈旧场块，不是脑侧漏看 ⇒ C7b 不成立为缺陷。
用法：`T92_ROOT=<树> python scratch/_t92_c7b_check.py`
"""
import os
import sys

ROOT = os.environ["T92_ROOT"]
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL                                            # noqa: E402

DEAD, LIVE = (60, 10), (61, 10)

w = TL.FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
w.dirt.update({DEAD, LIVE})
w.crops[DEAD] = {"ripe": False, "watered": True, "dead": True}
w.crops[LIVE] = {"ripe": False, "watered": True, "dead": False}
# 场块**写死**：说还有 1 株死苗（模拟陈旧快照）
w.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 0, "dryDeadCrops": 0,
          "deadCrops": 1, "unwateredCrops": 0, "hoeDirt": 2, "dryTiles": []}

run = TL.make_run(w, target_days=1, max_days=1)
run.run()
rep = run.days[0]
end = [e for e in run.entries if e.get("event") == "day_end"][0]
print(f"ended_reason={rep.ended_reason!r}")
print(f"stages={[(s.get('stage'), s.get('ok'), s.get('leftover')) for s in end.get('stages', [])]}")
print(f"rep.dead_crops={rep.dead_crops}（来自静态 farm 块）")
print(f"世界里的死苗还在吗：{DEAD in w.crops}  crops={sorted(w.crops)}")
print(f"地里还有没有 dead=true 的格："
      f"{[t for t, c in w.crops.items() if c.get('dead')]}")
print("⇒ 结论：" + ("世界已清掉 ⇒ C7b 的 dead_crops=1 是夹具工件（陈旧场块），不是脑侧漏看"
                    if DEAD not in w.crops else "世界还留着死苗 ⇒ C7b 成立"))
