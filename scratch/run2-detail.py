# -*- coding: utf-8 -*-
"""run2 账本逐条细看：紧凑渲染 + 单独导出过大的字段（plots/outcomes/notes）。

输出：logs/run2-journal-detail.txt（逐条一行）+ logs/run2-day-end-88.json（原始大记录）
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
JOURNAL = REPO / "logs" / "longrun-3day-llm-run2.jsonl"
OUT_TXT = REPO / "logs" / "run2-journal-detail.txt"

OUT: list[str] = []

SMALL = ("ok", "code", "reason", "stage", "stages", "zone", "anchor", "tile", "day", "day_text",
         "verdict", "llm", "intent", "task", "target", "from", "to", "count", "note", "kind",
         "switched", "exhausted", "n", "stats", "before", "after", "verified", "ended_by", "ended_reason",
         "checks", "policy", "decision", "source", "why", "goal", "energy", "stamina")
SKIP = ("plots", "outcomes", "tiles", "notes", "final")


def p(t: str = "") -> None:
    print(t, flush=True)
    OUT.append(str(t))


def clip(o, n: int = 150) -> str:
    s = json.dumps(o, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def render(i: int, r: dict) -> str:
    parts = [f"[{i:3d}]", str(r.get("event")), f"t={r.get('t')}"]
    for k, v in r.items():
        if k in ("event", "t") or k in SKIP:
            continue
        if k in SMALL or not isinstance(v, (dict, list)):
            parts.append(f"{k}={clip(v)}")
    extra = [k for k in r if k in SKIP]
    if extra:
        parts.append("+big:" + ",".join(f"{k}({len(r[k]) if isinstance(r[k], (list, dict)) else '?'})" for k in extra))
    return "  ".join(parts)


def main() -> int:
    recs = [json.loads(l) for l in JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    p(f"== 逐条（{len(recs)} 条）==")
    for i, r in enumerate(recs):
        p(render(i, r))

    for idx in (88, 91):
        if idx < len(recs):
            (REPO / "logs" / f"run2-day-end-{idx}.json").write_text(
                json.dumps(recs[idx], ensure_ascii=False, indent=2), encoding="utf-8")

    # day_end #88 的 plots / 失败格
    if len(recs) > 88:
        r = recs[88]
        p("")
        p("--- day_end[88] checks / plots ---")
        p("checks: " + clip(r.get("checks"), 300))
        for pl in (r.get("plots") or []):
            p("plot: " + clip({k: v for k, v in pl.items() if k != "note"}, 200))
            p("  note: " + clip(pl.get("note"), 400))
        p("")
        p(f"--- day_end[88] outcomes（{len(r.get('outcomes') or [])} 条）---")
        for o in (r.get("outcomes") or []):
            p("  " + clip(o, 250))
        p("")
        p(f"--- day_end[88] notes（{len(r.get('notes') or [])} 条）---")
        for n in (r.get("notes") or []):
            p("  " + clip(n, 300))
        p("")
        p("--- day_end[88] stats/stages 其余键 ---")
        for k, v in r.items():
            if k not in ("plots", "outcomes", "notes", "final"):
                p(f"  {k} = {clip(v, 400)}")

    # LLM 决策
    p("")
    p("--- llm=true 的记录 ---")
    for i, r in enumerate(recs):
        if r.get("llm") is True:
            p(f"  [{i}] " + clip(r, 700))

    p("")
    p("--- decision 类记录（全部）---")
    for i, r in enumerate(recs):
        if r.get("event") == "decision":
            p(f"  [{i}] " + clip(r, 400))

    p("")
    p("--- outcome 类记录（全部）---")
    for i, r in enumerate(recs):
        if r.get("event") == "outcome":
            p(f"  [{i}] " + clip(r, 300))

    p("")
    p("--- blocked 类记录（全部）---")
    for i, r in enumerate(recs):
        if r.get("event") == "blocked":
            p(f"  [{i}] " + clip(r, 300))

    p("")
    p("--- policy / plot_exhausted / refill / review / day_start ---")
    for i, r in enumerate(recs):
        if r.get("event") in ("policy", "plot_exhausted", "refill", "review", "day_start", "intent_verdict", "intent_vetoed"):
            p(f"  [{i}] " + clip(r, 300))

    OUT_TXT.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
