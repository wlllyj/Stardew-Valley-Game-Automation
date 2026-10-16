r"""task-146 反例 2：窗口内问题能否被脏标签/改名降级 + summer 20 现场取证（只写 scratch/）。"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "logs" / "longrun-3day-llm-run9c.jsonl"
spec = importlib.util.spec_from_file_location("vr", ROOT / "tools" / "verify-run3.py")
VR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VR)

raw = LEDGER.read_text(encoding="utf-8").splitlines()
rows = [json.loads(x) for x in raw if x.strip()]


def run_case(tag, mutate, target_days=3):
    data = [mutate(dict(r)) for r in rows]
    path = ROOT / "scratch" / f"_t146_{tag}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in data) + "\n", encoding="utf-8")
    ok, s = VR.report(VR.load(str(path)), target_days=target_days)
    print(f"[{tag}] ok={ok} verdict={s.get('verdict')!r} strict={s.get('strict_verdict')!r} "
          f"problems={len(s.get('problems') or [])} infos={len(s.get('infos') or [])}")
    for p in (s.get("problems") or []):
        print(f"      PROBLEM {p}")
    return s


def bad_window_day(day, label=None, check="watered_outdoor"):
    def mut(r):
        if r.get("event") == "day_end" and r.get("day") == [1, "summer", day]:
            r["checks"] = dict(r.get("checks") or {}, **{check: False})
            r["verified"] = False
            if label is not None:
                r["day"] = [1, label, day]
        return r
    return mut


print("=== C1: 窗口日 summer 21 watered_outdoor=false（干净标签）===")
run_case("c1", bad_window_day(21))
print("\n=== C2: 同上但把 summer 21 标签改脏（summer]21）===")
run_case("c2", bad_window_day(21, label="summer]21"))
print("\n=== C3: 同上但把窗口日 summer 21 改名成已知历史名（summer 18）===")
run_case("c3", bad_window_day(21, label="summer 18"))
print("\n=== E: 伪造 verified=true 但 checks.watered_outdoor=false（自述与九项不自洽）===")


def lie(r):
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 21]:
        r["checks"] = dict(r.get("checks") or {}, watered_outdoor=False)
        r["verified"] = True
    return r


run_case("e", lie)
print("\n=== F: 把 summer 20 的 no_unmet_stages 改 false 但 verified 仍 true ===")


def lie2(r):
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 20]:
        r["checks"] = dict(r.get("checks") or {}, no_unmet_stages=False)
        r["verified"] = True
    return r


run_case("f", lie2)

print("\n=== summer 20 现场：该日全部事件 ===")
for i, r in enumerate(rows):
    if r.get("event") == "day_end" and r.get("day") == [1, "summer", 20]:
        start = None
        for j in range(i, -1, -1):
            if rows[j].get("event") == "day_start":
                start = j
                break
        for j in range(start, i + 1):
            e = rows[j]
            line = json.dumps(e, ensure_ascii=False)
            print(f"  L{j+1} {line[:520]}")
        break

print("\n=== summer 21 的 day_start（翌日晨间状态，用于交叉核对 summer 20 是否留下活）===")
for i, r in enumerate(rows):
    if r.get("event") == "day_start" and r.get("day") == [1, "summer", 21]:
        print(f"  L{i+1} {json.dumps(r, ensure_ascii=False)[:900]}")
        break
print("\nDONE2")
