# -*- coding: utf-8 -*-
"""把一份**完整**世界快照落盘，并打印最常用的几个切片（排查用）。

为什么需要：`observe --full` 的输出经常要落地慢慢看，而 PowerShell 的 `>` 重定向
默认写 UTF-16，直接用 `json.load(utf-8)` 读会报
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`。
本脚本从桥直接取、自己用 UTF-8 写文件，绕开重定向这个坑。

    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\dump-observe.py            # 落盘 brain\\run\\observe-full.json + 打印摘要
    python tools\\dump-observe.py --quiet    # 只落盘

落盘内容就是 `/v1/observe?detail=full` 的原始 JSON（含 `location.furniture[]`）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

RUN_DIR = Path(__file__).resolve().parents[1] / "brain" / "run"


def main() -> int:
    ap = argparse.ArgumentParser(description="把完整世界快照落盘（UTF-8，绕开 PowerShell 重定向）")
    ap.add_argument("--out", default=str(RUN_DIR / "observe-full.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    try:
        snap = BridgeClient(timeout=20.0).observe("full", timeout=20.0)
    except BridgeError as exc:
        print(f"✗ 取快照失败：{exc}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已落盘 {out}（{out.stat().st_size} 字节）")
    if args.quiet:
        return 0

    loc = snap.get("location") or {}
    print("== player ==")
    print(json.dumps(snap.get("player"), ensure_ascii=False, indent=1))
    print("== ui / liveness / game ==")
    for k in ("ui", "liveness", "game"):
        print(f"{k}: {json.dumps(snap.get(k), ensure_ascii=False)}")
    print("== location ==")
    print(json.dumps({k: v for k, v in loc.items()
                      if k not in ("furniture", "objects", "terrainFeatures", "characters")},
                     ensure_ascii=False))
    print(f"location.objects = {json.dumps(loc.get('objects'), ensure_ascii=False)}")
    print(f"location.terrainFeatures = {json.dumps(loc.get('terrainFeatures'), ensure_ascii=False)}")
    print("location.furniture[] =")
    for f in (loc.get("furniture") or []):
        print("  " + json.dumps(f, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
