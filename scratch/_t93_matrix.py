# -*- coding: utf-8 -*-
"""task-93 负例矩阵：NIT-5 四态（存档 vs 账本收尾）+ 严格口径第二判决「只打印、不改 rc」。

自造夹具（不依赖 `_t45_fx`，全在 `scratch/_t93_fx/` 下）：
  t93-pos-newer1-finish   存档比账本收尾**新 1 天** + 账本有 `finish`  ⇒ 期望 exit 0 + info
  t93-neg-newer1-nofinish 同上但**删掉 finish**（跑批被中断）          ⇒ 期望 exit 1 + problem
  t93-neg-newer2-finish   存档新 **2** 天 + 有 finish                  ⇒ 期望 exit 1 + problem
  t93-pos-behind1         存档**落后 1 天**                            ⇒ 期望 exit 0 + info（现状不变）
  t93-pos-run7-live       run7 真实样本（task-90 读数：problem 1）    ⇒ 期望 exit 0 + info + 严格口径段
  t93-run7-no-strict      同 run7 但 `--no-strict`                     ⇒ rc 与 problem/info 数**完全一致**

用法：& $py scratch/_t93_matrix.py      （PYTHONUTF8=1）
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "scratch" / "_t93_fx"
TOOL = ROOT / "scratch" / "_t45_three_source.py"
PY = sys.executable
SAVE_NAME = "Wahaha_450799035"

SMAPI_HEADER = [
    "[20:00:00 INFO SMAPI] SMAPI 4.5.2 with Stardew Valley 1.6.15 build 24356 on Microsoft Windows",
    "[20:00:00 INFO SMAPI] Mods loaded: 1 mods",
    "[20:00:00 INFO SMAPI]       AgentFarm.Bridge 0.7.26 by deputy",
]


def smapi_lines(times):
    out = list(SMAPI_HEADER)
    ln = len(out)
    for t in times:
        hh, mm, ss = (int(x) for x in t.split(":"))
        out.append(f"{ln+1}: [{hh:02d}:{mm:02d}:{ss:02d} TRACE SMAPI] Synchronizing 'NewDay' task...")
        ln += 1
        out.append(f"{ln+1}: [{hh:02d}:{mm:02d}:{ss:02d} TRACE game] SaveGame.Save() called.")
        ln += 1
        out.append(f"{ln+1}: [{hh:02d}:{mm:02d}:{ss:02d} TRACE SMAPI] Synchronizing 'Save' task...")
        ln += 1
        out.append(f"{ln+1}: [{hh:02d}:{mm:02d}:{ss+2:02d} TRACE game] "
                   "SaveGame.Save() completed without exceptions.")
        ln += 1
        out.append(f"{ln+1}: [{hh:02d}:{mm:02d}:{ss+3:02d} TRACE SMAPI] Context: after save, "
                   "starting the next day.")
        ln += 1
    out.append(f"{ln+1}: [23:00:00 TRACE SMAPI] Disposing...")
    return out


def ledger(days, finish=True):
    """run5/run7 的真实形状：`final.day` 是这一天、`day_after` 是跨到的那天，另加 ok `sleep` 事件。"""
    out = []
    t = 1.0
    for start, end, money in days:
        out.append({"event": "day_start", "t": round(t, 2), "day": start, "money": money})
        t += 1.0
        out.append({"event": "sleep", "t": round(t, 2), "ok": True, "code": "ok",
                    "reason": "已跨日（已踩触发格 (10, 9)：回执 ui_modal = 命中信号）",
                    "before": {"day": start, "timeOfDay": 1400, "isInBed": False},
                    "after": {"day": end, "timeOfDay": 600, "isInBed": True}})
        t += 1.0
        out.append({"event": "day_end", "t": round(t, 2), "day": start, "day_after": end,
                    "final": {"day": start, "money": money}, "ended_by": "sleep",
                    "ended_reason": "no_work:到点了", "verified": True,
                    "checks": {"slept_by_us": True, "no_hard_failures": True,
                               "crops_watered": True, "watered_outdoor": True,
                               "no_unmet_stages": True, "day_justified": True}})
        t += 100.0
    if finish:
        out.append({"event": "finish", "t": round(t, 2), "code": 0,
                    "verified_streak": len(days), "actions": 30, "minutes": 5.3})
    return out


def save_xml(season, day, money=114):
    return (f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<SaveGame>\n  <player>\n"
            f"    <name>Wahaha</name>\n    <money>{money}</money>\n  </player>\n"
            f"  <year>1</year>\n  <currentSeason>{season}</currentSeason>\n"
            f"  <dayOfMonth>{day}</dayOfMonth>\n  <gameVersion>1.6.15</gameVersion>\n</SaveGame>\n")


def write_case(name, *, events, smapi, save=(1, "spring", 29)):
    d = FX / name
    if d.exists():
        shutil.rmtree(d)
    sd = d / "Saves" / SAVE_NAME
    sd.mkdir(parents=True)
    (d / "ledger.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in events), encoding="utf-8", newline="\n")
    (d / "smapi.txt").write_text("\n".join(smapi) + "\n", encoding="utf-8", newline="\n")
    year, season, day = save
    (sd / SAVE_NAME).write_text(save_xml(season, day), encoding="utf-8", newline="\n")
    (sd / "SaveGameInfo").write_text("<SaveGameInfo><money>114</money></SaveGameInfo>\n", encoding="utf-8")
    shutil.copyfile(sd / SAVE_NAME, sd / f"{SAVE_NAME}_old")
    shutil.copyfile(sd / "SaveGameInfo", sd / "SaveGameInfo_old")
    return d


def run(case_dir: Path, extra=()):
    # 注意：对账器用「账本文件 mtime − 6h」过滤 SMAPI 行，而夹具是**现在**写的 ⇒ `--date` 必须用今天，
    # 否则夹具 SMAPI 行全部落在过滤窗口之前（曾导致 4 条假 problem）。
    today = _date.today().isoformat()
    cmd = [PY, str(TOOL),
           "--ledger", str(case_dir / "ledger.jsonl"),
           "--smapi", str(case_dir / "smapi.txt"),
           "--save-dir", str(case_dir / "Saves" / SAVE_NAME),
           "--snapshots", str(case_dir / "no_such_snapshots.jsonl"),
           "--baseline", str(case_dir / "no_such_baseline.json"),
           "--date", today, *extra]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def lines_of(out: str, tag: str):
    return [ln.strip() for ln in out.splitlines() if tag in ln]


def main() -> int:
    FX.mkdir(parents=True, exist_ok=True)
    times2 = ["20:10:00", "20:40:00"]
    # 账本：spring 27 → spring 28（收尾 spring 28 = 绝对日 28）
    end_at_28 = ledger([([1, "spring", 27], [1, "spring", 28], 14)])
    end_at_28_nofin = ledger([([1, "spring", 27], [1, "spring", 28], 14)], finish=False)
    end_at_summer1 = ledger([([1, "spring", 27], [1, "spring", 28], 14),
                             ([1, "spring", 28], [1, "summer", 1], 114)])
    cases = [
        # ① 存档新 1 天 + 有 finish ⇒ info（且 rc 必须仍为 0）
        ("t93-pos-newer1-finish", write_case("t93-pos-newer1-finish", events=end_at_28,
                                             smapi=smapi_lines(times2), save=(1, "summer", 1)), 0,
         "新 1 天", False, True),
        # ② 存档新 1 天 + 无 finish ⇒ problem
        ("t93-neg-newer1-nofinish", write_case("t93-neg-newer1-nofinish", events=end_at_28_nofin,
                                               smapi=smapi_lines(times2), save=(1, "summer", 1)), 1,
         "没有 `finish`", True, False),
        # ③ 存档新 2 天 + 有 finish ⇒ problem
        ("t93-neg-newer2-finish", write_case("t93-neg-newer2-finish", events=end_at_28,
                                             smapi=smapi_lines(times2), save=(1, "summer", 2)), 1,
         "新 2 天", True, False),
        # ④ 存档落后 1 天 ⇒ info（现状不变）
        ("t93-pos-behind1", write_case("t93-pos-behind1", events=end_at_summer1,
                                       smapi=smapi_lines(times2), save=(1, "spring", 28)), 0,
         "落后 1 天", False, True),
    ]
    bad = 0
    print("=" * 96)
    for name, d, expect, needle, want_problem, want_info in cases:
        r = run(d)
        hit_p = any(needle in x for x in lines_of(r.stdout, "[PROBLEM]"))
        hit_i = any(needle in x for x in lines_of(r.stdout, "[info]"))
        ok = (r.returncode == expect and
              (hit_p if want_problem else True) and (hit_i if want_info else True) and
              (not hit_p if not want_problem else True))
        if not ok:
            bad += 1
        print(f"[{name}] exit={r.returncode} 期望={expect} {'OK' if ok else '**MISMATCH**'} "
              f"| problem {len(lines_of(r.stdout, '[PROBLEM]'))} / info {len(lines_of(r.stdout, '[info]'))}")
        for x in lines_of(r.stdout, "[PROBLEM]"):
            print("    " + x)
        if want_info:
            for x in lines_of(r.stdout, "[info]"):
                if needle in x:
                    print("    " + x)

    # ⑤⑥ run7 真实样本：NIT-5 生效（problem 1 → 0）+ 严格口径段 + 只打印不改 rc
    run7 = ROOT / "logs" / "longrun-3day-llm-run7.jsonl"
    save_dir = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "Saves" / SAVE_NAME
    base_cmd = [PY, str(TOOL), "--ledger", str(run7),
                "--smapi", str(ROOT / "scratch" / "_t86_smapi_run7_live.txt"),
                "--save-dir", str(save_dir),
                "--snapshots", str(FX / "no_such_snapshots.jsonl"),
                "--baseline", str(ROOT / "logs" / "run7-baseline.json"),
                "--date", "2026-10-14"]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    r5 = subprocess.run(base_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    r6 = subprocess.run(base_cmd + ["--no-strict"], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", env=env)
    p5, p6 = len(lines_of(r5.stdout, "[PROBLEM]")), len(lines_of(r6.stdout, "[PROBLEM]"))
    i5, i6 = len(lines_of(r5.stdout, "[info]")), len(lines_of(r6.stdout, "[info]"))
    strict_block = lines_of(r5.stdout, "严格口径")
    hist_lines = lines_of(r5.stdout, "[窗口外历史]")
    saved_day = None
    try:
        txt = (save_dir / SAVE_NAME).read_text(encoding="utf-8", errors="replace")
        import re as _re
        saved_day = (int(_re.findall(r"<dayOfMonth>(\d+)</dayOfMonth>", txt)[-1]),
                     _re.findall(r"<currentSeason>(\w+)</currentSeason>", txt)[-1])
    except Exception as exc:  # noqa: BLE001
        saved_day = f"<读不到: {exc}>"
    ok5 = r5.returncode == 0 and p5 == 0 and bool(strict_block) and len(hist_lines) >= 1
    ok6 = (r5.returncode == r6.returncode and p5 == p6 and i5 == i6)
    if not ok5:
        bad += 1
    if not ok6:
        bad += 1
    print(f"[t93-pos-run7-live] exit={r5.returncode}（task-90 读数 problem 1） problem={p5} / info={i5} "
          f"| 存档 XML={saved_day} | 严格口径段 {len(strict_block)} 行 / 历史 {len(hist_lines)} 条 "
          f"{'OK' if ok5 else '**MISMATCH**'}")
    for x in lines_of(r5.stdout, "[PROBLEM]"):
        print("    " + x)
    for x in lines_of(r5.stdout, "[info]"):
        print("    " + x)
    for x in strict_block[:3] + hist_lines[:3]:
        print("    " + x)
    print(f"[t93-run7-no-strict] exit={r6.returncode} problem={p6} / info={i6} "
          f"⇒ 与上一条 {'完全一致（只打印、不改 rc）' if ok6 else '**不一致**'} {'OK' if ok6 else '**MISMATCH**'}")
    print("=" * 96)
    print(f"task-93 负例矩阵结论：{'全部符合期望' if bad == 0 else f'{bad} 个不符期望'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
