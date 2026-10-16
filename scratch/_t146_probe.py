r"""task-146 反例 + 交叉核对（只写 scratch/，不改任何生产文件）。

用法：$env:PYTHONUTF8=1; & $py scratch\_t146_probe.py
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "logs" / "longrun-3day-llm-run9c.jsonl"

spec = importlib.util.spec_from_file_location("vr", ROOT / "tools" / "verify-run3.py")
VR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VR)

CHECKS = [
    "slept_by_us", "no_blocking_modal", "no_hard_failures",
    "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
    "crops_watered", "watered_outdoor", "day_justified",
]

raw = LEDGER.read_text(encoding="utf-8").splitlines()
rows = [json.loads(x) for x in raw if x.strip()]
print(f"ledger lines: {len(raw)}  parsed: {len(rows)}")

ends = [(i + 1, r) for i, r in enumerate(rows) if r.get("event") == "day_end"]
print(f"\n=== ① day_end 九项 checks 与 verified 自洽 ===")
for lineno, e in ends:
    day = e.get("day")
    checks = e.get("checks") or {}
    missing = [k for k in CHECKS if k not in checks]
    extra = [k for k in checks if k not in CHECKS]
    all_true = all(bool(checks.get(k)) for k in CHECKS)
    consistent = (bool(e.get("verified")) == all_true) and not missing
    print(f"[line {lineno}] {day} verified={e.get('verified')} 九项全真={all_true} "
          f"自洽={'OK' if consistent else 'MISMATCH'} 未通过={[k for k in CHECKS if not checks.get(k)]} "
          f"缺失={missing} 多余={extra}")
    print(f"    ok_steps={e.get('ok_steps')} skipped={e.get('skipped_steps')} failed={e.get('failed_steps')} "
          f"ended_by={e.get('ended_by')} reason={str(e.get('ended_reason'))[:60]!r}")

print(f"\n=== ② Σ stages[].ok/skip/fail vs day_end 计数 ===")
for lineno, e in ends:
    stages = e.get("stages") or []
    s_ok = sum(int(s.get("ok") or 0) for s in stages)
    s_skip = sum(int(s.get("skipped") or 0) for s in stages)
    s_fail = sum(int(s.get("failed") or 0) for s in stages)
    ok = (s_ok == int(e.get("ok_steps") or 0) and s_skip == int(e.get("skipped_steps") or 0)
          and s_fail == int(e.get("failed_steps") or 0))
    print(f"[line {lineno}] {e.get('day')} stages={len(stages)} Σok={s_ok} vs {e.get('ok_steps')} | "
          f"Σskip={s_skip} vs {e.get('skipped_steps')} | Σfail={s_fail} vs {e.get('failed_steps')} "
          f"=> {'OK' if ok else 'MISMATCH'}")

print(f"\n=== ③ 窗口阈值扫描（同一本账本，只改 --days/target_days）===")
for n in (1, 2, 3, 5):
    ok, summary = VR.report(rows, target_days=n)
    print(f"--days {n}: ok={ok} verdict={summary.get('verdict')!r} strict={summary.get('strict_verdict')!r} "
          f"problems={len(summary.get('problems') or [])} infos={len(summary.get('infos') or [])}")
    for p in (summary.get("problems") or []):
        print(f"      PROBLEM {p}")

print(f"\n=== ④ 反例 A：把 summer 19 拉进窗口（截断到 summer 21 day_end 之后）===")
cut = None
for i, r in enumerate(rows):
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 21]:
        cut = i + 1
print(f"截断行号 = {cut}（保留前 {cut} 行：summer 18/19/20/21）")
tmp = ROOT / "scratch" / "_t146_cut21.jsonl"
tmp.write_text("\n".join(raw[:cut]) + "\n", encoding="utf-8")
ok, summary = VR.report(VR.load(str(tmp)), target_days=3)
print(f"ok={ok} verdict={summary.get('verdict')!r} strict={summary.get('strict_verdict')!r} "
      f"problems={len(summary.get('problems') or [])}")
for p in (summary.get("problems") or []):
    print(f"      PROBLEM {p}")

print(f"\n=== ④ 反例 A2：把 summer 18 也拉进窗口（截断到 summer 20，窗口=18/19/20）===")
cut2 = None
for i, r in enumerate(rows):
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 20]:
        cut2 = i + 1
tmp2 = ROOT / "scratch" / "_t146_cut20.jsonl"
tmp2.write_text("\n".join(raw[:cut2]) + "\n", encoding="utf-8")
ok, summary = VR.report(VR.load(str(tmp2)), target_days=3)
print(f"ok={ok} verdict={summary.get('verdict')!r} strict={summary.get('strict_verdict')!r} "
      f"problems={len(summary.get('problems') or [])}")
for p in (summary.get("problems") or []):
    print(f"      PROBLEM {p}")

print(f"\n=== ④ 反例 B：伪造 summer 20 为有问题的日子（把 watered_outdoor 改 false）后仍要求 VERIFIED ===")
forged = []
for r in rows:
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 20]:
        r = dict(r)
        r["checks"] = dict(r.get("checks") or {}, watered_outdoor=False)
        r["verified"] = False
    forged.append(r)
tmp3 = ROOT / "scratch" / "_t146_forged20.jsonl"
tmp3.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in forged) + "\n", encoding="utf-8")
ok, summary = VR.report(VR.load(str(tmp3)), target_days=3)
print(f"ok={ok} verdict={summary.get('verdict')!r} strict={summary.get('strict_verdict')!r} "
      f"problems={len(summary.get('problems') or [])}")
for p in (summary.get("problems") or []):
    print(f"      PROBLEM {p}")

print(f"\n=== ④ 反例 C：把 summer 19 的标签改脏（summer]19）后仍把问题降级为历史？ ===")
dirty = []
for r in rows:
    r2 = dict(r)
    if r2.get("day") == [1, "summer", 19]:
        r2["day"] = [1, "summer]19", 19]
    dirty.append(r2)
tmp4 = ROOT / "scratch" / "_t146_dirty19.jsonl"
tmp4.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in dirty) + "\n", encoding="utf-8")
ok, summary = VR.report(VR.load(str(tmp4)), target_days=3)
print(f"ok={ok} verdict={summary.get('verdict')!r} strict={summary.get('strict_verdict')!r} "
      f"problems={len(summary.get('problems') or [])} infos={len(summary.get('infos') or [])}")
for p in (summary.get("problems") or []):
    print(f"      PROBLEM {p}")

print("\nDONE")
