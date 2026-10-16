# -*- coding: utf-8 -*-
"""三源一致性检查骨架（task-184 待命期只读准备）。

三源 = ① 脑侧 StepResult ② Mod 原始回执 ③ 世界差分（两份独立 `observe?detail=full`）。
本脚本**离线**工作：只吃已经落盘的 JSON（不自带任何 harvest/sell 动作、不联网、不碰桥），
因此可以在没有游戏的情况下自测与复现 task-177 的反向不一致。

核心判据（task-184 的验收口径）：脑侧 `ok` + Mod `acted=true/actedEvidence` + 世界证据，
**三者一致**才算 PASS；任一方向不一致都要给出分类名 + 最小复现信息。

用法
----
1) 自测（内置 task-177 的两个真实样本 + 2 个合成反例）：
     python scratch\\_t184_triple_check.py --selftest
2) 检查真实取证（before/after 两份 full observe + 回执 JSON）：
     python scratch\\_t184_triple_check.py --before scratch\\run10b-tile6029-before.json \
         --after scratch\\run10b-tile6029-after.json --tile 60,29 --receipt scratch\\_t184_receipt.json
   `--brain` 可选：脑侧 StepResult 的 JSON（`{"ok":..,"code":..,"status":..,"reason":..}`）。
3) 从脑账本里取 StepResult（长跑跑完后用）：`--journal logs\\longrun-....jsonl --tile 60,29`

退出码：0 = 三源一致（全成功或全失败）；10 = 反向不一致；11 = 输入不完整（缺 before/after）；
12 = 找不到指定格；13 = `--selftest` 用例与预期不符。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))

# 从一份 full observe 里取"那一格"时要看的字段（task-177 用过的那组）
TILE_KEYS = ("kind", "tool", "feature", "crop", "ripe", "ready", "readySource", "harvestMethod",
             "fullyGrown", "currentPhase", "phaseDays", "dayOfCurrentPhase", "dead", "watered",
             "standable", "actionable", "plantable", "regrowsAfterHarvest")
FARM_KEYS = ("crops", "ripeCrops", "readyCrops", "deadCrops", "unwateredCrops", "dryCrops",
             "hoeDirt", "emptyDirt")

# 三源分类名（写进报告时直接引用）
C_AGREE_OK = "AGREE_SUCCESS"
C_AGREE_FAIL = "AGREE_FAILURE"
C_BRAIN_FAIL_WORLD_CHANGED = "BRAIN_SAYS_FAIL__WORLD_CHANGED"      # 缺陷 A 的签名
C_MOD_NOACTION_WORLD_CHANGED = "MOD_SAYS_NO_ACTION__WORLD_CHANGED"  # 缺陷 B 的签名
C_BRAIN_OK_WORLD_UNCHANGED = "BRAIN_SAYS_OK__WORLD_UNCHANGED"      # 洗白（绝不允许）
C_MOD_ACTED_WORLD_UNCHANGED = "MOD_ACTED__WORLD_UNCHANGED"         # 回执说谎
C_PARTIAL = "PARTIAL_MISMATCH"


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _observe(doc: dict) -> dict:
    """接受三种形状：裸 observe / {"observe": ...} / {"observe": {"observe": ...}}。"""
    for _ in range(3):
        if isinstance(doc, dict) and "observe" in doc and isinstance(doc["observe"], dict):
            doc = doc["observe"]
            continue
        break
    return doc if isinstance(doc, dict) else {}


def _tile_of(obs: dict, tile: tuple[int, int]) -> dict | None:
    tiles = (((obs.get("location") or {}).get("tiles")) or [])
    for t in tiles:
        if isinstance(t, dict) and list(t.get("tile") or []) == [tile[0], tile[1]]:
            return t
    return None


def _farm(obs: dict) -> dict:
    return obs.get("farm") or {}


def _inv(obs: dict) -> list:
    return ((obs.get("player") or {}).get("inventory")) or []


def _qid_map(inv: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for slot in inv:
        if not isinstance(slot, dict):
            continue
        qid = slot.get("itemId") or slot.get("qid") or slot.get("id")
        stack = slot.get("stack") or 0
        if qid:
            out[str(qid)] = out.get(str(qid), 0) + int(stack)
    return out


def world_diff(before: dict, after: dict, tile: tuple[int, int]) -> dict:
    """四判据 + 逐 qid 背包 diff（一镰刀可能收多格 ⇒ 记账按 qid 不按格）。"""
    b_obs, a_obs = _observe(before), _observe(after)
    b_t, a_t = _tile_of(b_obs, tile), _tile_of(a_obs, tile)
    b_f, a_f = _farm(b_obs), _farm(a_obs)
    b_inv, a_inv = _qid_map(_inv(b_obs)), _qid_map(_inv(a_obs))
    loot = {q: a_inv.get(q, 0) - b_inv.get(q, 0) for q in set(b_inv) | set(a_inv)
            if a_inv.get(q, 0) - b_inv.get(q, 0) != 0}
    seq_b = b_obs.get("worldSeq")
    seq_a = a_obs.get("worldSeq")
    crit = {
        "crop_gone": bool(b_t and b_t.get("crop") not in (None, "") and not (a_t or {}).get("crop")),
        "ready_flipped": bool(b_t and b_t.get("ready") is True and (a_t or {}).get("ready") is not True),
        "loot_gained": bool(loot),
        "readyCrops_down": (b_f.get("readyCrops") is not None and a_f.get("readyCrops") is not None
                            and a_f["readyCrops"] < b_f["readyCrops"]),
        "worldSeq_advanced": (seq_b is not None and seq_a is not None and seq_a > seq_b),
    }
    return {
        "tile": list(tile),
        "tile_before": {k: (b_t or {}).get(k) for k in TILE_KEYS} if b_t else None,
        "tile_after": {k: (a_t or {}).get(k) for k in TILE_KEYS} if a_t else None,
        "tile_key_present": {"harvestMethod_before": bool(b_t and "harvestMethod" in b_t),
                            "harvestMethod_after": bool(a_t and "harvestMethod" in a_t),
                            "readySource_before": bool(b_t and "readySource" in b_t)},
        "farm_before": {k: b_f.get(k) for k in FARM_KEYS},
        "farm_after": {k: a_f.get(k) for k in FARM_KEYS},
        "loot_qid_diff": loot,
        "worldSeq_before": seq_b, "worldSeq_after": seq_a,
        "criteria": crit,
        # 世界层面的"收获成功"= 四择一任一成立（task-181 要落的口径）
        "world_harvest_ok": any(crit[k] for k in ("crop_gone", "ready_flipped", "loot_gained", "readyCrops_down")),
    }


def classify(brain: dict | None, receipt: dict | None, world: dict) -> dict:
    brain_ok = bool(brain and brain.get("ok") is True and (brain.get("code") or "ok") == "ok")
    rec_acted = bool(receipt and (receipt.get("acted") is True
                                  or (receipt.get("actedEvidence") and receipt.get("actedEvidence") != "none")))
    rec_status = (receipt or {}).get("status")
    rec_ok = bool(receipt and receipt.get("ok") is True and rec_status == "ok")
    world_ok = bool(world.get("world_harvest_ok"))

    tags: list[str] = []
    if world_ok and not brain_ok:
        tags.append(C_BRAIN_FAIL_WORLD_CHANGED)
    if world_ok and (rec_status == "no_action" or (receipt and receipt.get("acted") is False)):
        tags.append(C_MOD_NOACTION_WORLD_CHANGED)
    if brain_ok and not world_ok:
        tags.append(C_BRAIN_OK_WORLD_UNCHANGED)
    if rec_acted and not world_ok:
        tags.append(C_MOD_ACTED_WORLD_UNCHANGED)

    if brain_ok and world_ok and (rec_acted or rec_ok):
        verdict = C_AGREE_OK
    elif (not brain_ok) and (not world_ok) and not rec_acted:
        verdict = C_AGREE_FAIL
    else:
        verdict = tags[0] if tags else C_PARTIAL
    return {"brain_ok": brain_ok, "mod_acted": rec_acted, "mod_labelled_ok": rec_ok,
            "mod_status": rec_status, "world_harvest_ok": world_ok,
            "tags": tags, "verdict": verdict,
            "three_way_consistent": verdict in (C_AGREE_OK, C_AGREE_FAIL)}


def report(brain, receipt, world, *, title: str = "") -> dict:
    v = classify(brain, receipt, world)
    crit = world["criteria"]
    print(f"--- 三源一致性检查 {('· ' + title) if title else ''} ---")
    print(f"[1] 脑侧 StepResult : ok={None if brain is None else brain.get('ok')} "
          f"code={None if brain is None else brain.get('code')} status={None if brain is None else brain.get('status')}")
    print(f"[2] Mod 原始回执    : ok={None if receipt is None else receipt.get('ok')} "
          f"status={v['mod_status']} acted={None if receipt is None else receipt.get('acted')} "
          f"actedEvidence={None if receipt is None else receipt.get('actedEvidence')}")
    print(f"[3] 世界差分(观测)  : crop消失了={crit['crop_gone']} / ready翻转={crit['ready_flipped']} / "
          f"该 qid 背包+N={crit['loot_gained']}{world['loot_qid_diff'] or ''} / "
          f"readyCrops下降={crit['readyCrops_down']} / worldSeq前进={crit['worldSeq_advanced']} "
          f"⇒ world_harvest_ok={world['world_harvest_ok']}")
    print(f"    farm: crops {world['farm_before'].get('crops')}→{world['farm_after'].get('crops')} / "
          f"readyCrops {world['farm_before'].get('readyCrops')}→{world['farm_after'].get('readyCrops')} / "
          f"emptyDirt {world['farm_before'].get('emptyDirt')}→{world['farm_after'].get('emptyDirt')}")
    flag = "PASS" if v["three_way_consistent"] else "FAIL"
    print(f"VERDICT: {flag} · {v['verdict']}" + (f" · tags={v['tags']}" if v["tags"] else ""))
    if not v["three_way_consistent"]:
        print("最小复现: " + json.dumps({
            "tile": world["tile"], "harvestMethod_before": world["tile_key_present"],
            "tile_before": world["tile_before"], "tile_after": world["tile_after"],
            "loot_qid_diff": world["loot_qid_diff"], "criteria": crit,
            "receipt": receipt, "brain": brain,
        }, ensure_ascii=False)[:1200])
    return v


# ---------------------------------------------------------------- 自测（离线，无游戏）
def _obs(farm: dict, tiles: list, inv: list, worldSeq: int) -> dict:
    return {"observe": {"worldSeq": worldSeq, "farm": farm,
                        "player": {"inventory": inv}, "location": {"tiles": tiles}}}


def selftest() -> int:
    ok = True
    # case 1/2 = task-177 的真实形态（样本格 (60,29)：世界变了、脑与 Mod 都说失败）
    t6029_b = {"tile": [60, 29], "crop": "270", "ready": True, "readySource": "game",
               "harvestMethod": "Grab", "ripe": True, "fullyGrown": True, "dayOfCurrentPhase": -9,
               "regrowsAfterHarvest": True, "watered": True}
    t6029_a = dict(t6029_b, ready=False, dayOfCurrentPhase=4, tool="can")
    inv_b = [{"itemId": "(O)535", "stack": 3}]
    inv_a = [{"itemId": "(O)535", "stack": 3}, {"itemId": "(O)270", "stack": 1}]
    w1 = world_diff(
        _obs({"crops": 102, "readyCrops": 102, "ripeCrops": 1, "emptyDirt": 51}, [t6029_b], inv_b, 60),
        _obs({"crops": 102, "readyCrops": 101, "ripeCrops": 1, "emptyDirt": 51}, [t6029_a], inv_a, 61),
        (60, 29))
    v1 = report({"ok": False, "code": "failed", "status": "", "reason": "游戏口径可收但作物还在…"},
                {"ok": False, "status": "no_action", "acted": False, "skill": "interact"}, w1,
                title="真实形态：样本格 (60,29) 反向不一致")
    if v1["verdict"] != C_BRAIN_FAIL_WORLD_CHANGED or v1["three_way_consistent"]:
        print("!! case1 预期 BRAIN_SAYS_FAIL__WORLD_CHANGED + FAIL"); ok = False
    if C_MOD_NOACTION_WORLD_CHANGED not in v1["tags"]:
        print("!! case1 预期同时命中 MOD_SAYS_NO_ACTION__WORLD_CHANGED"); ok = False

    # case 3 = 三源一致的失败（安全形态）
    w2 = world_diff(
        _obs({"crops": 102, "readyCrops": 102}, [t6029_b], inv_b, 60),
        _obs({"crops": 102, "readyCrops": 102}, [t6029_b], inv_b, 60), (60, 29))
    v2 = report({"ok": False, "code": "failed"}, {"ok": False, "status": "no_action", "acted": False}, w2,
                title="合成：三源一致失败")
    if v2["verdict"] != C_AGREE_FAIL or not v2["three_way_consistent"]:
        print("!! case3 预期 AGREE_FAILURE + PASS"); ok = False

    # case 4 = 洗白（脑说 ok、Mod 说 acted、世界没变）—— 绝不允许
    v3 = report({"ok": True, "code": "ok", "status": "ok"},
                {"ok": True, "status": "ok", "acted": True, "actedEvidence": "tile_sig"}, w2,
                title="合成：洗白 (ok + acted + 世界没变)")
    if v3["verdict"] not in (C_BRAIN_OK_WORLD_UNCHANGED, C_MOD_ACTED_WORLD_UNCHANGED) or v3["three_way_consistent"]:
        print("!! case4 预期洗白类 + FAIL"); ok = False

    # case 5 = 一镰刀多格：该格 crop 消失 + loot 多个 qid
    t6028_a = {"tile": [60, 28], "plantable": True}
    # 真实读数：一镰刀收 4 格 ⇒ (O)262 40→44、(O)178 17→19（fixture 只放这两个 qid，避免假 diff）
    inv_c_before = [{"itemId": "(O)262", "stack": 40}, {"itemId": "(O)178", "stack": 17}]
    inv_c = [{"itemId": "(O)262", "stack": 44}, {"itemId": "(O)178", "stack": 19}]
    w4 = world_diff(
        _obs({"crops": 102, "readyCrops": 101, "emptyDirt": 51},
             [{"tile": [60, 28], "crop": "262", "ready": True, "harvestMethod": "Scythe"}], inv_c_before, 65),
        _obs({"crops": 98, "readyCrops": 97, "emptyDirt": 55}, [t6028_a], inv_c, 67), (60, 28))
    v4 = report({"ok": True, "code": "ok"}, {"ok": True, "status": "ok", "skill": "use_tool"}, w4,
                title="真实形态：对照格 (60,28) 一镰刀多格")
    if v4["verdict"] != C_AGREE_OK or not w4["criteria"]["loot_gained"] or len(w4["loot_qid_diff"]) != 2:
        print("!! case5 预期 AGREE_SUCCESS + 两个 qid loot"); ok = False

    print(f"\nSELFTEST {'PASS' if ok else 'FAIL'}（5 个用例：2 真实形态 + 3 合成；无游戏、无网络）")
    return 0 if ok else 13


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before")
    ap.add_argument("--after")
    ap.add_argument("--receipt")
    ap.add_argument("--brain")
    ap.add_argument("--journal")
    ap.add_argument("--tile")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not (args.before and args.after and args.tile):
        print("需要 --before --after --tile x,y（或 --selftest）", file=sys.stderr)
        return 11
    tile = tuple(int(p) for p in args.tile.split(","))
    before, after = _load(args.before), _load(args.after)
    if _tile_of(_observe(before), tile) is None or _tile_of(_observe(after), tile) is None:
        print(f"!! {tile} 在 before/after 的 location.tiles 里找不到（窗口外？先 move 到旁边）", file=sys.stderr)
        return 12
    receipt = _load(args.receipt) if args.receipt else None
    brain = _load(args.brain) if args.brain else None
    if args.journal and brain is None:
        tile_s = f"{tile[0]},{tile[1]}"
        with open(args.journal, "r", encoding="utf-8") as fh:
            for line in fh:
                if tile_s in line and ('"outcome"' in line or '"blocked"' in line):
                    rec = json.loads(line)
                    brain = {"ok": rec.get("ok"), "code": rec.get("code"),
                             "status": rec.get("status"), "reason": rec.get("reason")}
    world = world_diff(before, after, tile)
    v = report(brain, receipt, world, title=f"{tile}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"verdict": v, "world": world, "receipt": receipt, "brain": brain}, fh,
                      ensure_ascii=False, indent=2)
        print(f"已写出 {args.json}")
    return 0 if v["three_way_consistent"] else 10


if __name__ == "__main__":
    sys.exit(main())
