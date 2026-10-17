# -*- coding: utf-8 -*-
"""task-209 §2：农场已放置机器扫描（3×3 网格走位 + 每点 full observe 收集 `kind=="object"`）。

做法：每点 `move_to`（失败记 unreachable，不硬耗）→ `observe?detail=full` →
把窗口内 `location.tiles[]` 里 `kind=="object"` 的 `tile/objId/type/actionable/name` 收集，
跨点按 tile 去重，落 `scratch/t210-farm-objects.json`。

只走位 + 只读观测，不改世界（不挖/不收/不放/不砍）。末尾把玩家走回 Farm 中央 (64,15)。
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

# 农场大致 80×65；3×3 网格，点间隔 ~22–24 格（窗口 400 格 ≈ 以玩家为中心 20×20）
POINTS = [(18, 16), (40, 16), (62, 16),
          (18, 36), (40, 36), (62, 36),
          (18, 56), (40, 56), (62, 56)]
HOME = (64, 15)
# 关心的机器 objId（SDV 常量的字符串形式；Mod 给的是 objId/type 字段原文）
WANT = {"114": "Furnace 熔炉", "12": "Charcoal Kiln 炭窑", "13": "Furnace?", "130": "Chest 箱子",
        "232": "Stone Chest 石箱", "105": "Tapper?", "10": "?"}


def tile_of(entry: dict) -> tuple[int, int] | None:
    t = entry.get("tile")
    if isinstance(t, (list, tuple)) and len(t) == 2:
        return int(t[0]), int(t[1])
    return None


def main() -> int:
    c = BridgeClient()
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "points": POINTS, "per_point": [],
                 "objects": [], "unreachable": [], "machines": {}}
    seen: dict[tuple[int, int], dict] = {}
    for (x, y) in POINTS:
        rec: dict = {"point": [x, y], "move": None, "elapsed_s": None, "seen_obj": 0, "error": None}
        t0 = time.time()
        try:
            mv = c.move_to(x, y, timeout_ms=30000)
            rec["move"] = {"ok": mv.get("ok"), "status": mv.get("status"),
                           "reason": (mv.get("reason") or "")[:220],
                           "to": (mv.get("player") or {}).get("tile") if isinstance(mv.get("player"), dict) else None}
        except BridgeError as exc:
            rec["move"] = {"ok": False, "status": exc.status, "reason": (exc.reason or "")[:220]}
            out["unreachable"].append({"point": [x, y], "status": exc.status, "reason": (exc.reason or "")[:300]})
        rec["elapsed_s"] = round(time.time() - t0, 2)
        try:
            obs = c.observe("full")
        except BridgeError as exc:
            rec["error"] = f"observe 失败：{exc.status}: {(exc.reason or '')[:160]}"
            out["per_point"].append(rec)
            print(f"[{x:>2},{y:>2}] move={rec['move'] and rec['move']['status']} observe 失败 {rec['error']}")
            continue
        p = obs.get("player") or {}
        loc = obs.get("location") or {}
        tiles = loc.get("tiles") or []
        kinds: dict[str, int] = {}
        for t in tiles:
            k = str(t.get("kind"))
            kinds[k] = kinds.get(k, 0) + 1
        n_obj = 0
        for t in tiles:
            if t.get("kind") != "object":
                continue
            tt = tile_of(t)
            if tt is None:
                continue
            n_obj += 1
            if tt in seen:
                continue
            row = {"tile": [tt[0], tt[1]], "objId": t.get("objId"), "type": t.get("type"),
                   "name": t.get("name"), "actionable": t.get("actionable"), "from_point": [x, y]}
            seen[tt] = row
        rec["seen_obj"] = n_obj
        rec["player_tile_after"] = p.get("tile")
        rec["window_tiles"] = len(tiles)
        rec["location_objects_total"] = loc.get("objects")
        rec["kinds"] = kinds
        out["per_point"].append(rec)
        print(f"[{x:>2},{y:>2}] move={rec['move']['status']:<8} at={p.get('tile')} window={len(tiles)} "
              f"obj_in_window={n_obj} kinds={kinds} ({rec['elapsed_s']}s)")
        time.sleep(0.2)
    out["objects"] = [seen[k] for k in sorted(seen)]
    # 分组：按 objId 统计 + 识别关心的机器
    by_id: dict[str, list] = {}
    for row in out["objects"]:
        by_id.setdefault(str(row.get("objId")), []).append(row["tile"])
    out["by_objId"] = {k: {"count": len(v), "tiles": sorted(v)[:12], "hint": WANT.get(k)} for k, v in
                       sorted(by_id.items(), key=lambda kv: -len(kv[1]))}
    out["machines"] = {k: out["by_objId"][k] for k in ("114", "12", "130", "232") if k in out["by_objId"]}
    print("\n=== 去重后 object 总数 = %d ===" % len(out["objects"]))
    for k, v in list(out["by_objId"].items())[:20]:
        print(f"  objId={k:<6} count={v['count']:<4} {v['hint'] or ''} tiles[:6]={v['tiles'][:6]}")
    print(f"\n关心的机器：{json.dumps(out['machines'], ensure_ascii=False)}")
    print(f"unreachable 点：{json.dumps(out['unreachable'], ensure_ascii=False)[:400]}")
    # 走回 Farm 中央（不硬耗；失败也照实记）
    try:
        mv = c.move_to(*HOME, timeout_ms=40000)
        print(f"\n回程 move_to{HOME}: status={mv.get('status')} ok={mv.get('ok')} "
              f"reason={(mv.get('reason') or '')[:120]}")
        out["return_home"] = {"ok": mv.get("ok"), "status": mv.get("status")}
    except BridgeError as exc:
        print(f"\n回程失败：{exc.status}: {(exc.reason or '')[:200]}")
        out["return_home"] = {"ok": False, "status": exc.status}
    path = os.path.join(REPO, "scratch", "t210-farm-objects.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n已写出 {path}（{os.path.getsize(path)} B）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
