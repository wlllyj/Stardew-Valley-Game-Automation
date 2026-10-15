"""task-86 对抗：新口径（尾部窗口 / history_problems）能不能把"窗口内"的问题洗成历史？

自造账本（不用 journal-green 的现成文件，自建天数/字段以便控制窗口）。
每个变体都跑 旧口径（_t86_tool_old.py）与 新口径（_t86_tool_new.py），打印 rc / 问题数 / 历史数
以及关键问题的原文。

用法：python scratch/_t86_adv.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(ROOT, "scratch", "_t86_tool_old.py")
NEW = os.path.join(ROOT, "scratch", "_t86_tool_new.py")
OUT = os.path.join(ROOT, "scratch")

OK_CHECKS = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
             "no_unmet_stages": True, "crops_watered": True, "watered_outdoor": True,
             "day_justified": True}


def day_rows(start: list, after: list, *, verified: bool = True, ended_by: str = "sleep",
             checks: dict | None = None, watermark: bool = True,
             reason: str = "night:到点了", leftover: int = 0, ok_steps: int = 32,
             t0: float = 1.0, key_season: str | None = None) -> list[dict]:
    """一天：day_start / decision / stage / sleep / day_end。

    `key_season` 非 None ⇒ 把 day_start 的 season 改成它（用于"改 key"对抗）。
    `watermark=False` ⇒ 那一天浇水没做完（verified 也置 False）。
    """
    d = list(start)
    if key_season is not None:
        d = [d[0], key_season, d[2]]
    dd = list(d)
    chk = dict(checks if checks is not None else OK_CHECKS)
    rows = [
        {"t": t0, "event": "day_start", "day": d,
         "final": {"day": d, "stamina": 270.0, "crops": 32, "unwatered_crops": 32, "money": 200}},
        {"t": t0 + 5.0, "event": "decision", "day": d, "boundary": "new_day",
         "source": "llm", "llm": True,
         "intents": [{"task": "water_area", "area_hint": "anchor:field_ne"}]},
        {"t": t0 + 300.0, "event": "stage", "day": d, "stage": "water_area", "tiles": 32,
         "ok": ok_steps, "skipped": 0, "failed": 0, "stopped": "", "leftover": leftover},
        {"t": t0 + 500.0, "event": "sleep", "day": d, "ok": True,
         "before": {"day": d, "timeOfDay": 2200},
         "after": {"day": list(after), "timeOfDay": 600}},
        {"t": t0 + 520.0, "event": "day_end", "day": dd, "ended_by": ended_by,
         "ended_reason": reason, "verified": verified,
         "final": {"day": list(after), "timeOfDay": 600, "stamina": 270.0, "crops": 33,
                   "unwatered_crops": 0 if watermark else 9, "money": 200},
         "checks": chk,
         "day_text": f"{d[1]} {d[2]}：phase water_area...",
         "ok_steps": ok_steps if watermark else 0, "skipped_steps": 0, "failed_steps": 0,
         "stages": [{"stage": "water_area", "tiles": 32, "leftover": leftover,
                     "ok": ok_steps, "attempted": 32}],
         "outcomes": [], "notes": []},
    ]
    return rows


def finish(streak: int, days: int) -> dict:
    return {"t": 9000.0, "event": "finish", "code": 0 if streak >= days else 1,
            "verified_streak": streak, "days": days, "actions": 96, "minutes": 10.0}


def bad_day(start: list, after: list, t0: float, *, skip_sleep: bool = False,
            ended_by: str = "sleep") -> list[dict]:
    """坏日：浇水没做完（verified=False）；ended_by="sleep" ⇒ 它在流水账里仍是"睡过去的坏日"。"""
    chk = dict(OK_CHECKS)
    chk["watered_outdoor"] = False
    chk["crops_watered"] = False
    rows = day_rows(start, after, verified=False, ended_by=ended_by, checks=chk,
                    watermark=False, leftover=9, t0=t0)
    return rows


def day_rows_leftover_fix(rows: list[dict], leftover: int) -> list[dict]:
    for r in rows:
        if r.get("event") == "stage":
            r["leftover"] = leftover
        if r.get("event") == "day_end":
            r["stages"][0]["leftover"] = leftover
    return rows


def write_ledger(tag: str, rows: list[dict], days: int, streak: int) -> str:
    path = os.path.join(OUT, f"review-t86-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps(finish(streak, days), ensure_ascii=False) + "\n")
    return path


def run(tool: str, path: str, days: int) -> tuple[int, dict | None, str]:
    p = subprocess.run([sys.executable, tool, "--journal", path, "--days", str(days), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return p.returncode, json.loads(p.stdout), p.stdout
    except Exception:
        return p.returncode, None, p.stdout + p.stderr


def spring(n: int) -> list:
    return ["1", "spring", n]


def build_window_ok_history_bad(n_bad: int = 5) -> tuple[list[dict], int, int]:
    rows: list[dict] = []
    day = 5
    for i in range(n_bad):  # 坏日：浇水没做完，睡得着但没达标
        rows += bad_day(spring(day), spring(day + 1), t0=1.0 + i * 600)
        day += 1
    for i in range(3):  # 尾部 3 天全绿
        rows += day_rows(spring(day), spring(day + 1), t0=1.0 + (n_bad + i) * 600)
        day += 1
    return rows, 3, 3


VARIANTS: dict[str, tuple[list[dict], int, int]] = {}


def register(tag: str, rows: list[dict], days: int, streak: int) -> None:
    VARIANTS[tag] = (rows, days, streak)


def main() -> int:
    # A1：尾部 3 天全绿 + 前面 5 天全坏（设计允许的窗口）
    register("a1-window-ok-history-bad", *build_window_ok_history_bad(5))
    # A6：27 天坏 + 3 天绿（"系统性缺陷在窗口外累积"）
    register("a6-systematic-27-bad-3-clean", *build_window_ok_history_bad(27))

    # A2：窗口内中间那天有"账目自相矛盾"（verified=True 但 no_unmet_stages 与 leftover 不一致）
    rows: list[dict] = []
    rows += day_rows(spring(10), spring(11), t0=1.0)
    mid = day_rows(spring(11), spring(12), t0=601.0, leftover=5)
    for r in mid:
        if r.get("event") == "day_end":
            r["checks"]["no_unmet_stages"] = True          # 谎报：有 leftover 却说没遗留
            r["verified"] = True
    rows += mid
    rows += day_rows(spring(12), spring(13), t0=1201.0)
    register("a2-inwindow-contradiction", rows, 3, 3)

    # A3：run 停在坏的一天（尾部一天坏）⇒ streak=0 ⇒ 不降级
    rows = []
    rows += day_rows(spring(10), spring(11), t0=1.0)
    rows += day_rows(spring(11), spring(12), t0=601.0)
    rows += day_rows(spring(12), spring(13), t0=1201.0)
    rows += bad_day(spring(13), spring(14), t0=1801.0, ended_by="pass_out")
    register("a3-stop-on-bad-day", rows, 3, 0)

    # A4a：窗口内矛盾（正常 key）—— 期望红
    rows = []
    rows += day_rows(spring(10), spring(11), t0=1.0)
    mid = day_rows(spring(11), spring(12), t0=601.0, leftover=5)
    for r in mid:
        if r.get("event") == "day_end":
            r["checks"]["no_unmet_stages"] = True
            r["verified"] = True
    rows += mid
    rows += day_rows(spring(12), spring(13), t0=1201.0)
    register("a4a-inwindow-contradiction-normal-key", rows, 3, 3)

    # A4b：同一本账，只把中间那天的 day_start season 改成 "spring]x"（改 key 骗降级）
    rows = []
    rows += day_rows(spring(10), spring(11), t0=1.0)
    mid = day_rows(spring(11), spring(12), t0=601.0, leftover=5, key_season="spring]x")
    for r in mid:
        if r.get("event") == "day_end":
            r["checks"]["no_unmet_stages"] = True
            r["verified"] = True
    rows += mid
    rows += day_rows(spring(12), spring(13), t0=1201.0)
    register("a4b-inwindow-contradiction-injected-key", rows, 3, 3)

    # A5：全局问题（bridge_down 事件）不许被历史化 —— 用 A1 的 8 天 + 早期 bridge_down
    rows, days, streak = build_window_ok_history_bad(5)
    rows = rows[:]
    rows.insert(0, {"t": 0.5, "event": "bridge_down", "note": "合成：早期桥掉线"})
    register("a5-global-event-with-clean-window", rows, days, streak)

    print(f"{'variant':<44}{'old_rc':<7}{'new_rc':<7}{'old_p':<6}{'new_p':<6}{'hist':<6}{'new_verdict'}")
    for tag, (rows, days, streak) in VARIANTS.items():
        path = write_ledger(tag, rows, days, streak)
        rco, o, _ = run(OLD, path, days)
        rcn, n, raw = run(NEW, path, days)
        print(f"{tag:<44}{rco:<7}{rcn:<7}"
              f"{len(o['problems']) if o else -1:<6}{len(n['problems']) if n else -1:<6}"
              f"{len(n.get('history_problems', [])) if n else -1:<6}"
              f"{n['verdict'] if n else 'PARSE_FAIL'}")

    # A4a/A4b 原文对照（打穿与否的判据）
    for tag in ("a4a-inwindow-contradiction-normal-key",
                "a4b-inwindow-contradiction-injected-key"):
        path = os.path.join(OUT, f"review-t86-{tag}.jsonl")
        rco, o, _ = run(OLD, path, 3)
        rcn, n, _ = run(NEW, path, 3)
        print(f"\n===== {tag} =====")
        print(f"旧 rc={rco} 问题 {json.dumps(o['problems'], ensure_ascii=False)}")
        print(f"新 rc={rcn} verdict={n['verdict']} streak={n['verified_streak_tail']}")
        print(f"新 问题 {json.dumps(n['problems'], ensure_ascii=False)}")
        print(f"新 历史 {json.dumps(n.get('history_problems', []), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
