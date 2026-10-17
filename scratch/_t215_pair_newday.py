# -*- coding: utf-8 -*-
"""task-215 交付件：**通用**六串配对表（只读；不改 tools/）。

为什么补这个：现有 `scratch/runX-tools.py` 系列每个 run 一份、SMAPI 路径与
`--after/--before` 默认值都写死（例：`runA-tools.py` 默认 `03:45:38–04:23:00`），
换一次 run 就要复制改代码。本脚本把同一套逻辑做成**一条命令**：

    $env:PYTHONUTF8=1
    python scratch\\_t215_pair_newday.py --smapi logs\\runA-0732-smapi-window.txt
    python scratch\\_t215_pair_newday.py --smapi logs\\run9-smapi-window.txt --json scratch\\pair-run9.json

口径（与 `docs/_run10-criteria.md` §5-3 一致）：
  * 六串 **必须成组出现**；缺组 ⇒ 输出【无法判定（落盘链缺组）】，
    **不许**拿"存档 mtime 没变"直接判失败或通过；
  * 第 4 串有两个真实变体：`Synchronizing 'Save' task...`（SMAPI 任务）与
    `Saving without compression...`（游戏侧）—— 成功跨日**两条都会出现**，
    所以这里都数、都列（runX 系列脚本只数其中一个，属历史口径差异）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
DAY = re.compile(r"Context: after save, starting (.+?)\.?\s*$")

# (键, 正则)：六串（第 4 串拆成两个变体）+ 两个辅助信号
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("newday", re.compile(r"Synchronizing 'NewDay' task\.\.\.")),
    ("before_save", re.compile(r"Context: before save\.")),
    ("save_called", re.compile(r"SaveGame\.Save\(\) called\.")),
    ("save_task", re.compile(r"Synchronizing 'Save' task\.\.\.")),
    ("saving", re.compile(r"Saving without compression\.\.\.")),
    ("completed", re.compile(r"SaveGame\.Save\(\) completed without exceptions\.")),
    ("after_save", re.compile(r"Context: after save, starting ")),
    # 辅助（不计入六串配对，只作上下文）
    ("task_complete", re.compile(r"task complete\.")),
    ("warp_farm", re.compile(r"Warping to Farm")),
]

CORE_KEYS = ("newday", "before_save", "save_called", "save_task", "saving", "completed", "after_save")


def parse(path: Path, after: str, before: str) -> tuple[list[tuple[str, int, str, str]], int, int]:
    """返回 [(时间, 行号, 原文, 键)]、窗口行数、总行数。"""
    hits: list[tuple[str, int, str, str]] = []
    total = window = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, line in enumerate(fh, 1):
            total += 1
            m = TS.match(line)
            if not m:
                continue
            stamp = m.group(1)
            if after and stamp < after:
                continue
            if before and stamp > before:
                continue
            window += 1
            for key, pat in PATTERNS:
                if pat.search(line):
                    hits.append((stamp, lineno, line.rstrip("\n"), key))
    return hits, window, total


def main(argv: list[str] | None = None) -> int:
    try:  # Windows 控制台 cp1252 下中文会 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="六串配对表（NewDay/before save/Save called/Save task/Saving/completed/after save）")
    ap.add_argument("--smapi", required=True, help="冻结的 SMAPI 窗口文件（logs/runX-smapi-window.txt）")
    ap.add_argument("--after", default="", help="窗口起点 HH:MM:SS（含）")
    ap.add_argument("--before", default="", help="窗口终点 HH:MM:SS（含）")
    ap.add_argument("--pair-seconds", type=int, default=180,
                    help="一个 NewDay 之后多少秒内找其余串（默认 180s）")
    ap.add_argument("--json", dest="json_out", default="", help="结构化结果写到这个文件")
    args = ap.parse_args(argv)

    path = Path(args.smapi)
    if not path.exists():
        print(f"[exit 2] 文件不存在：{path}")
        return 2
    hits, window, total = parse(path, args.after, args.before)
    by_key: dict[str, list[tuple[str, int, str]]] = {k: [] for k in CORE_KEYS}
    for stamp, lineno, line, key in hits:
        if key in by_key:
            by_key[key].append((stamp, lineno, line))

    print("=" * 84)
    print(f"SMAPI 冻结窗口 = {path}")
    print(f"总行数 = {total}；窗口 {args.after or '(起)'}–{args.before or '(终)'} 内 {window} 行")
    print("=" * 84)
    print("\n[1] 六串计数（第 4 串两个真实变体都数）")
    for key in CORE_KEYS:
        items = by_key[key]
        print(f"  {key:<12} = {len(items):>3} 次  行号 {[i[1] for i in items][:12]}")
    print(f"  （辅助）task_complete = {sum(1 for h in hits if h[3] == 'task_complete')}，"
          f"Warping to Farm = {sum(1 for h in hits if h[3] == 'warp_farm')}")

    print("\n[2] 按 NewDay 成组配对（起点后 --pair-seconds 内找其余串）")
    groups: list[dict] = []
    for stamp, lineno, line in by_key["newday"]:
        seconds = lambda s: sum(int(x) * m for x, m in zip(s.split(":"), (3600, 60, 1)))  # noqa: E731
        base = seconds(stamp)
        found: dict[str, list[int]] = {}
        for key in CORE_KEYS:
            if key == "newday":
                continue
            found[key] = [i[1] for i in by_key[key]
                          if 0 <= seconds(i[0]) - base <= args.pair_seconds]
        missing = [k for k in CORE_KEYS if k != "newday" and not found[k]]
        groups.append({"newday_line": lineno, "newday_time": stamp,
                       "found": found, "missing": missing,
                       "complete": not missing})
        flag = "✅ 成组" if not missing else f"❌ 缺组 {missing} ⇒ 【无法判定】"
        print(f"  L{lineno} {stamp} NewDay → "
              + " ".join(f"{k}@L{v[0]}" if v else f"{k}@缺" for k, v in found.items())
              + f"  {flag}")

    complete = sum(1 for g in groups if g["complete"])
    if groups and complete == 0:
        print("\n结论：所有 NewDay 都缺组 ⇒ **落盘链缺组**，按文档 §5-3 写【无法判定】，"
              "不许拿存档 mtime 判通过或失败。")
    elif groups:
        print(f"\n结论：{complete}/{len(groups)} 组完整。（缺组的那几次按【无法判定】单列。）")
    else:
        print("\n结论：窗口内没有 NewDay ⇒ 本轮没有跨日可判。")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"smapi": str(path), "window": [args.after, args.before],
                                   "counts": {k: len(v) for k, v in by_key.items()},
                                   "groups": groups}, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n结构化结果已写：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
