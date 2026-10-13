# -*- coding: utf-8 -*-
r"""task-35 独立验收探针（只读产线源码，只写 scratch\）。

1) 直接调用产线 `LongRun._water_evidence`（brain/agentfarm/longrun.py:529-597）打点，
   覆盖：室内末快照 / 全浇 / 空窗口 / farm 口径 3 干格 / farm 0 作物 / 旧 Mod 缺 dryCrops /
   窗口被截断。
2) 用产线函数的**真实返回值**改 scratch\\journal-green.jsonl 的 3 个 day_end，生成破坏性账本
   （`verified` 按 longrun.py:1907 `all(checks.values())` 同口径重算），交给 tools\\verify-run3.py。

跑法（pwsh，必须带 PYTHONUTF8）：
  $env:PYTHONUTF8="1"; & $py scratch\_t35_probe.py
"""
import hashlib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))
sys.path.insert(0, str(REPO / "tests"))

import test_longrun as T  # noqa: E402

OUT = REPO / "scratch"


def sha(rel: str) -> str:
    b = (REPO / rel).read_bytes()
    return f"sha256={hashlib.sha256(b).hexdigest()[:12]} size={len(b)}"


def show(tag: str, ok: bool, info: dict) -> None:
    print(f"[{tag}] ok={ok!r} {json.dumps(info, ensure_ascii=False)}")


def indoor_obs(w) -> dict:
    obs = w.obs()
    obs["location"] = {"name": "FarmHouse", "isOutdoorFarm": False, "tiles": [],
                       "tillable": [], "furniture": [], "doors": []}
    return obs


def make_world(*, watered: bool):
    w = T.FakeWorld(weeds=0, seeds=0, money=0)
    w.dirt.add((60, 10))
    w.crops[(60, 10)] = {"ripe": False, "watered": watered}
    return w


def probe() -> dict:
    res = {}
    for rel in ("brain/agentfarm/longrun.py", "tests/test_longrun.py",
                "brain/agentfarm/farmwork.py", "tools/verify-run3.py"):
        print(f"{rel} {sha(rel)}")

    w = make_world(watered=False)
    run = T.make_run(w, target_days=1, max_days=1)
    indoor = indoor_obs(w)
    outdoor_dry = w.obs()

    # A1 室内末快照 + 户外有未浇作物 ⇒ 必须 False（窗口口径）
    res["A1"] = run._water_evidence(indoor, outdoor_obs=outdoor_dry,
                                    outdoor_t=12.5, outdoor_name="Farm")
    show("A1 indoor-last+outdoor-dry", *res["A1"])

    # A2 户外全浇 ⇒ True
    w2 = make_world(watered=True)
    run2 = T.make_run(w2, target_days=1, max_days=1)
    res["A2"] = run2._water_evidence(indoor_obs(w2), outdoor_obs=w2.obs(),
                                     outdoor_t=12.5, outdoor_name="Farm")
    show("A2 all-watered", *res["A2"])

    # A3 户外快照存在但窗口 0 格（farm 口径不可用）⇒ 期望 False，实测？
    odd = w.obs()
    odd["location"] = {"name": "Farm", "isOutdoorFarm": True, "tiles": [], "tillable": [],
                       "furniture": [], "doors": []}
    odd.pop("farm", None)
    res["A3"] = run._water_evidence({"location": {"name": "FarmHouse"}, "farm": {}},
                                    outdoor_obs=odd, outdoor_t=9.0, outdoor_name="Farm")
    show("A3 empty-window", *res["A3"])

    # A4 farm 口径 dryCrops=3 ⇒ False / scope=farm
    obs4 = w.obs()
    obs4["farm"] = {"loaded": True, "complete": True, "crops": 5, "dryCrops": 3,
                    "unwateredCrops": 5, "hoeDirt": 5}
    res["A4"] = run._water_evidence(obs4, outdoor_obs=w.obs(), outdoor_t=5.0, outdoor_name="Farm")
    show("A4 farm-dryCrops=3", *res["A4"])

    # A5 farm 口径 0 作物（真空真）⇒ True、tiles=crops=0
    obs5 = w.obs()
    obs5["farm"] = {"loaded": True, "complete": True, "crops": 0, "dryCrops": 0,
                    "unwateredCrops": 0, "hoeDirt": 0}
    res["A5"] = run._water_evidence(obs5, outdoor_obs=w.obs(), outdoor_t=5.0, outdoor_name="Farm")
    show("A5 farm-0-crops-vacuous", *res["A5"])

    # A6 旧 Mod 无 dryCrops ⇒ 退回窗口
    obs6 = w.obs()
    obs6["farm"] = {"loaded": True, "complete": True, "crops": 5, "unwateredCrops": 5, "hoeDirt": 5}
    res["A6"] = run._water_evidence(obs6, outdoor_obs=w.obs(), outdoor_t=5.0, outdoor_name="Farm")
    show("A6 old-mod-no-dryCrops", *res["A6"])

    # A7 窗口 tilesTruncated=true 且窗口里没有作物格 ⇒ dry=0（白过候选）
    odd7 = w.obs()
    loc7 = dict(odd7["location"])
    loc7["tilesTruncated"] = True
    loc7["tiles"] = [{"tile": [1, 1], "kind": "dirt", "watered": False}]
    odd7["location"] = loc7
    odd7.pop("farm", None)
    res["A7"] = run._water_evidence({"location": {"name": "FarmHouse"}, "farm": {}},
                                    outdoor_obs=odd7, outdoor_t=7.0, outdoor_name="Farm")
    show("A7 truncated-window-no-crop-tile", *res["A7"])
    return res


