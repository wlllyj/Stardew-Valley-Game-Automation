"""只读：把彩排账本的事件形状拉平（键集合、decision/LLM 计数、day_end.stages[] 键、sleep/blocked 明细）。

用法: python scratch\\_reh_fields.py <journal.jsonl>
"""
import collections
import json
import sys

path = sys.argv[1]
rows = []
with open(path, encoding="utf-8") as fh:
    for i, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append((i, json.loads(line)))
        except json.JSONDecodeError as exc:
            print(f"[坏行 {i}] {exc}")

print(f"=== {path}: {len(rows)} 事件 ===")
byname = collections.Counter(ev.get("event") for _, ev in rows)
for name, n in byname.most_common():
    print(f"  {name:26s} {n}")

print("\n=== 每类事件的键集合（并集）===")
keys = collections.defaultdict(set)
for _, ev in rows:
    keys[ev.get("event")].update(ev.keys())
for name in sorted(keys, key=lambda k: str(k)):
    print(f"  {name:26s} {sorted(keys[name])}")

print("\n=== 新事件是否存在 ===")
for probe in ("env_fail", "inconclusive_fail", "env_spin_capped", "modal_blocked",
              "modal_timeout", "modal_loop_capped", "modal_wait_error", "modal_wait_start",
              "modal_gone", "modal_switched", "modal_dismissed", "levelup_profession_pending",
              "levelup_profession_unknown", "step", "stage", "policy_fallback"):
    print(f"  {probe:28s} {byname.get(probe, 0)}")

print("\n=== decision 全量 ===")
llm_n = 0
for i, ev in rows:
    if ev.get("event") != "decision":
        continue
    is_llm = bool(ev.get("llm")) or ev.get("source") == "llm"
    if is_llm:
        llm_n += 1
    intents = ev.get("intents") or []
    itxt = "; ".join(f"{x.get('task')}@{x.get('area_hint')}" for x in intents if isinstance(x, dict))
    print(f"  L{i} t={ev.get('t')} day={ev.get('day')} boundary={ev.get('boundary')!r} "
          f"source={ev.get('source')!r} llm={ev.get('llm')!r} zone={ev.get('zone')!r} "
          f"fallback={str(ev.get('fallback'))[:80]!r} intents=[{itxt}]")
print(f"  >> decision 总数 {byname.get('decision', 0)}，其中 llm 计 {llm_n}")

print("\n=== decision 里所有 llm/usage/model/truncat 相关键 ===")
seen = set()
for _, ev in rows:
    if ev.get("event") != "decision":
        continue
    for k in ev:
        if any(s in k.lower() for s in ("llm", "usage", "token", "truncat", "model", "prompt", "latency", "ms")):
            seen.add(k)
print("  ", sorted(seen))
for i, ev in rows:
    if ev.get("event") == "decision" and (ev.get("llm") or ev.get("source") == "llm"):
        extra = {k: v for k, v in ev.items()
                 if any(s in k.lower() for s in ("llm", "usage", "token", "truncat", "model", "prompt", "latency", "ms"))}
        print(f"  L{i} {json.dumps(extra, ensure_ascii=False)[:400]}")

print("\n=== day_end 形状 ===")
for i, ev in rows:
    if ev.get("event") != "day_end":
        continue
    print(f"  L{i} day={ev.get('day')} ended_by={ev.get('ended_by')!r} verified={ev.get('verified')!r}")
    print(f"     checks={json.dumps(ev.get('checks'), ensure_ascii=False)}")
    print(f"     final keys={sorted((ev.get('final') or {}).keys())}")
    print(f"     final={json.dumps(ev.get('final'), ensure_ascii=False)}")
    print(f"     final_water={json.dumps(ev.get('final_water'), ensure_ascii=False)}")
    stages = ev.get("stages") or []
    sk = set()
    for st in stages:
        if isinstance(st, dict):
            sk.update(st.keys())
    print(f"     stages n={len(stages)} 键并集={sorted(sk)}")
    for st in stages:
        if isinstance(st, dict):
            print(f"       {json.dumps(st, ensure_ascii=False)[:500]}")

print("\n=== sleep 明细 ===")
for i, ev in rows:
    if ev.get("event") == "sleep":
        print(f"  L{i} {json.dumps(ev, ensure_ascii=False)[:700]}")

print("\n=== blocked 明细 ===")
for i, ev in rows:
    if ev.get("event") == "blocked":
        print(f"  L{i} {json.dumps(ev, ensure_ascii=False)[:400]}")

print("\n=== t 序列倒挂 ===")
prev = None
for i, ev in rows:
    t = ev.get("t")
    if isinstance(t, (int, float)):
        if prev is not None and t < prev[1]:
            print(f"  L{i} t={t} < 前一个 L{prev[0]} t={prev[1]}")
        prev = (i, t)
print("  (无输出=没有倒挂)")
