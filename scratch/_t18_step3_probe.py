"""task-18 诊断：pre 步 3（单技能砍树）在 0.7.45 上 FAIL —— 是 (32,17) 这格特殊，还是所有树都砍不动？
只读 + 正常砍树动作（与冒烟步 3 同类），不写存档；输出 JSON 行。
用法：PYTHONUTF8=1 python scratch/_t18_step3_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402


def tile_at(obs: dict, x: int, y: int) -> dict | None:
    for t in (obs.get("location") or {}).get("tiles") or []:
        if t.get("x") == x and t.get("y") == y:
            return t
    return None


def tree_candidates(obs: dict) -> list[tuple[int, int, tuple[int, int]]]:
    loc = obs.get("location") or {}
    by_xy = {(t.get("x"), t.get("y")): t for t in loc.get("tiles") or []}
    out: list[tuple[int, int, tuple[int, int]]] = []
    for (x, y), t in by_xy.items():
        if t.get("kind") != "tree":
            continue
        for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            nb = by_xy.get((x + dx, y + dy))
            if nb is not None and nb.get("standable"):
                out.append((x, y, (x + dx, y + dy)))
                break
    return out


def main() -> int:
    c = BridgeClient()
    obs = c.observe(detail="full")
    loc = obs.get("location") or {}
    print(json.dumps({"step": "observe0", "location": loc.get("name"),
                      "player": (obs.get("player") or {}).get("tile"),
                      "clock": obs.get("clock"),
                      "tile_keys": sorted((loc.get("tiles") or [{}])[0].keys())},
                     ensure_ascii=False))
    t0 = tile_at(obs, 32, 17)
    print(json.dumps({"step": "tile_32_17_before", "tile": t0}, ensure_ascii=False))

    # 1) 再对同一格挥一次斧
    try:
        r = c.use_tool((32, 17), tool="axe", timeout_ms=30000)
        print(json.dumps({"step": "axe_32_17", "receipt": r}, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"step": "axe_32_17", "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
    obs = c.observe(detail="full")
    print(json.dumps({"step": "tile_32_17_after", "tile": tile_at(obs, 32, 17),
                      "player": (obs.get("player") or {}).get("tile"),
                      "clock": obs.get("clock")}, ensure_ascii=False))

    # 2) 换一棵树：优先离 (32,17) 最近的其它候选
    cands = [cand for cand in tree_candidates(obs) if cand[:2] != (32, 17)]
    cands.sort(key=lambda v: abs(v[0] - 32) + abs(v[1] - 17))
    print(json.dumps({"step": "other_candidates", "n": len(cands), "first5": cands[:5]}, ensure_ascii=False))
    for (tx, ty, nb) in cands[:3]:
        t_before = tile_at(obs, tx, ty)
        try:
            w = c.move_to(nb, timeout_ms=60000)
            print(json.dumps({"step": "walk", "tile": [tx, ty], "stand": list(nb),
                              "ok": w.get("ok"), "reason": w.get("reason")}, ensure_ascii=False))
            r = c.use_tool((tx, ty), tool="axe", timeout_ms=30000)
            print(json.dumps({"step": "axe_other", "tile": [tx, ty],
                              "status": r.get("status"), "ok": r.get("ok"),
                              "reason": str(r.get("reason"))[:400]}, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"step": "axe_other", "tile": [tx, ty],
                              "error": f"{type(e).__name__}: {e}"[:400]}, ensure_ascii=False))
        obs = c.observe(detail="full")
        t_after = tile_at(obs, tx, ty)
        print(json.dumps({"step": "other_after", "tile": [tx, ty],
                          "kind_before": (t_before or {}).get("kind"),
                          "kind_after": (t_after or {}).get("kind"),
                          "player": (obs.get("player") or {}).get("tile")}, ensure_ascii=False))
        if (t_before or {}).get("kind") != (t_after or {}).get("kind"):
            print(json.dumps({"step": "verdict", "result": "另一棵树可砍 ⇒ (32,17) 格特殊/探针选格问题"}, ensure_ascii=False))
            return 0
    print(json.dumps({"step": "verdict", "result": "另试 3 棵候选全未变化 ⇒ 怀疑产品侧斧头动作失效（需报 Lead）"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
