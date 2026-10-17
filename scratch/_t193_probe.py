"""task-193 recon（只读）：账本里与「卖出白名单 / 掉落归因」有关的字段到底有没有、长什么样。

用法：python scratch\\_t193_probe.py [ledger ...]
默认扫 C2-a 相关账本（run8/run9 家族 + runA3）。
输出：每个账本里含 whitelist/loot/harvested 键的事件名 + 键集合 + 值样例（去重、限量）。
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = [
    "logs/longrun-runA3-0736.jsonl",
    "logs/longrun-3day-llm-run8.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
    "logs/longrun-3day-llm-run9d.jsonl",
]
KEYWORDS = ("whitelist", "loot", "harvested")


def scan(path: str) -> None:
    if not os.path.exists(path):
        print(f"== {path}: 不存在")
        return
    events = Counter()
    shapes = defaultdict(Counter)
    samples = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            name = ev.get("event")
            keys = [k for k in ev if any(w in k.lower() for w in KEYWORDS)]
            if keys:
                events[name] += 1
                for k in keys:
                    shapes[name][k] += 1
                    samples.setdefault((name, k), ev[k])
            # 嵌套一层（after/receipt 等）
            for parent in ("after", "before", "receipt", "detail", "final"):
                sub = ev.get(parent)
                if isinstance(sub, dict):
                    keys2 = [k for k in sub if any(w in k.lower() for w in KEYWORDS)]
                    if keys2:
                        events[f"{name}.{parent}"] += 1
                        for k in keys2:
                            shapes[f"{name}.{parent}"][k] += 1
                            samples.setdefault((f"{name}.{parent}", k), sub[k])
    print(f"== {os.path.basename(path)}")
    if not events:
        print("   （无任何 whitelist/loot/harvested 键）")
        return
    for name, cnt in sorted(events.items()):
        print(f"   {name} ×{cnt}")
        for k, c in sorted(shapes[name].items()):
            v = json.dumps(samples[(name, k)], ensure_ascii=False)
            print(f"      {k} ×{c}  例: {v[:160]}")


def main() -> int:
    targets = sys.argv[1:] or DEFAULT
    for rel in targets:
        scan(rel if os.path.isabs(rel) else os.path.join(ROOT, rel))
    print()
    allf = sorted(glob.glob(os.path.join(ROOT, "logs", "*.jsonl")))
    print(f"logs/*.jsonl 共 {len(allf)} 本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
