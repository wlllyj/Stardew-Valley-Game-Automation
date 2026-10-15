r"""task-97 D 段：run7 末态与经济闭环路径（只读账本，评估 run8"不做操作员预置"的风险）。

用法：`python scratch/_t97_run7.py [账本路径]`
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logs" / "longrun-3day-llm-run7.jsonl"


def moneyish(payload):
    """把 payload 里所有名字带 money/price/gold 的字段挑出来。"""
    out = {}
    if isinstance(payload, dict):
        for k, v in payload.items():
            if any(s in str(k).lower() for s in ("money", "price", "gold", "sell", "buy")):
                out[k] = v
            elif isinstance(v, dict):
                sub = moneyish(v)
                for kk, vv in sub.items():
                    out[f"{k}.{kk}"] = vv
    return out


def main():
    rows = [json.loads(ln) for ln in PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"账本：{PATH.name}  行数={len(rows)}")
    from collections import Counter
    print("事件计数：", dict(Counter(r.get("event") for r in rows)))

    days = {}
    for r in rows:
        ev = r.get("event")
        key = json.dumps(r.get("day"), ensure_ascii=False)
        if ev == "day_start":
            days[key] = {"start": r}
        elif ev == "day_end":
            days.setdefault(key, {})["end"] = r
    print(f"\n天数={len(days)}")
    for day, d in days.items():
        end = d.get("end") or {}
        checks = end.get("checks") or {}
        print(f"  {day}: ended_by={end.get('ended_by')!r} verified={end.get('verified')} "
              f"ok={end.get('ok_steps')} failed={end.get('failed_steps')} "
              f"watered_outdoor={checks.get('watered_outdoor')} "
              f"final_water={ {k: v for k, v in (end.get('final_water') or {}).items() if k in ('scope', 'tiles', 'crops', 'dry')} }")
        fw = end.get("final_water") or {}
        if fw.get("note"):
            print(f"      note={fw['note'][:200]}")

    fin = [r for r in rows if r.get("event") == "finish"]
    print("\nfinish：", json.dumps(fin[-1], ensure_ascii=False)[:600] if fin else "（无）")

    print("\n带钱/买卖字段的事件：")
    seen = 0
    for r in rows:
        p = moneyish(r.get("payload") if isinstance(r.get("payload"), dict) else r)
        if p:
            seen += 1
            if seen <= 40:
                print(f"  t={r.get('t')} event={r.get('event')} {json.dumps(p, ensure_ascii=False)[:300]}")
    print(f"  合计 {seen} 条")

    print("\n最后 12 条事件名：", [r.get("event") for r in rows[-12:]])


if __name__ == "__main__":
    main()
