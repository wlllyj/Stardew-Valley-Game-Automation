"""看几格 tile 的真值与 kind/feature 词表（输出严格限量，避免刷屏）。

用法：
    python scratch/probe_tiles.py 73 25 74 25 73 26 74 26
"""
from __future__ import annotations

import collections
import json
import sys

sys.path.insert(0, r"D:\Deepseek Harness Workspace\星露谷游戏自动化\brain")

from agentfarm.bridge import BridgeClient  # noqa: E402


def main() -> int:
    args = sys.argv[1:]
    goto = ""
    if "--farm" in args:
        args.remove("--farm")
        goto = "Farm"
    pairs = [int(v) for v in args]
    want = {(pairs[i], pairs[i + 1]) for i in range(0, len(pairs) - 1, 2)}
    c = BridgeClient(timeout=20.0)
    if goto:
        r = c.move_to_location(goto, timeout_ms=40000)
        print("goto %s：status=%s reached=%s 用时=%sms"
              % (goto, r.get("status"), r.get("reachedLocation"), r.get("elapsedMs")))
    obs = c.observe("full")
    loc = obs["location"]
    tiles = loc.get("tiles") or []
    tillable = {tuple(t) for t in (loc.get("tillable") or [])}
    print("地点 %s outdoor=%s tiles=%d 截断=%s tillable=%d 玩家 %s"
          % (loc.get("name"), loc.get("isOutdoorFarm"), len(tiles),
             loc.get("tilesTruncated"), len(tillable), obs["player"]["tile"]))
    vocab = collections.Counter((t.get("kind"), t.get("feature"), t.get("tool"),
                                 t.get("objId")) for t in tiles)
    print("kind/feature/tool/objId 词表（全部 %d 种）" % len(vocab))
    for k, v in vocab.most_common():
        print("  %3d  %s" % (v, k))
    print("指定格：")
    for t in tiles:
        key = tuple(t.get("tile") or [])
        if key in want:
            print("  %s  %s" % (key, json.dumps(t, ensure_ascii=False)))
    print("指定格是否在 tillable[]：%s"
          % sorted((x, x in tillable) for x in want))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
