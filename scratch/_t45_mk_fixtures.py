# -*- coding: utf-8 -*-
"""task-45 夹具生成器：造一套**自洽的三源**（绿）与 4 个负例（红），用来证明对账器不会恒绿。

产物（全在 scratch/ 下，不碰 tools/、不碰游戏/桥）：
  scratch/_t45_fx/ok/            绿夹具：3 天账本 + SMAPI(3 NewDay/3 Save) + 存档 XML(day 29) + snapshots
  scratch/_t45_fx/neg-A-ledger-cut/   负例 A：删掉第 2 天的 day_end          ⇒ 期望 RED
  scratch/_t45_fx/neg-B-smapi-short/  负例 B：SMAPI 少一条 NewDay           ⇒ 期望 RED
  scratch/_t45_fx/neg-C-no-save/      负例 C：SMAPI 无 Save + 存档 mtime 不动 ⇒ 期望 RED
  scratch/_t45_fx/neg-D-save-behind/  负例 D：存档 XML 天落后 2 天（mtime 更新）⇒ 期望 RED

用法：& $py scratch/_t45_mk_fixtures.py   （PYTHONUTF8=1）
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "scratch" / "_t45_fx"
SAVE_NAME = "Wahaha_450799035"

SMAPI_HEADER = [
    "[20:00:00 INFO SMAPI] SMAPI 4.5.2 with Stardew Valley 1.6.15 build 24356 on Microsoft Windows",
    "[20:00:00 INFO SMAPI] Mods loaded: 1 mods",
    "[20:00:00 INFO SMAPI]       AgentFarm.Bridge 0.7.24 by deputy",
]


def smapi_session(newday_times, with_save=True, drop_newday_idx=None, drop_save_idx=None):
    """按 `20:10:00` 这种时钟造 SMAPI 行；`drop_save_idx` 保留 NewDay 但**不写 Save**（模拟游戏自身跳过保存）。"""
    drop_save = set()
    if drop_save_idx is not None:
        drop_save = set(drop_save_idx if isinstance(drop_save_idx, (tuple, list, set)) else (drop_save_idx,))
    lines = list(SMAPI_HEADER)
    ln = len(lines)
    for i, t in enumerate(newday_times):
        if drop_newday_idx is not None and i == drop_newday_idx:
            continue
        hh, mm, ss = (int(x) for x in t.split(":"))
        def stamp(offset=0):
            s = ss + offset
            m, s2 = mm + s // 60, s % 60
            h, m2 = hh + m // 60, m % 60
            return f"{h:02d}:{m2:02d}:{s2:02d}"
        lines.append(f"{ln+1}: [{stamp(0)} TRACE SMAPI] Synchronizing 'NewDay' task...")
        ln += 1
        if with_save and i not in drop_save:
            lines.append(f"{ln+1}: [{stamp(0)} TRACE SMAPI] Context: before save.")
            ln += 1
            lines.append(f"{ln+1}: [{stamp(0)} TRACE game] SaveGame.Save() called.")
            ln += 1
            lines.append(f"{ln+1}: [{stamp(0)} TRACE SMAPI] Synchronizing 'Save' task...")
            ln += 1
            lines.append(f"{ln+1}: [{stamp(2)} TRACE game] SaveGame.Save() completed without exceptions.")
            ln += 1
            lines.append(f"{ln+1}: [{stamp(3)} TRACE SMAPI] Context: after save, starting spring X Y1.")
            ln += 1
    lines.append(f"{ln+1}: [21:30:00 TRACE SMAPI] Disposing...")
    return lines


def ledger_lines(cut_second_day_end=False, drop_sleep_idx=None, midrun_open_last=False):
    """按 run5 的**真实形状**造账本：`day_end` 用 `day_after` 表示跨到的那天、`final.day` 是这一天本身，
    没有 `cross_day`；另加独立的 ok `sleep` 事件（before/after 天）供账本内互证。
    `drop_sleep_idx` 保留 day_end（仍自称 sleep）但**删掉 sleep 事件** ⇒ 期望判红（账本内互证失败）。
    `midrun_open_last=True` 模拟"跑批进行中"：最后一天只有 day_start、没有 day_end、也没有 finish。"""
    drop_sleep = set()
    if drop_sleep_idx is not None:
        drop_sleep = set(drop_sleep_idx if isinstance(drop_sleep_idx, (tuple, list, set)) else (drop_sleep_idx,))
    out = []
    days = [([1, "spring", 26], [1, "spring", 27], 14),
            ([1, "spring", 27], [1, "spring", 28], 14),
            ([1, "spring", 28], [1, "spring", 29], 114)]
    t = 1.0
    for i, (start, end, money) in enumerate(days):
        out.append({"event": "day_start", "t": round(t, 2), "day": start, "money": money})
        t += 1.0
        if midrun_open_last and i == len(days) - 1:
            continue
        if i == 0:
            out.append({"event": "sell", "t": round(t, 2), "day": start, "ok": True,
                        "qid": "(O)24", "stack": 1, "before": {"shippingBin": {"count": 0}},
                        "after": {"shippingBin": {"count": 1}}})
            t += 1.0
        if cut_second_day_end and i == 1:
            t += 100.0
            continue
        if i not in drop_sleep:
            out.append({"event": "sleep", "t": round(t, 2), "ok": True, "code": "ok",
                        "reason": f"已跨日：spring {start[2]}日 → spring {end[2]}日（已踩触发格 (10, 9)："
                                  "回执 ui_modal = 命中信号）",
                        "before": {"day": start, "timeOfDay": 1400, "isInBed": False},
                        "after": {"day": end, "timeOfDay": 600, "isInBed": True}})
            t += 1.0
        out.append({"event": "day_end", "t": round(t, 2), "day": start, "day_after": end,
                    "final": {"day": start, "money": money}, "ended_by": "sleep",
                    "ended_reason": "no_work:到点了", "verified": True,
                    "checks": {"slept_by_us": True, "no_hard_failures": True}})
        t += 100.0
    if not midrun_open_last:
        out.append({"event": "finish", "t": round(t, 2), "code": 0, "verified_streak": 3,
                    "actions": 30, "minutes": 5.3})
    return out

def save_xml(day, money):
    return (f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<SaveGame>\n  <player>\n"
            f"    <name>Wahaha</name>\n    <money>{money}</money>\n  </player>\n"
            f"  <year>1</year>\n  <currentSeason>spring</currentSeason>\n"
            f"  <dayOfMonth>{day}</dayOfMonth>\n  <gameVersion>1.6.15</gameVersion>\n</SaveGame>\n")


def snapshots(no_save_progress=False):
    start = {"tag": "start", "at": "2026-10-13T20:00:00",
             "save_main": {"exists": True, "size": 1000, "mtime": "2026-10-13T20:00:00.000"},
             "smapi_lines": 3, "smapi_newday": 0, "smapi_save": 0}
    end = {"tag": "end", "at": "2026-10-13T21:20:00",
           "save_main": {"exists": True, "size": 2000, "mtime": "2026-10-13T21:10:02.000"},
           "smapi_lines": 20, "smapi_newday": 3, "smapi_save": 3}
    if no_save_progress:
        end["save_main"] = dict(start["save_main"])
        end["smapi_newday"] = 3
        end["smapi_save"] = 3
    return [start, end]


def write_case(name, *, ledger=None, smapi_lines=None, save_day=29, save_money=114,
               snaps=None, ledger_then_save_gap=False):
    d = FX / name
    if d.exists():
        shutil.rmtree(d)
    sd = d / "Saves" / SAVE_NAME          # 星露谷的存档"目录"名与主存档文件名同名
    sd.mkdir(parents=True)
    led = d / "ledger.jsonl"
    led.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (ledger or [])),
                   encoding="utf-8", newline="\n")
    if ledger_then_save_gap:
        time.sleep(0.05)
    (d / "smapi.txt").write_text("\n".join(smapi_lines or []) + "\n", encoding="utf-8", newline="\n")
    (sd / SAVE_NAME).write_text(save_xml(save_day, save_money), encoding="utf-8", newline="\n")
    (sd / "SaveGameInfo").write_text("<SaveGameInfo><money>%d</money></SaveGameInfo>\n" % save_money,
                                     encoding="utf-8", newline="\n")
    shutil.copyfile(sd / SAVE_NAME, sd / f"{SAVE_NAME}_old")
    shutil.copyfile(sd / "SaveGameInfo", sd / "SaveGameInfo_old")
    (d / "baseline.json").write_text(json.dumps({"money": 114, "day": [1, "spring", 29],
                                                 "activeMenu": "ShippingMenu"}, ensure_ascii=False),
                                     encoding="utf-8")
    snap_path = d / "snapshots.jsonl"
    snap_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                                 for x in (snaps if snaps is not None else snapshots())),
                         encoding="utf-8", newline="\n")
    return d


def main():
    FX.mkdir(parents=True, exist_ok=True)
    nd = ["20:10:00", "20:40:00", "21:10:00"]
    ok = write_case("ok", ledger=ledger_lines(), smapi_lines=smapi_session(nd))
    print(f"[fx] 绿夹具 : {ok}")
    a = write_case("neg-A-ledger-cut", ledger=ledger_lines(cut_second_day_end=True),
                   smapi_lines=smapi_session(nd), ledger_then_save_gap=True)
    print(f"[fx] 负例 A : {a}（删掉第 2 天 day_end）")
    b = write_case("neg-B-smapi-short", ledger=ledger_lines(),
                   smapi_lines=smapi_session(nd, drop_newday_idx=1), ledger_then_save_gap=True)
    print(f"[fx] 负例 B : {b}（SMAPI 少一条 NewDay）")
    c = write_case("neg-C-no-save", ledger=ledger_lines(),
                   smapi_lines=smapi_session(nd, with_save=False),
                   snaps=snapshots(no_save_progress=True), ledger_then_save_gap=True)
    print(f"[fx] 负例 C : {c}（SMAPI 无 Save + 存档 mtime 不动）")
    dd = write_case("neg-D-save-behind", ledger=ledger_lines(), smapi_lines=smapi_session(nd),
                    save_day=27, ledger_then_save_gap=True)
    print(f"[fx] 负例 D : {dd}（存档 XML 天落后 2 天且 mtime 更新）")
    e = write_case("pos-E-save-one-day-behind", ledger=ledger_lines(), smapi_lines=smapi_session(nd),
                   save_day=28, ledger_then_save_gap=True)
    print(f"[fx] 正例 E : {e}（存档只落后 1 天 ⇒ 期望 GREEN + 需人工确认 info）")
    g = write_case("pos-G-one-day-no-save", ledger=ledger_lines(),
                   smapi_lines=smapi_session(nd, drop_save_idx=1), ledger_then_save_gap=True)
    print(f"[fx] 正例 G : {g}（只有 1 次跨日没落盘（游戏自身跳过保存）⇒ 期望 GREEN + save_skipped_by_game info）")
    f = write_case("neg-F-two-days-no-save", ledger=ledger_lines(),
                   smapi_lines=smapi_session(nd, drop_save_idx=(1, 2)), ledger_then_save_gap=True)
    print(f"[fx] 负例 F : {f}（连续 2 次跨日没落盘 ⇒ 期望 RED）")
    h = write_case("neg-H-cross-day-without-sleep-event", ledger=ledger_lines(drop_sleep_idx=1),
                   smapi_lines=smapi_session(nd), ledger_then_save_gap=True)
    print(f"[fx] 负例 H : {h}（day_end 自称 sleep 且天数 +1，但账本里没有对应的 ok sleep 事件 ⇒ 期望 RED）")
    i_case = write_case("pos-I-midrun-last-day-open", ledger=ledger_lines(midrun_open_last=True),
                        smapi_lines=smapi_session(nd[:2]), ledger_then_save_gap=True)
    print(f"[fx] 正例 I : {i_case}（跑批进行中：最后一天没 day_end、没有 finish ⇒ 期望 GREEN + info）")
    print("[fx] 用法：--ledger <dir>/ledger.jsonl --smapi <dir>/smapi.txt "
          "--save-dir <dir>/Saves/Wahaha_450799035 --snapshots <dir>/snapshots.jsonl "
          "--baseline <dir>/baseline.json --date 2026-10-13")


if __name__ == "__main__":
    main()
