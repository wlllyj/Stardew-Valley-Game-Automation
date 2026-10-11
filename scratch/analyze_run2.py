# -*- coding: utf-8 -*-
"""汇总 logs/longrun-3day-llm-run2.jsonl：逐日、动作成败、失败格、LLM 调用、睡觉尝试。

日志只是"代码自己说了什么"，最终结论仍以 observe 差分为准。本脚本不做判断，只做归纳。
输出：logs/run2-journal-summary.txt
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JOURNAL = REPO / "logs" / "longrun-3day-llm-run2.jsonl"
OUT_TXT = REPO / "logs" / "run2-journal-summary.txt"

OUT: list[str] = []


def p(t: str = "") -> None:
    print(t, flush=True)
    OUT.append(str(t))


def clip(obj, n: int = 400) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


def disc_of(rec: dict) -> str:
    for k in ("event", "kind", "type", "record", "tag", "what"):
        v = rec.get(k)
        if isinstance(v, str) and v:
            return f"{k}={v}"
    return "keys=" + ",".join(sorted(rec.keys())[:8])


def main() -> int:
    if not JOURNAL.exists():
        p(f"[FATAL] 账本不存在：{JOURNAL}")
        _flush()
        return 2
    recs = []
    bad = 0
    for line in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    p(f"== 账本汇总 {JOURNAL} ==")
    p(f"记录数 {len(recs)}（无法解析 {bad} 行）")
    if not recs:
        _flush()
        return 0

    p("")
    p("--- 首条记录全文 ---")
    p(clip(recs[0], 1500))
    p("")
    p("--- 末条记录全文 ---")
    p(clip(recs[-1], 1500))

    p("")
    p("--- 记录类型计数 ---")
    for k, v in Counter(disc_of(r) for r in recs).most_common():
        p(f"  {v:5d}  {k}")

    # LLM 调用
    llm = [r for r in recs if any(r.get(k) is True for k in ("llm", "used_llm", "boundary_llm"))]
    llm2 = [r for r in recs if isinstance(r.get("decision"), dict) and r["decision"].get("llm") is True]
    p("")
    p(f"--- LLM：llm=true 的顶层记录 {len(llm)} 条；decision.llm=true 的记录 {len(llm2)} 条 ---")
    for r in llm2[:20]:
        p("  " + clip(r, 500))

    # 逐日
    p("")
    p("--- 逐日（按记录里出现的 day 聚合）---")
    byday = defaultdict(list)
    for r in recs:
        d = None
        for k in ("day", "clock", "date"):
            v = r.get(k)
            if isinstance(v, list) and len(v) == 3:
                d = tuple(v)
            elif isinstance(v, dict) and "day" in v:
                d = (v.get("year"), v.get("season"), v.get("day"))
        if d is None:
            for k in ("day_key", "on_day"):
                if isinstance(r.get(k), list) and len(r.get(k)) == 3:
                    d = tuple(r[k])
        byday[d].append(r)
    for d, rs in byday.items():
        p(f"  day={d}: {len(rs)} 条" + ("  | " + clip(rs[-1], 300) if rs else ""))

    # 失败动作
    p("")
    p("--- 失败/异常类记录 ---")
    fails = []
    for i, r in enumerate(recs):
        s = json.dumps(r, ensure_ascii=False)
        if any(t in s for t in ('"failed"', '"fail"', '"error"', '"ok": false', "'ok': False", "no_work", "sleep_failed")):
            fails.append((i, r))
    p(f"命中 {len(fails)} 条")
    for i, r in fails[:60]:
        p(f"  [{i}] " + clip(r, 420))

    # 睡觉相关
    p("")
    p("--- 睡觉相关记录 ---")
    for i, r in enumerate(recs):
        s = json.dumps(r, ensure_ascii=False)
        if "sleep" in s.lower():
            p(f"  [{i}] " + clip(r, 500))

    # 失败格
    p("")
    p("--- 提到格坐标的失败记录 ---")
    for i, r in fails:
        s = json.dumps(r, ensure_ascii=False)
        if "tile" in s or "x" in s:
            p(f"  [{i}] " + clip(r, 400))

    _flush()
    return 0


def _flush() -> None:
    try:
        OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
        OUT_TXT.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"[warn] 写 {OUT_TXT} 失败：{exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
