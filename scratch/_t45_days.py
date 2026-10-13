"""只读：把 run5 账本里每个 day_end 的关键判据原样打出来（task-45 独立复算用）。

用途：核对 tools/verify-run3.py 的结论（例如 spring 26 是否只有浇水一项不过），
不改任何生产文件、不碰游戏/桥。
"""
import json
import sys
from pathlib import Path

LEDGER = Path(sys.argv[1] if len(sys.argv) > 1 else
              r"logs\longrun-3day-llm-run5.jsonl")


def main() -> int:
    recs = []
    for i, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            recs.append((i, json.loads(line)))
        except json.JSONDecodeError as exc:
            print(f"坏行 {i}: {exc}")
    print(f"账本 {LEDGER}：{len(recs)} 行")
    for i, r in recs:
        ev = r.get("event")
        if ev == "goto_farm":
            print(f"  L{i} goto_farm: ok={r.get('ok')} where={r.get('where')} code={r.get('code')}")
        elif ev == "farm_evidence_unavailable":
            print(f"  L{i} farm_evidence_unavailable: {json.dumps(r, ensure_ascii=False)[:220]}")
    for i, r in recs:
        if r.get("event") != "day_end":
            continue
        day = r.get("final", {}).get("day")
        print(f"\n=== L{i} day_end day={day} day_after={r.get('day_after')} "
              f"ended_by={r.get('ended_by')} verified={r.get('verified')}")
        print(f"    ended_reason: {str(r.get('ended_reason'))[:200]}")
        print(f"    checks: {json.dumps(r.get('checks'), ensure_ascii=False)}")
        print(f"    final_water: {json.dumps(r.get('final_water'), ensure_ascii=False)}")
        print(f"    failed_steps={r.get('failed_steps')} ok_steps={r.get('ok_steps')} "
              f"skipped_steps={r.get('skipped_steps')} plots={r.get('plots')}")
        for s in (r.get("stages") or []):
            print(f"    stage {s.get('stage')}: tiles={s.get('tiles')} ok={s.get('ok')} "
                  f"failed={s.get('failed')} failed_any={s.get('failed_any')} "
                  f"leftover={s.get('leftover')} env_block={s.get('env_block')} "
                  f"inconclusive={s.get('inconclusive')} round={s.get('round')}")
        for n in (r.get("notes") or []):
            print(f"    note: {str(n)[:180]}")
        # 睡前最后一轮"守卫为什么说没活"的原始证据：decision/outcome/sleep 记录
        for j, r2 in recs:
            if i - 12 <= j <= i and r2.get("event") in ("sleep", "decision", "outcome", "review"):
                keys = ("event", "task", "chosen", "kind", "reason", "reasons", "raw",
                        "ended_by", "before", "after", "ok", "note", "text")
                slim = {k: r2.get(k) for k in keys if k in r2}
                print(f"    L{j} {json.dumps(slim, ensure_ascii=False)[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
