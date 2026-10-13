# -*- coding: utf-8 -*-
"""task-45：**三源对账器**（账本 ↔ SMAPI 日志 ↔ 存档）—— deputy-lead 自写，只读。

为什么需要它：账本是"脑的自述"，SMAPI 是"游戏侧的事件时间线"，存档是"游戏自己落盘的真值"。
三者独立，才能把"脑自称跨了 3 天"变成"游戏确实跨了 3 天且落了盘"。

三源与判据
----------
* **账本**（jsonl）：逐日 `day_start.day` → `day_end.final.day` 必须**恰好 +1 天**（季节 28 天折算绝对日序）。
* **SMAPI**：`Synchronizing 'NewDay' task...` / `SaveGame.Save() called.` / `SaveGame.Save() completed ...`。
  账本每推进一天，就必须有一条 NewDay 与之配对（按时钟就近、且**单调**），且该 NewDay 之后 ≤`--save-grace`
  秒内要么有 `SaveGame.Save() completed`，要么存档 mtime 前进。
* **存档**：`Wahaha_450799035` / `SaveGameInfo`（含 `_old`）的 size/mtime，以及存档 XML 里的
  `<money>` / `<dayOfMonth>` / `<currentSeason>` / `<year>`（**游戏自己写的真值**）。
  账本收尾那天必须与存档 XML 的那天一致；若存档 mtime 早于账本收尾（落盘滞后）则降级为 info 并说明。
* **窗口 delta**（`--snapshots` 的 start/end 两行）：save size/mtime 必须前进、SMAPI 行数必须前进、
  `smapi_newday` 的增量必须 ≥ 账本跨日次数。

用法（只读，不碰游戏/桥）：
  & $py scratch/_t45_three_source.py                       # 默认看 run5
  & $py scratch/_t45_three_source.py --ledger scratch/_t45_fx/ledger.jsonl \
      --smapi scratch/_t45_fx/smapi.txt --save-dir scratch/_t45_fx/Saves/Wahaha_450799035 \
      --snapshots scratch/_t45_fx/snapshots.jsonl --date 2026-10-13
  & $py scratch/_t45_three_source.py --json

退出码：0=无问题（可能有 info）/ 1=发现 problem / 2=用法或 IO 错误 / 3=账本不存在（只跑 SMAPI+存档预检）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as _date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEASONS = ("spring", "summer", "fall", "winter")
DAYS_PER_SEASON = 28

SMAPI_DEFAULT = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SAVE_DEFAULT = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "Saves" / "Wahaha_450799035"

SMAPI_LINE = re.compile(r"^\s*(?:\d+:\s*)?\[(\d{2}):(\d{2}):(\d{2})\s+([A-Z]+)\s+([^\]]+)\]\s*(.*)$")


# --------------------------------------------------------------------------- 小工具
def ordinal(day) -> int | None:
    """`[year, season, dayOfMonth]` → 绝对日序（季节 28 天）。"""
    try:
        y, s, d = int(day[0]), str(day[1]).strip().lower(), int(day[2])
        return ((y - 1) * len(SEASONS) + SEASONS.index(s)) * DAYS_PER_SEASON + d
    except Exception:
        return None


def ordinal_str(day) -> str:
    return f"{day[0]}年 {day[1]} {day[2]}日" if isinstance(day, (list, tuple)) and len(day) >= 3 else repr(day)


def fmt_mtime(ts: float | None) -> str:
    return "-" if ts is None else datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.infos: list[str] = []
        self.oks: list[str] = []

    def problem(self, msg: str) -> None:
        self.problems.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def ok(self, msg: str) -> None:
        self.oks.append(msg)


# --------------------------------------------------------------------------- 三源
def load_ledger(path: Path, rep: Report):
    if not path.exists():
        return None
    recs: list[tuple[int, dict]] = []
    for ln, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            rep.problem(f"账本第 {ln} 行不是合法 JSON（跳过）")
            continue
        if isinstance(ev, dict):
            recs.append((ln, ev))
    days: list[dict] = []
    cur: dict | None = None
    finish: dict | None = None
    sells: list[dict] = []
    slept: list[dict] = []
    for ln, ev in recs:
        name = ev.get("event")
        if name == "day_start":
            cur = {"line": ln, "start_day": ev.get("day"), "start_money": ev.get("money"),
                   "start_t": ev.get("t"), "end_day": None, "final_day": None, "ended_by": None,
                   "end_t": None, "cross_day": False, "end_line": None}
            days.append(cur)
        elif name == "day_end" and cur is not None:
            final = ev.get("final") or {}
            cur["end_line"] = ln
            # run5 的真实形状：`final.day` = 这一天本身，`day_after` = 跨到的那一天 ⇒ 优先用 day_after
            cur["final_day"] = final.get("day") or ev.get("day")
            cur["end_day"] = ev.get("day_after") or final.get("day") or ev.get("day")
            cur["ended_by"] = ev.get("ended_by")
            cur["end_t"] = ev.get("t")
            cur["cross_day"] = bool(ev.get("cross_day"))
            cur["end_money"] = ev.get("money")
        elif name == "sleep":
            if ev.get("ok"):
                slept.append({"line": ln, "t": ev.get("t"),
                              "before": (ev.get("before") or {}).get("day"),
                              "after": (ev.get("after") or {}).get("day")})
        elif name == "finish":
            finish = {"line": ln, **{k: ev.get(k) for k in ("t", "code", "verified_streak", "actions", "minutes")}}
        elif name == "sell" and ev.get("ok"):
            sells.append({"line": ln, "day": ev.get("day"), "qid": ev.get("qid"),
                          "stack": ev.get("stack"), "after": ev.get("after")})
    return {"recs": recs, "days": days, "finish": finish, "sells": sells, "slept": slept,
            "path": path, "mtime": path.stat().st_mtime if path.exists() else None}


def load_smapi(path: Path, day_anchor: _date, rep: Report):
    if not path.exists():
        return None
    out = {"path": path, "lines": 0, "newday": [], "save_called": [], "save_done": [],
           "session_start": None, "mtime": path.stat().st_mtime}
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out["lines"] = len(raw)
    prev_time = None
    roll = timedelta(0)
    for ln, line in enumerate(raw, 1):
        m = SMAPI_LINE.match(line)
        if not m:
            continue
        hh, mm, ss = (int(m.group(i)) for i in (1, 2, 3))
        t = datetime.combine(day_anchor, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)
        if prev_time is not None and t + roll < prev_time:
            roll += timedelta(days=1)
        t = t + roll
        prev_time = t
        if out["session_start"] is None:
            out["session_start"] = t
        msg = m.group(6)
        rec = {"line": ln, "at": t, "text": msg.strip()}
        if "Synchronizing 'NewDay' task" in msg:
            out["newday"].append(rec)
        elif "SaveGame.Save() called" in msg:
            out["save_called"].append(rec)
        elif "SaveGame.Save() completed" in msg:
            out["save_done"].append(rec)
    return out


def load_save(save_dir: Path, rep: Report):
    if not save_dir.exists():
        return None
    out = {"dir": save_dir, "files": {}, "xml": {}}
    for name in ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old"):
        p = save_dir / name
        if p.exists():
            st = p.stat()
            out["files"][name] = {"size": st.st_size, "mtime": st.st_mtime}
    main = save_dir / "Wahaha_450799035"
    if main.exists():
        text = main.read_text(encoding="utf-8", errors="replace")
        for key, pat in (("money", r"<money>(-?\d+)</money>"),
                         ("day", r"<dayOfMonth>(\d+)</dayOfMonth>"),
                         ("season", r"<currentSeason>(\w+)</currentSeason>"),
                         ("year", r"<year>(\d+)</year>")):
            hits = re.findall(pat, text)
            out["xml"][key] = hits[-1] if hits else None
            out["xml"][f"{key}_hits"] = len(hits)
        if out["xml"].get("day") and out["xml"].get("season") and out["xml"].get("year"):
            out["xml"]["day_triple"] = [int(out["xml"]["year"]), str(out["xml"]["season"]).lower(),
                                        int(out["xml"]["day"])]
    return out


def load_snapshots(path: Path, start_tag: str, end_tag: str, rep: Report):
    if not path.exists():
        return None
    rows = []
    for ln, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rep.problem(f"快照第 {ln} 行不是合法 JSON")
    if not rows:
        return None
    start = next((r for r in rows if r.get("tag") == start_tag), rows[0])
    end = next((r for r in rows if r.get("tag") == end_tag), rows[-1])
    return {"rows": rows, "start": start, "end": end}


# --------------------------------------------------------------------------- 判据
def check_ledger_chain(led, rep: Report) -> list[dict]:
    """P1：逐日 day_start → day_end（run5 用 `day_after`）必须恰好 +1 天；
    并且"自称 slept"的跨日必须在账本里有对应的 ok `sleep` 事件（账本内互证）。
    返回跨日了的那些天。"""
    if led is None:
        return []
    advances = []
    if not led["days"]:
        rep.problem("账本里没有任何 day_start（对账无从谈起）")
        return advances
    for idx, d in enumerate(led["days"]):
        o0, o1 = ordinal(d["start_day"]), ordinal(d["end_day"])
        tag = ordinal_str(d["start_day"])
        if o1 is None:
            # 跑批进行中（还没有 finish）时最后一天当然没有 day_end ⇒ 记 info，不判红；
            # 收工后（有 finish）再缺就是真问题（负例 A：中间某天被截断，照样判红）。
            if led["finish"] is None and idx == len(led["days"]) - 1:
                rep.info(f"[{tag}] 账本还在跑（没有 finish）：最后一天还没有 day_end ⇒ 本次不判红"
                         "（最终对账请在 run 收工、finish 落账后重跑）")
                continue
            rep.problem(f"[{tag}] 这一天没有 day_end/day_after（账本被截断？行 {d['line']}）")
            continue
        step = o1 - o0
        if d["ended_by"] == "sleep":
            if step != 1:
                rep.problem(f"[{tag}] day_end 自称 ended_by=sleep，但天数不是恰好 +1："
                            f"{ordinal_str(d['start_day'])} → {ordinal_str(d['end_day'])}（行 {d['end_line']}）")
                continue
            # 账本内互证：ok sleep 事件的 before/after 天要正好是这一天
            match = [s for s in led["slept"]
                     if ordinal(s["before"]) == o0 and ordinal(s["after"]) == o1]
            if match:
                rep.ok(f"[{tag}] 跨日 +1 → {ordinal_str(d['end_day'])}"
                       f"（账本 sleep 事件行 {match[0]['line']} 自述 "
                       f"{ordinal_str(match[0]['before'])} → {ordinal_str(match[0]['after'])}）")
            else:
                rep.problem(f"[{tag}] 跨日 +1 但账本里没有对应的 ok sleep 事件"
                            f"（before/after 天对不上，行 {d['end_line']}）")
            advances.append(d)
        else:
            if step != 0:
                rep.info(f"[{tag}] ended_by={d['ended_by']}（非 sleep）但天数前进了 {step} 天"
                         f"（{ordinal_str(d['start_day'])} → {ordinal_str(d['end_day'])}）")
            rep.info(f"[{tag}] 未跨日（ended_by={d['ended_by']}）⇒ 不要求 SMAPI NewDay")
    return advances


def check_smapi_pairs(advances: list[dict], sm, led, rep: Report, grace_s: float) -> None:
    """P2/P3a-c（Lead 裁定后的口径）：
    P3a 每次跨日必须配对一条 NewDay；
    P3b **反方向**：不许出现 `SaveGame.Save() completed` 却找不到对应 NewDay；
    P3c NewDay 有、Save 没有 ⇒ 记 info（`save_skipped_by_game`，游戏自身跳过保存），**连续 ≥2 天**才升 problem。
    """
    if sm is None:
        rep.info("没有 SMAPI 日志可读 ⇒ 只做账本与存档对账（证据强度下降）")
        return
    t0 = led["mtime"] - 3600 * 6 if led else None
    newdays = [r for r in sm["newday"] if t0 is None or r["at"] >= datetime.fromtimestamp(t0)]
    if advances:
        if len(newdays) < len(advances):
            rep.problem(f"SMAPI NewDay 只有 {len(newdays)} 条，而账本声称跨日 {len(advances)} 次"
                        f"（存档/日志里找不到那么多天）")
        used = newdays[:len(advances)]
        for i, (d, pick) in enumerate(zip(advances, used), 1):
            rep.ok(f"[{ordinal_str(d['end_day'])}] ↔ SMAPI 第 {i} 条 NewDay（行 {pick['line']} @ "
                   f"{pick['at'].strftime('%H:%M:%S')}）")
        for d in advances[len(used):]:
            rep.problem(f"[{ordinal_str(d['end_day'])}] 没有可配对的 SMAPI NewDay")
    # ---- P3b 反方向：有 Save 完成，却找不到对应的 NewDay
    for sd in sm["save_done"]:
        if not any(0 <= (sd["at"] - nd["at"]).total_seconds() <= grace_s for nd in newdays):
            rep.problem(f"L{sd['line']} @ {sd['at'].strftime('%H:%M:%S')} 有 'SaveGame.Save() completed'，"
                        f"但前面 {int(grace_s)}s 内没有 `Synchronizing 'NewDay' task`（反方向对不上）")
    # ---- P3c：NewDay 之后没落盘
    missing: list[tuple[int, dict]] = []
    for i, nd in enumerate(newdays, 1):
        if not any(0 <= (sd["at"] - nd["at"]).total_seconds() <= grace_s for sd in sm["save_done"]):
            missing.append((i, nd))
    if missing and sm.get("mtime"):
        log_mtime = datetime.fromtimestamp(sm["mtime"])
        last_nd = newdays[-1]
        if missing[-1][1] is last_nd and 0 <= (log_mtime - last_nd["at"]).total_seconds() < grace_s:
            i, nd = missing.pop()
            rep.info(f"第 {i} 次 NewDay（行 {nd['line']} @ {nd['at'].strftime('%H:%M:%S')}）之后 "
                     f"{int(grace_s)}s 内还没有 Save，但日志仍在写（mtime {log_mtime.strftime('%H:%M:%S')}）"
                     "⇒ 暂按『可能仍在写盘』处理，不计入跳过")
    runs: list[list[tuple[int, dict]]] = []
    for item in missing:
        if runs and item[0] == runs[-1][-1][0] + 1:
            runs[-1].append(item)
        else:
            runs.append([item])
    for run in runs:
        def _who(i, nd):
            day = ordinal_str(advances[i - 1]["end_day"]) if i <= len(advances) else f"第 {i} 次跨日"
            return f"{day}（行 {nd['line']} @ {nd['at'].strftime('%H:%M:%S')}）"
        where = "、".join(_who(i, nd) for i, nd in run)
        if len(run) >= 2:
            rep.problem(f"save_skipped_by_game：连续 {len(run)} 次跨日都没有落盘（{where}）"
                        "⇒ 游戏连续多日不落盘，账本的天数没有存档背书")
        else:
            rep.info(f"save_skipped_by_game：{where} 有 NewDay 但没有 SaveGame.Save() completed"
                     f"（{int(grace_s)}s 内）⇒ 按『游戏自身跳过保存』记 info（task-47 在挖触发条件），不判 problem")


def check_save(advances: list[dict], sv, led, rep: Report) -> None:
    """P4（Lead 裁定后放宽）：存档 XML 的"天"与账本收尾天相差 ≤1 天 ⇒ info（save-day 语义 + 游戏自身跳过保存）；
    ≥2 天、或"存档比账本新"⇒ problem。"""
    if sv is None:
        rep.problem("存档目录/主存档读不到 ⇒ 少了最重要的一源")
        return
    triple = (sv.get("xml") or {}).get("day_triple")
    if not triple:
        rep.problem("存档 XML 里没有 <dayOfMonth>/<currentSeason>/<year> ⇒ 无法用游戏真值核对天数")
        return
    main = sv["files"].get("Wahaha_450799035")
    rep.ok(f"存档 XML 真值：{ordinal_str(triple)}、money={sv['xml'].get('money')}"
           f"（<money> 命中 {sv['xml'].get('money_hits')} 处）；主存档 {main['size'] if main else '?'} B"
           f" @ {fmt_mtime(main['mtime']) if main else '-'}")
    if not advances:
        return
    last = advances[-1]
    o_save, o_last = ordinal(triple), ordinal(last["end_day"])
    if o_save is None or o_last is None:
        rep.problem("天数折算失败（存档或账本的 day 形状不对）")
        return
    gap = o_last - o_save
    if gap == 0:
        rep.ok(f"存档天数与账本收尾一致：{ordinal_str(triple)}")
    elif gap == 1:
        # 只有 1 天的差：极可能是 Stardew 存档里的 save-day = "睡前那一天"（真值口径），
        # 也可能是落盘滞后。**不单独判死**——跨日另有 SMAPI NewDay/Save 与窗口 delta 三处硬证据；
        # 落后 ≥2 天才判 problem（见 neg-D）。
        rep.info(f"存档比账本收尾落后 1 天（存档 {ordinal_str(triple)} / 账本 "
                 f"{ordinal_str(last['end_day'])}）⇒ 需人工确认是『save-day=睡前那天』的语义差，还是落盘滞后；"
                 "本工具不因此单独判死（另有 SMAPI NewDay/Save 配对与窗口 delta 把关）")
    elif gap >= 2:
        rep.problem(f"存档还停在 {ordinal_str(triple)}，账本已到 {ordinal_str(last['end_day'])}"
                    f"（落后 {gap} 天）⇒ 超出『save-day 语义差 + 游戏跳过保存』能解释的 1 天，"
                    f"是少了天数/money 没落盘（存档 mtime {fmt_mtime(main['mtime']) if main else '-'}）")
    else:
        # 跑批进行中：最后一天可能已经在游戏里跨过去了、账本还没写 day_end/收尾 ⇒ 领先 1 天记 info；
        # 收工后（有 finish）或在跑也领先 ≥2 天 ⇒ 仍是 problem（账本少记了天数）。
        unfinished = led is not None and led.get("finish") is None
        if unfinished and gap == -1:
            rep.info(f"跑批进行中（没有 finish）：存档已到 {ordinal_str(triple)}、账本收尾 "
                     f"{ordinal_str(last['end_day'])} —— 领先 1 天属收尾未写 ⇒ 本次不判红"
                     f"（存档 mtime {fmt_mtime(main['mtime']) if main else '-'}）")
        else:
            rep.problem(f"存档比账本收尾还新 {abs(gap)} 天（存档 {ordinal_str(triple)} / 账本 "
                        f"{ordinal_str(last['end_day'])}）⇒ 账本少记了天数（或存档不是这一局的）")


def check_window(snap, advances, sm, sv, rep: Report) -> None:
    if snap is None:
        rep.info("没有 start/end 快照 ⇒ 无法算窗口 delta")
        return
    if len(snap["rows"]) < 2 or snap["start"] is snap["end"]:
        rep.info(f"窗口快照只有 {len(snap['rows'])} 行（`end` 快照还没写）⇒ 窗口 delta 待跑完再算，"
                 "已跳过 P6（不因此判红）")
        return
    s, e = snap["start"], snap["end"]
    rep.info(f"窗口：{s.get('tag')}@{s.get('at')} → {e.get('tag')}@{e.get('at')}")
    sm_main = (s.get("save_main") or {}), (e.get("save_main") or {})
    if sm_main[0].get("exists") and sm_main[1].get("exists"):
        if (sm_main[1].get("size"), sm_main[1].get("mtime")) == (sm_main[0].get("size"), sm_main[0].get("mtime")):
            rep.problem("窗口首尾的主存档 size/mtime 完全没变 ⇒ 窗口内游戏一次都没落盘")
        else:
            rep.ok(f"主存档前进：size {sm_main[0].get('size')}→{sm_main[1].get('size')}、"
                   f"mtime {sm_main[0].get('mtime')} → {sm_main[1].get('mtime')}")
    dn_new = (e.get("smapi_newday") or 0) - (s.get("smapi_newday") or 0)
    dn_save = (e.get("smapi_save") or 0) - (s.get("smapi_save") or 0)
    rep.info(f"窗口 delta：SMAPI 行 {s.get('smapi_lines')}→{e.get('smapi_lines')}、"
             f"NewDay {s.get('smapi_newday')}→{e.get('smapi_newday')}（+{dn_new}）、"
             f"Save {s.get('smapi_save')}→{e.get('smapi_save')}（+{dn_save}）")
    if advances and dn_new < len(advances):
        rep.problem(f"窗口内 SMAPI NewDay 只增加 {dn_new} 条，少于账本跨日 {len(advances)} 次")
    if advances and dn_save < len(advances):
        rep.problem(f"窗口内 SMAPI Save 只增加 {dn_save} 次，少于账本跨日 {len(advances)} 次（没落盘）")
    del sm, sv


def check_payout(led, baseline, rep: Report) -> None:
    """P5：账本说卖出去了，就应当能在真值里看到钱变多（存档 money 或 baseline.money）。"""
    if led is None:
        return
    sells = led["sells"]
    if not sells:
        rep.info("账本里没有成功的 sell 事件 ⇒ 本次没有出货分红要对")
        return
    items = sum(int(s.get("stack") or 1) for s in sells)
    first_money = next((d.get("start_money") for d in led["days"] if d.get("start_money") is not None), None)
    base_money = None
    if baseline is not None and isinstance(baseline, dict):
        base_money = baseline.get("money")
    if first_money is not None and base_money is not None and base_money > first_money:
        rep.ok(f"出货到账证据：账本起跑 money={first_money} → 真机 baseline money={base_money}"
               f"（+{base_money - first_money}g，账本记了 {len(sells)} 笔 / {items} 个）")
    elif first_money is not None and base_money is not None:
        rep.problem(f"账本记了 {len(sells)} 笔出货，但真机 money 没变（{first_money} → {base_money}）⇒ 到账链没证据")
    else:
        rep.info(f"账本记了 {len(sells)} 笔出货（{items} 个），但缺 baseline/起跑 money ⇒ 到账链只能靠窗口 delta 旁证")


# --------------------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="task-45 三源对账（账本 ↔ SMAPI ↔ 存档），只读")
    ap.add_argument("--ledger", default=str(ROOT / "logs" / "longrun-3day-llm-run5.jsonl"))
    ap.add_argument("--smapi", default=str(SMAPI_DEFAULT))
    ap.add_argument("--save-dir", default=str(SAVE_DEFAULT))
    ap.add_argument("--snapshots", default=str(ROOT / "scratch" / "run5-external-snapshots.jsonl"))
    ap.add_argument("--baseline", default=str(ROOT / "logs" / "run5-baseline.json"))
    ap.add_argument("--start-tag", default="start")
    ap.add_argument("--end-tag", default="end")
    ap.add_argument("--date", default=None, help="SMAPI 日志所属日期 YYYY-MM-DD（默认用日志 mtime）")
    ap.add_argument("--save-grace", type=float, default=180.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rep = Report()
    ledger_path = Path(args.ledger)
    smapi_path = Path(args.smapi)
    save_dir = Path(args.save_dir)

    if args.date:
        anchor = _date.fromisoformat(args.date)
    elif smapi_path.exists():
        anchor = datetime.fromtimestamp(smapi_path.stat().st_mtime).date()
    else:
        anchor = _date.today()

    led = load_ledger(ledger_path, rep)
    sm = load_smapi(smapi_path, anchor, rep)
    sv = load_save(save_dir, rep)
    snap = load_snapshots(Path(args.snapshots), args.start_tag, args.end_tag, rep)
    baseline = None
    bp = Path(args.baseline)
    if bp.exists():
        try:
            baseline = json.loads(bp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            rep.info(f"baseline 读不了（{exc}）")

    print("=" * 90)
    print("task-45 三源对账（只读）")
    print("=" * 90)
    print(f"账本   : {ledger_path}  " + ("<缺失>" if led is None else
          f"{len(led['recs'])} 行 / {len(led['days'])} 天 / finish={led['finish']}"))
    print(f"SMAPI  : {smapi_path}  " + ("<缺失>" if sm is None else
          f"{sm['lines']} 行 / NewDay {len(sm['newday'])} / Save-called {len(sm['save_called'])} / "
          f"Save-done {len(sm['save_done'])}（日期锚 {anchor}）"))
    print(f"存档   : {save_dir}  " + ("<缺失>" if sv is None else
          f"{len(sv['files'])} 个文件 / XML {sv['xml'].get('day_triple')} money={sv['xml'].get('money')}"))
    print(f"快照   : {args.snapshots}  " + ("<缺失>" if snap is None else
          f"{len(snap['rows'])} 行"))
    print(f"baseline: {args.baseline}  " + ("<缺失>" if baseline is None else
          f"money={baseline.get('money')} day={baseline.get('day')}"))
    print("-" * 90)

    if led is None:
        print("!! 账本还没生成 ⇒ **预检模式**（只对 SMAPI + 存档两源；三源对账等 run5 落账本后再跑）")
        lines = sm["lines"] if sm else 0
        if sm:
            for r in sm["newday"]:
                print(f"  NewDay  行 {r['line']:>5} @ {r['at'].strftime('%H:%M:%S')}")
            for r in sm["save_done"]:
                print(f"  Save✓   行 {r['line']:>5} @ {r['at'].strftime('%H:%M:%S')}")
            del lines
        if sv:
            main = sv["files"].get("Wahaha_450799035")
            print(f"  存档    主 {main['size']} B @ {fmt_mtime(main['mtime'])}；"
                  f"_old {sv['files'].get('Wahaha_450799035_old', {}).get('size')} B @ "
                  f"{fmt_mtime(sv['files'].get('Wahaha_450799035_old', {}).get('mtime'))}")
        if baseline:
            print(f"  baseline day={baseline.get('day')} money={baseline.get('money')} "
                  f"activeMenu={baseline.get('activeMenu')} worldSeq={baseline.get('worldSeq')}")
        check_save([], sv, None, rep)
        check_payout(None, baseline, rep)
        _emit(rep, args.json)
        return 3

    advances = check_ledger_chain(led, rep)
    check_smapi_pairs(advances, sm, led, rep, args.save_grace)
    check_save(advances, sv, led, rep)
    check_window(snap, advances, sm, sv, rep)
    check_payout(led, baseline, rep)

    if led["finish"]:
        f = led["finish"]
        rep.info(f"账本 finish：code={f.get('code')} verified_streak={f.get('verified_streak')} "
                 f"actions={f.get('actions')} minutes={f.get('minutes')}")
    _emit(rep, args.json)
    return 1 if rep.problems else 0


def _emit(rep: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"problems": rep.problems, "infos": rep.infos, "oks": rep.oks},
                         ensure_ascii=False, indent=2))
        return
    for m in rep.oks:
        print(f"  [ok]    {m}")
    for m in rep.infos:
        print(f"  [info]  {m}")
    for m in rep.problems:
        print(f"  [PROBLEM] {m}")
    print("-" * 90)
    print(f"结论：problem {len(rep.problems)} / info {len(rep.infos)} / ok {len(rep.oks)}"
          f" ⇒ {'RED（对不上）' if rep.problems else 'GREEN（三源自洽）'}")
    if rep.problems:
        print("对不上的原文：")
        for m in rep.problems:
            print(f"  * {m}")


if __name__ == "__main__":
    raise SystemExit(main())