def patch_ledger(res: dict, cases: dict) -> None:
    rows = [json.loads(line) for line in
            (OUT / "journal-green.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"green rows={len(rows)} events={[r['event'] for r in rows if r['event'] in ('day_start', 'day_end', 'finish')]}")
    ends = [(i, r) for i, r in enumerate(rows) if r["event"] == "day_end"]
    print("day_end checks keys=", sorted(ends[0][1].get("checks", {}).keys()))

    for name, (ok, key) in cases.items():
        info = res[key][1]
        out_rows = json.loads(json.dumps(rows))          # 深拷贝
        for r in out_rows:
            if r["event"] != "day_end":
                continue
            r["checks"]["watered_outdoor"] = bool(ok)
            r["final_water"] = info
            r["verified"] = all(bool(v) for v in r["checks"].values())
        path = OUT / f"review-t19-{name}.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
                        encoding="utf-8")
        print(f"wrote {path.name} watered_outdoor={ok!r} final_water={json.dumps(info, ensure_ascii=False)} "
              f"verified={[r['verified'] for r in out_rows if r['event'] == 'day_end']}")


def integration_stale_farm() -> None:
    """I1 集成：world 里作物被真浇过、但 `farm` 块自述 dryCrops=1（陈旧/不一致）⇒ 这一天**不许**
    VERIFIED（`checks.watered_outdoor` 与 `rep.verified` 与 `run()` 退出码三处必须一致）。"""
    w = make_world(watered=False)
    w.farm = {"loaded": True, "complete": True, "crops": 1, "dryCrops": 1,
              "unwateredCrops": 1, "hoeDirt": 1}
    run = T.make_run(w, target_days=1, max_days=1)
    code = run.run()
    rep = run.days[0]
    print(f"[I1 stale-farm-block] run()={code!r} checks={json.dumps(rep.checks, ensure_ascii=False)} "
          f"verified={rep.verified!r} final_water={json.dumps(rep.final_water, ensure_ascii=False)} "
          f"world_watered={int(rep.final.get('unwatered_crops') or 0) == 0}")


def main() -> None:
    res = probe()
    patch_ledger(res, {
        "B1-window-dry": (False, "A1"),      # 室内末快照 + 户外有未浇作物
        "B2-farm-dry": (False, "A4"),        # farm 口径 dryCrops=3
        "B3-empty-window-true": (True, "A3"),  # 空窗口却自称 true（产线真实返回值）
    })
    integration_stale_farm()


if __name__ == "__main__":
    main()
