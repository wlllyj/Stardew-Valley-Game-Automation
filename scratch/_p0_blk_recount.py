# -*- coding: utf-8 -*-
"""【0.7.48 P0-1】用**既有含 tiles 的真机观测 JSON**复算「新旧 blockers_zone 差 == 该区真实 clump 数」。

观测来源：`scratch/*observe*.json` / `scratch/t15_*.json`（observe?detail=full 的落盘）。
判据（逐区）：
    new_blockers(zone) - old_blockers(zone) == #{tiles 中 kind=="clump" 且落在 zone.bounds 内}

old = D1 事故前的口径 `BLOCKER_KINDS | {stump,log,boulder,rockPile,greenRain}`（死代码）
new = `BLOCKER_KINDS | {"clump"}`（本次修复；承载位）

用法：$env:PYTHONUTF8="1"; & <DSH python> scratch\\_p0_blk_recount.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm import fields as F  # noqa: E402

OLD = frozenset(F.BLOCKER_KINDS | {"stump", "log", "boulder", "rockPile", "greenRain"})
NEW = F.ZONE_BLOCKER_KINDS
# 承载位契约（Contracts.cs:590 / WorldSnapshot.cs:807 / ClumpMeta.cs:39-73）：
# 大障碍在 tiles[].kind 里**只**写 "clump"；子类型在 clumpKind。
CARRIER = F.CLUMP_KIND
# D1 事故前的错误模型：把子类型当 kind 写（Mod 永不产出，属过期夹具）
LEGACY = frozenset({"stump", "log", "boulder", "rockPile", "greenRain"})


def kind_counts_in_bounds(obs, bounds, kinds):
    loc = (obs or {}).get("location") or {}
    tiles = loc.get("tiles") or []
    x0, y0, x1, y1 = bounds
    n = 0
    for t in tiles:
        if not isinstance(t, dict):
            continue
        xy = t.get("tile") or t.get("xy")
        if not xy or len(xy) < 2:
            continue
        x, y = xy[0], xy[1]
        if x0 <= x <= x1 and y0 <= y <= y1 and t.get("kind") in kinds:
            n += 1
    return n


def clump_in_bounds(obs, bounds):
    return kind_counts_in_bounds(obs, bounds, {CARRIER})


def legacy_in_bounds(obs, bounds):
    return kind_counts_in_bounds(obs, bounds, LEGACY)



def is_observe(obs) -> bool:
    return isinstance(obs, dict) and isinstance(obs.get("location"), dict)


def main() -> int:
    cands = sorted(REPO.glob("scratch/*.json")) + sorted(REPO.glob("scratch/**/*.json"))
    files_tiles, files_clump, checked, bad, failclosed = 0, 0, 0, 0, 0
    stale_files = 0
    seen = set()
    for p in cands:
        if p in seen:
            continue
        seen.add(p)
        try:
            obs = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not is_observe(obs):
            continue
        loc = obs["location"]
        tiles = loc.get("tiles") or []
        if not tiles:
            continue
        files_tiles += 1
        has_clump = any(t.get("kind") == "clump" for t in tiles)
        zones = F.zones_from_observe(obs, split=2)
        if not zones:
            continue
        rows = []
        local_bad = 0
        for z in zones:
            F.ZONE_BLOCKER_KINDS = OLD            # 临时换回 D1 旧口径
            old = F.zone_blockers_total(z, obs)
            F.ZONE_BLOCKER_KINDS = NEW            # 还原新口径
            new = F.zone_blockers_total(z, obs)
            cc = clump_in_bounds(obs, z.bounds)
            lg = legacy_in_bounds(obs, z.bounds)
            checked += 1
            if old is None or new is None:
                ok = (old is None and new is None)   # 截断 ⇒ 两边都【无法判定】，正确
                failclosed += 1
                rows.append(f"{z.name}:FAIL-CLOSED(old={old},new={new})")
            else:
                # 精确不变量：new - old == 真承载位 clump 数 − 过期夹具 legacy 数
                ok = (new - old) == (cc - lg)
                rows.append(f"{z.name}:diff={new-old} clump={cc} legacy={lg}")
            if not ok:
                bad += 1
                local_bad += 1
                rows[-1] += " ***MISMATCH***"
        whole = (-10 ** 6, -10 ** 6, 10 ** 6, 10 ** 6)
        if legacy_in_bounds(obs, whole):
            stale_files += 1
            rows.append("[过期夹具:含非承载位 legacy kind]")
        if has_clump or local_bad:
            files_clump += (1 if has_clump else 0)
            print(f"[{p.name}] tiles={len(tiles)} trunc={bool(loc.get('tilesTruncated'))} "
                  + "  ".join(rows))
    F.ZONE_BLOCKER_KINDS = NEW
    print(f"\n含 tiles 的观测文件={files_tiles}（其中含 clump 的={files_clump}）  "
          f"逐区断言={checked}  不符={bad}  其中 fail-closed(None)={failclosed}  "
          f"过期夹具文件={stale_files}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
