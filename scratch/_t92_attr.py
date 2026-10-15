r"""task-92 归因实验：C8b（干作物在窗口外 + farm 证据不可用）在两棵树上是否都放行。

用法：`T92_ROOT=<树> python scratch/_t92_attr.py`
只打印两棵树都有的字段（不碰 task-84 新增属性），便于 pre/post 逐字对比。
"""
import importlib.util
import json
import os
import sys

ROOT = os.environ["T92_ROOT"]
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL                                            # noqa: E402

spec = importlib.util.spec_from_file_location(
    "_vr3_attr", os.path.join(ROOT, "tools", "verify-run3.py"))
VR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VR)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_verify_run3 as TV                                        # noqa: E402


class Hide(TL.FakeWorld):
    def __init__(self, hidden, **kw):
        super().__init__(**kw)
        self.hidden = set(hidden)

    def obs(self):
        o = super().obs()
        o["location"]["tiles"] = [t for t in o["location"]["tiles"]
                                  if tuple(t["tile"]) not in self.hidden]
        return o


def case(tag, world):
    run = TL.make_run(world, target_days=1, max_days=1)
    run.run()
    rep = run.days[0]
    end = [e for e in run.entries if e.get("event") == "day_end"][0]
    print(f"\n--- {tag} ---")
    print(f"ended_by={rep.ended_by!r}")
    print(f"ended_reason={rep.ended_reason!r}")
    print(f"verified={rep.verified}")
    print(f"checks={json.dumps(rep.checks, ensure_ascii=False, sort_keys=True)}")
    print(f"final_water={json.dumps(rep.final_water, ensure_ascii=False, sort_keys=True)}")
    print(f"ok_steps={rep.ok_steps} failed_steps={rep.failed_steps}")
    day = end["final"]["day"]
    rows = [TV.day_start(day, t=0.0), TV.sleep_ok(t=100.0), dict(end),
            TV.finish(code=0 if end.get("verified") else 1,
                      streak=1 if end.get("verified") else 0, days=1)]
    ok, s = VR.report(rows, target_days=1)
    print(f"[工具] ok={ok} verdict={s.get('verdict')} problems={json.dumps(s.get('problems'), ensure_ascii=False)}")


def main():
    print(f"ROOT={ROOT}")
    w = Hide({(63, 12)}, weeds=0, seeds=0, money=0)
    w.crops[(63, 12)] = {"ripe": False, "watered": False, "dead": False}
    w.dirt.add((63, 12))
    w.dirt.add((64, 12))                      # 窗口里留一格空耕地
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    case("C8b farm.complete=false", w)

    w = Hide({(63, 12)}, weeds=0, seeds=0, money=0)
    w.crops[(63, 12)] = {"ripe": False, "watered": False, "dead": False}
    w.dirt.add((63, 12))
    w.dirt.add((64, 12))
    w.farm = None
    case("C8c 没有 farm 块", w)

    w = Hide({(63, 12)}, weeds=0, seeds=0, money=0)
    w.crops[(63, 12)] = {"ripe": False, "watered": False, "dead": True}   # 谎报死苗（对照）
    w.dirt.add((63, 12))
    w.dirt.add((64, 12))
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    case("C6c 活苗谎报死苗 + complete=false", w)

    print("\nDONE")


if __name__ == "__main__":
    main()
