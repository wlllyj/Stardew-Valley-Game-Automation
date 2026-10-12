"""只读：账本 schema 核对（task-25 用）。

  python scratch\\_ledger_schema.py logs\\longrun-3day-llm-run2.jsonl
      → 每种 event 的键集合 + 计数；并逐条打印 day_end 的 stages/outcomes/checks/final/其它键
  python scratch\\_ledger_schema.py logs\\longrun-3day-llm-run1.jsonl
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path):
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append((i, json.loads(raw)))
            except Exception as exc:
                print(f"L{i}: 解析失败 {exc}")
    return out


def main() -> int:
    path = sys.argv[1]
    rows = load(path)
    print(f"文件: {path}  行数: {max((i for i, _ in rows), default=0)}（非空事件 {len(rows)}）")
    keys = {}
    for _, ev in rows:
        keys.setdefault(ev.get("event"), set()).update(ev.keys())
    for name in sorted(keys, key=lambda n: (n is None, n)):
        print(f"  {name}: {len(keys[name])} 键 -> {sorted(keys[name])}")
    print()
    for i, ev in rows:
        if ev.get("event") != "day_end":
            continue
        day = ev.get("day")
        print(f"--- day_end L{i} day={day} ended_by={ev.get('ended_by')} verified={ev.get('verified')}")
        for key in ("checks", "ok_steps", "skipped_steps", "failed_steps", "final_water"):
            if key in ev:
                print(f"    {key} = {json.dumps(ev[key], ensure_ascii=False)}")
            else:
                print(f"    {key} = <缺失>")
        print(f"    final = {json.dumps(ev.get('final'), ensure_ascii=False)}")
        for key in ("stages", "outcomes"):
            seq = ev.get(key)
            print(f"    {key}: {type(seq).__name__} len={len(seq) if isinstance(seq, (list, dict)) else '-'}")
            if isinstance(seq, list):
                for entry in seq:
                    print(f"      {json.dumps(entry, ensure_ascii=False)}")
        other = sorted(set(ev) - {"event", "t", "day", "day_text", "started_at", "ended_by",
                                  "ended_reason", "verified", "checks", "ok_steps", "skipped_steps",
                                  "failed_steps", "final", "final_water", "stages", "outcomes", "plots"})
        print(f"    其它键: {other}  plots.len={len(ev.get('plots') or [])} notes={json.dumps(ev.get('notes'), ensure_ascii=False)[:400]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
