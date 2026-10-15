"""task-94 只读：把 run5/run6/run7 账本里与播种/开垦有关的事件形状拉平。

只读，不写生产文件。用法： python scratch\_t94_shapes.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGERS = {
    "run5": os.path.join(ROOT, "logs", "longrun-3day-llm-run5.jsonl"),
    "run6": os.path.join(ROOT, "logs", "longrun-3day-llm-run6.jsonl"),
    "run7": os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl"),
}
WANT = (
    "stage", "outcome", "decision", "plot", "stage_exhausted", "stage_no_target",
    "stage_midway_leftover", "blocked", "tool_refused", "unreachable", "unreachable_stage",
    "idle", "sow", "till", "plant", "water", "harvest", "clear_dead_scope",
    "intent_verdict", "policy", "plot_walk", "goto_farm", "work_spot", "plots_capped",
)


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except Exception as exc:  # noqa: BLE001
                rows.append((i, {"event": "<bad>", "error": str(exc)}))
    return rows


def main():
    for name, path in LEDGERS.items():
        if not os.path.isfile(path):
            print(f"== {name}: 缺文件 {path}")
            continue
        rows = load(path)
        cnt = Counter(str(ev.get("event")) for _, ev in rows)
        print(f"== {name}: {len(rows)} 行, {len(cnt)} 种事件")
        print("   事件计数:", "、".join(f"{k}={v}" for k, v in sorted(cnt.items())))
        for want in WANT:
            hits = [(ln, ev) for ln, ev in rows if str(ev.get("event")) == want]
            if not hits:
                continue
            keys = defaultdict(set)
            for _, ev in hits:
                for k, v in ev.items():
                    keys[k].add(type(v).__name__)
            print(f"   [{want}] ×{len(hits)} keys="
                  + "、".join(f"{k}:{'/'.join(sorted(v))}" for k, v in sorted(keys.items())))
            ln, ev = hits[0]
            sample = {k: v for k, v in ev.items() if k not in ("event",)}
            print(f"      首条 L{ln}: {json.dumps(sample, ensure_ascii=False)[:600]}")
        # day_end.stages 形状
        for ln, ev in rows:
            if ev.get("event") == "day_end":
                stages = ev.get("stages")
                print(f"   [day_end L{ln}] stages type={type(stages).__name__}"
                      f" len={len(stages) if isinstance(stages, list) else '-'}")
                if isinstance(stages, list) and stages:
                    print("      stages[0]=", json.dumps(stages[0], ensure_ascii=False)[:500])
                    for st in stages:
                        if isinstance(st, dict) and st.get("stage") in ("plant_area", "till_area"):
                            print("      ", json.dumps(st, ensure_ascii=False)[:500])
                fin = ev.get("final") or {}
                print(f"      final keys={sorted(fin)} seeds={fin.get('seeds')}")
                break
        print()


if __name__ == "__main__":
    sys.exit(main())
