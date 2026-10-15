r"""task-92 对抗脚本：死苗口径（task-84 / 0.7.27）会不会变成新的洗白通道。

三段：
  A. 真代码整天跑（真 FarmWorker + 真 LongRun，`T92_ROOT` 可指向别的树以证明会变红）
     C6a farm 口径真值（活苗被谎报 dead）    C6b farm 口径也被伪造
     C6c farm 证据不可用（complete=false）    C6d 完全没有 farm 块（旧 Mod / 窗口口径）
     C7  窗口里有死苗 + 活苗都浇了            C8  干作物在窗口外 + farm 证据不可用
  B. 把 A 段真实产物做成账本喂 `tools/verify-run3.py`（进程内 report()）看工具判什么
  C. 账本级直接伪造（dead_crops/dry_dead 的三种形态）
用法：`python scratch/_t92_adv.py`
"""
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.environ.get("T92_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "tests"), os.path.join(ROOT, "brain"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL                    # noqa: E402
import test_verify_run3 as TV                # noqa: E402


def _vr():
    spec = importlib.util.spec_from_file_location(
        "_vr3_readonly_for_t92", os.path.join(ROOT, "tools", "verify-run3.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VR = _vr()
LIVE, DEAD = (61, 10), (60, 10)


def add(w, tile, *, dead, watered=False, ripe=False):
    w.crops[tile] = {"ripe": ripe, "watered": watered, "dead": dead}
    w.dirt.add(tile)


class HideFakeWorld(TL.FakeWorld):
    """模仿 400 格观测窗口：把某些格子从 `location.tiles[]` 里藏起来（但世界真有这株）。"""

    def __init__(self, hidden, **kw):
        super().__init__(**kw)
        self.hidden = set(hidden)

    def obs(self):
        o = super().obs()
        o["location"]["tiles"] = [t for t in o["location"]["tiles"]
                                  if tuple(t["tile"]) not in self.hidden]
        return o


def run_day(w):
    run = TL.make_run(w, target_days=1, max_days=1)
    run.run()
    rep = run.days[0]
    ends = [e for e in run.entries if e.get("event") == "day_end"]
    return run, rep, (ends[0] if ends else None)


def brief(tag, run, rep, end):
    print(f"\n--- {tag} ---")
    print(f"ended_by={rep.ended_by!r} ended_reason={rep.ended_reason!r}")
    print(f"verified={rep.verified} checks={json.dumps(rep.checks, ensure_ascii=False)}")
    print(f"final_water={json.dumps(rep.final_water, ensure_ascii=False)}")
    print(f"dead_crops={rep.dead_crops}/{rep.dead_crops_status} "
          f"dry_dead={rep.dry_dead}/{rep.dry_dead_status} gave_up={rep.gave_up_tiles}")
    print(f"ok_steps={rep.ok_steps} failed_steps={rep.failed_steps} stages="
          f"{[(s.get('stage'), s.get('ok'), s.get('leftover'), s.get('encircled')) for s in (end or {}).get('stages', [])]}")
    return run, rep, end


def as_ledger(run, end):
    """把真代码一天做成一本小账本，喂工具。"""
    if not end:
        return None
    day = end["final"]["day"]
    nd = end.get("day_after") or [day[0], day[1], day[2] + 1]
    rows = [TV.day_start(day, t=0.0),
            TV.sleep_ok(t=100.0, reason=end.get("ended_reason") or "night:到点了"),
            dict(end),
            TV.finish(code=0 if end.get("verified") else 1, streak=1 if end.get("verified") else 0,
                      days=1)]
    ok, summary = VR.report(rows, target_days=1)
    print(f"  [工具] ok={ok} verdict={summary.get('verdict')} "
          f"problems={json.dumps(summary.get('problems'), ensure_ascii=False)}")
    print(f"  [工具] infos={json.dumps(summary.get('infos'), ensure_ascii=False)}")
    return ok, summary


def main():
    print("=" * 78)
    print("A/C6a  farm 口径是真值：活苗被谎报 dead，但 Mod 说 dryCrops=1")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, LIVE, dead=True, watered=False)
    w.farm = {"loaded": True, "complete": True, "crops": 1, "dryCrops": 1, "dryDeadCrops": 0,
              "deadCrops": 0, "unwateredCrops": 1, "hoeDirt": 1}
    run, rep, end = brief("C6a", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("A/C6b  farm 口径也被伪造（dryCrops=0 / dryDeadCrops=1 / deadCrops=1）")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, LIVE, dead=True, watered=False)
    w.farm = {"loaded": True, "complete": True, "crops": 1, "dryCrops": 0, "dryDeadCrops": 1,
              "deadCrops": 1, "unwateredCrops": 1, "hoeDirt": 1}
    run, rep, end = brief("C6b", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("A/C6c  farm 证据不可用（complete=false）⇒ 走窗口口径")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, LIVE, dead=True, watered=False)
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    run, rep, end = brief("C6c", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("A/C6d  完全没有 farm 块（旧 Mod 形态）⇒ 纯窗口口径")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    add(w, LIVE, dead=True, watered=False)
    w.farm = None
    run, rep, end = brief("C6d", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("A/C7  窗口里一株死苗（没浇）+ 活苗都浇好了 ⇒ 收尾理由不许是 no_work")
    w = TL.FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
    add(w, DEAD, dead=True, watered=False)
    add(w, LIVE, dead=False, watered=True)
    w.farm = {"loaded": True, "complete": True, "crops": 2, "dryCrops": 0, "dryDeadCrops": 1,
              "deadCrops": 1, "unwateredCrops": 0, "hoeDirt": 2}
    run, rep, end = brief("C7", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("A/C8  干活苗在观测窗口外（看不见）+ farm 证据不可用 ⇒ 会不会判 no_work+VERIFIED")
    w = HideFakeWorld({(63, 12)}, weeds=0, seeds=0, money=0)
    add(w, (63, 12), dead=False, watered=False)
    w.farm = {"loaded": True, "complete": False, "crops": 1, "dryCrops": 1}
    run, rep, end = brief("C8", *run_day(w))
    as_ledger(run, end)

    print("\n" + "=" * 78)
    print("C 账本级伪造")
    for tag, extra in (
        ("F1 dry_dead=0 + dead_crops=1 + watered_outdoor=true(window,crops=0) + no_work",
         {"dead_crops": 1, "dead_crops_status": "ok", "dry_dead": 0, "dry_dead_status": "ok",
          "gave_up_tiles": []}),
        ("F2 dry_dead=1 + no_work ⇒ 新闸门应判红",
         {"dead_crops": 1, "dead_crops_status": "ok", "dry_dead": 1, "dry_dead_status": "ok",
          "gave_up_tiles": []}),
        ("F3 旧账本：完全没有 dry_dead/dead_crops",
         {}),
    ):
        rows = TV.green_rows(1)
        for i, r in enumerate(rows):
            if r.get("event") == "day_end":
                r = dict(r)
                r.update(extra)
                r["ended_reason"] = "no_work:确实找不到可做的活"
                r["checks"] = dict(r["checks"], watered_outdoor=True)
                r["final_water"] = {"t": 199.0, "location": "Farm", "tiles": 30, "crops": 0,
                                    "dry": 0, "scope": "window"}
                r["final"] = dict(r["final"], unwatered_crops=0)
                rows[i] = r
        ok, s = VR.report(rows, target_days=1)
        print(f"\n--- {tag} ---")
        print(f"ok={ok} verdict={s.get('verdict')}")
        print(f"problems={json.dumps(s.get('problems'), ensure_ascii=False)}")
        print(f"infos={json.dumps(s.get('infos'), ensure_ascii=False)}")

    print("\nALL DONE")


if __name__ == "__main__":
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    print(buf.getvalue())
