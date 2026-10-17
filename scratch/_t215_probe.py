# -*- coding: utf-8 -*-
"""task-215 只读探针：数 -llm.jsonl 的 kind 分布（L1 分母口径）+ 教训库字段形状（L0 口径）。

只读 logs/，不写任何文件（stdout 由调用方重定向到 scratch/）。

用法：
    $env:PYTHONUTF8=1; python scratch\\_t215_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    print("=== logs/*-llm.jsonl 的 kind 分布（L1 分母口径） ===")
    for path in sorted(LOGS.glob("*-llm.jsonl")):
        rows = 0
        kinds: dict[str, int] = {}
        with_prompt = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                kinds["<bad_json>"] = kinds.get("<bad_json>", 0) + 1
                rows += 1
                continue
            rows += 1
            kind = str(row.get("kind") or "<missing>")
            kinds[kind] = kinds.get(kind, 0) + 1
            if isinstance(row.get("prompt"), str):
                with_prompt += 1
        decision_like = kinds.get("decision", 0) + kinds.get("<missing>", 0)
        print(f"{path.name}: 行={rows} 有 prompt={with_prompt} kind={kinds} "
              f"⇒ 只算决策行分母={decision_like}")

    print("\n=== logs/*-lessons.json 的条目形状（L0 口径） ===")
    for path in sorted(LOGS.glob("*-lessons.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"{path.name}: 读不出（{type(exc).__name__}: {exc}）")
            continue
        entries = raw.get("lessons") if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            print(f"{path.name}: 顶层不是 list（keys={list(raw)[:8] if isinstance(raw, dict) else type(raw)}）")
            continue
        keys: set[str] = set()
        pos = 0
        for e in entries:
            if isinstance(e, dict):
                keys |= {str(k) for k in e}
                try:
                    if int(e.get("count") or 0) >= 1:
                        pos += 1
                except (TypeError, ValueError):
                    pass
        print(f"{path.name}: 条数={len(entries)} count>=1 的条数={pos} 键={sorted(keys)}")
        if entries:
            print(f"  首条 = {json.dumps(entries[0], ensure_ascii=False)[:300]}")

    print("\n=== 结论提示 ===")
    print("L0 文档口径 = lessons.total>=1 且至少 1 条 count>=1；compare-runs.py 只判 len(lessons)>=1。")
    print("L1 分母文档/卡面口径 = 只算决策行（kind=='decision' 或旧行无 kind）；"
          "compare-runs.py::prompts_of 未过滤 kind。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
