# -*- coding: utf-8 -*-
"""task-1 A8 取证生成器（纯离线；只读源文件，只写 logs/ 三份派生物）。

产出：
  1) logs/runA8-0743-smapi-window.txt     —— SMAPI-latest.txt 的 A8 窗口逐字截取（14:50:12 → 15:20:39）
  2) logs/runA8-0743-sixchain-final.json  —— 窗口内 12 对 + 窗口外 7 对六串（NewDay/before save/save called/save task/completed/after save）行号与配对
  3) logs/runA8-0743-daytable.json        —— 12 个 day_end 的逐日读数 + 失败日死循环现场行号
可选（--check-files）：复核 A8-start 四件与五文件现树 SHA256。

只读：logs/longrun-runA8-0743.jsonl、logs/longrun-runA8-0743.version.json、
      logs/ab-backup/A8-start/MANIFEST.json、%APPDATA%\\StardewValley\\ErrorLogs\\SMAPI-latest.txt、
      %APPDATA%\\StardewValley\\Saves\\Wahaha_450799035\\*（存档四件只记当前值，不冒充 A8 终点）

用法（必须 PYTHONUTF8=1）：
  python scratch\\_t250_a8_evidence.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
JOURNAL = os.path.join(LOGS, "longrun-runA8-0743.jsonl")
SIDECAR = os.path.join(LOGS, "longrun-runA8-0743.version.json")
A8DIR = os.path.join(LOGS, "ab-backup", "A8-start")
SAVEDIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
WINDOW_END = "15:20:39"
SAVE_FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")
VERSION_FILES = ("brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
                 "brain/agentfarm/bridge.py",
                 "mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll",
                 "mod/AgentFarm.Bridge/manifest.json")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
# 顺序即六串顺序（P3a/P3b：NewDay → before save → Save called → Save task → completed → after save）
PATS = (
    ("newday", "Synchronizing 'NewDay' task"),
    ("before_save", "Context: before save."),
    ("save_called", "SaveGame.Save() called."),
    ("save_task", "Synchronizing 'Save' task"),
    ("completed", "completed without exceptions"),
    ("after_save", "after save, starting"),
)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def l16_real(line: str) -> bool:
    """插件描述行（mods 列表）也含关键词；真实 SMAPI 行必须有 [HH:MM:SS 前缀且不含插件特征。"""
    if TS.match(line) is None:
        return False
    return (" by AgentFarm " not in line) and ("| v0." not in line)


def ts_of(line: str) -> str | None:
    m = TS.match(line)
    return m.group(1) if m else None


def seconds(hms: str) -> int:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


# ---------------------------------------------------------------- SMAPI 六串

def sixchain(lines: list[str], lo: int, hi: int) -> dict:
    """lines[lo:hi]（0-based，左闭右开）内按 NewDay 分段配对六串。返回结构化结果。"""
    hits: dict[str, list[dict]] = {k: [] for k, _ in PATS}
    excluded: list[dict] = []
    for i in range(lo, hi):
        line = lines[i]
        for key, needle in PATS:
            if needle in line:
                if not l16_real(line):
                    excluded.append({"key": key, "line": i + 1, "text": line[:120]})
                    continue
                hits[key].append({"line": i + 1, "time": ts_of(line), "text": line[:160]})

    # 以 NewDay 为段界：每段从该 NewDay 到下一个 NewDay（或窗口末）
    newdays = hits["newday"]
    pairs: list[dict] = []
    for n, nd in enumerate(newdays):
        seg_lo = nd["line"]
        seg_hi = newdays[n + 1]["line"] if n + 1 < len(newdays) else hi + 1
        seg: dict[str, dict | None] = {}
        for key, _ in PATS[1:]:
            cand = [h for h in hits[key] if seg_lo <= h["line"] < seg_hi]
            seg[key] = cand[0] if cand else None
        row: dict = {"n": n + 1, "newday": nd, **seg}
        ordered = True
        prev = nd["line"]
        for key, _ in PATS[1:]:
            cur = seg.get(key)
            if cur is None:
                ordered = False
                break
            if cur["line"] < prev:
                ordered = False
                break
            prev = cur["line"]
        times = [row[k]["time"] for k in ("newday", "before_save", "save_called", "save_task",
                                          "completed", "after_save") if row.get(k)]
        tsecs = [seconds(t) for t in times if t]
        mono = all(b >= a for a, b in zip(tsecs, tsecs[1:]))
        row["ordered"] = ordered
        row["monotonic_time"] = mono
        row["complete"] = all(row.get(k) for k, _ in PATS[1:])
        row["verdict"] = "PASS" if (ordered and mono) else "FAIL"
        pairs.append(row)

    counts = {k: len(v) for k, v in hits.items()}
    unpaired_newday = counts["newday"] - len(pairs)
    return {
        "window_lo_line": lo + 1, "window_hi_line": hi,
        "counts": counts,
        "pairs": pairs,
        "unpaired_newday": unpaired_newday,
        "excluded_l16": excluded,
        "all_pass": all(p["verdict"] == "PASS" for p in pairs) and unpaired_newday == 0,
        "raw_hits": hits,
    }


# ---------------------------------------------------------------- 账本逐日

def load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


COUNT_EVENTS = ("resume_walk", "work_spot", "resume_reevaluate", "no_progress_burst",
                "stage_shortfall", "stage_stop_named", "unreachable", "unreachable_stage",
                "unreachable_summary", "encircled", "encircled_stage", "encircled_summary",
                "frontier_clear", "stuck_flush", "sleep", "day_cap", "plot_exhausted")


def day_records(rows: list[dict]) -> tuple[list[dict], dict | None]:
    days: list[dict] = []
    cur: dict | None = None
    finish = None
    for ln, row in enumerate(rows, 1):
        ev = row.get("event")
        if ev == "day_start":
            cur = {"start_line": ln, "rows": [(ln, row)]}
            days.append(cur)
        elif cur is not None:
            cur["rows"].append((ln, row))
        if ev == "finish":
            finish = {"line": ln, "row": row}
    out = []
    for d in days:
        end_line, end_row = next(((ln, r) for ln, r in reversed(d["rows"])
                                  if r.get("event") == "day_end"), (None, None))
        if end_row is None:
            out.append({"start_line": d["start_line"], "end_line": None, "day": None})
            continue
        counts = {k: 0 for k in COUNT_EVENTS}
        lines_by: dict[str, list[int]] = {k: [] for k in COUNT_EVENTS}
        for ln, r in d["rows"]:
            if r.get("event") in counts:
                counts[r["event"]] += 1
                lines_by[r["event"]].append(ln)
        day = end_row.get("day")
        if isinstance(day, list) and len(day) == 3:
            day = f"{day[1]} {day[2]}"
        stages = end_row.get("stages") or []
        churn = [s for s in stages
                 if s.get("assigned") == 1 and s.get("assigned_undone") == 1
                 and s.get("stopped") == "incomplete"]
        # 阶段收尾事件里的 incomplete 1 格余量（带坐标）
        inc_stop = [(ln, r) for ln, r in d["rows"]
                    if r.get("event") == "stage_stop_named" and r.get("cause") == "incomplete"]
        checks = end_row.get("checks") or {}
        rec = {
            "day": day,
            "start_line": d["start_line"],
            "end_line": end_line,
            "ended_by": end_row.get("ended_by"),
            "verified": end_row.get("verified"),
            "day_after": end_row.get("day_after"),
            "ok_steps": end_row.get("ok_steps"),
            "skipped_steps": end_row.get("skipped_steps"),
            "failed_steps": end_row.get("failed_steps"),
            "checks_false": [k for k, v in checks.items() if v is False],
            "checks": checks,
            "ended_reason": end_row.get("ended_reason"),
            "stage_count": len(stages),
            "churn_1tile_stages": len(churn),
            "churn_1tile_assigned_undone": sum(int(s.get("assigned_undone") or 0) for s in churn),
            "incomplete_stop_events": len(inc_stop),
            "incomplete_stop_lines": [ln for ln, _ in inc_stop],
            "unreachable": end_row.get("unreachable"),
            "unreachable_tiles": end_row.get("unreachable_tiles"),
            "unreachable_bound": end_row.get("unreachable_bound"),
            "unreachable_exempt": end_row.get("unreachable_exempt"),
            "bound_basis": end_row.get("bound_basis"),
            "encircled": end_row.get("encircled"),
            "encircled_tiles": end_row.get("encircled_tiles"),
            "plot_pending": end_row.get("plot_pending"),
            "assigned_undone": end_row.get("assigned_undone"),
            "counts": counts,
            "lines_by": lines_by,
        }
        out.append(rec)
    return out, finish


def churn_detail(rows: list[dict], rec: dict) -> dict:
    """失败日现场：1 格余量重复分配的坐标 + resume 拿不出目标的行号。"""
    lo, hi = rec["start_line"], rec["end_line"]
    win = [(ln, r) for ln, r in enumerate(rows[lo - 1:hi], lo)]

    def items(evs):
        return [(ln, r) for ln, r in win if r.get("event") in evs]

    inc: list[dict] = []
    for ln, r in items(("stage_stop_named",)):
        if r.get("cause") == "incomplete":
            inc.append({"line": ln, "assigned": r.get("assigned"),
                        "assigned_undone": r.get("assigned_undone"),
                        "tiles": r.get("tiles"), "zone": r.get("zone")})
    resumes = [{"line": ln, "attempt": r.get("attempt"), "zone": r.get("zone"),
                "tiles": r.get("tiles"), "note": r.get("note")}
               for ln, r in items(("resume_walk", "work_spot"))]
    bursts = [{"line": ln, "count": r.get("count"), "tiles": r.get("tiles")}
              for ln, r in items(("no_progress_burst",))]
    encircled = [{"line": ln, "tile": r.get("tile"), "tiles": r.get("tiles"),
                  "zone": r.get("zone"), "reason": r.get("reason")}
                 for ln, r in items(("encircled", "encircled_stage"))]
    unreachable = [{"line": ln, "tile": r.get("tile"), "zone": r.get("zone")}
                   for ln, r in items(("unreachable",))]
    # 去重保留出现次数
    def uniq(seq):
        out = []
        for x in seq:
            if not out or out[-1] != x:
                out.append(x)
        return out
    tiles_inc = uniq([json.dumps(x.get("tiles"), ensure_ascii=False) for x in inc])
    return {"incomplete_stops": inc, "incomplete_distinct_tiles": tiles_inc,
            "resume_events": resumes, "no_progress_bursts": bursts,
            "encircled_events": encircled, "unreachable_events": unreachable}


# ---------------------------------------------------------------- 文件指纹

def file_fingerprint(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    st = os.stat(path)
    return {"path": path, "size": st.st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "mtime_epoch": st.st_mtime, "sha256": sha256(path)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-files", action="store_true", help="复核 A8-start 四件与五文件现树")
    ap.add_argument("--out-window", default=os.path.join(LOGS, "runA8-0743-smapi-window.txt"))
    ap.add_argument("--out-six", default=os.path.join(LOGS, "runA8-0743-sixchain-final.json"))
    ap.add_argument("--out-day", default=os.path.join(LOGS, "runA8-0743-daytable.json"))
    args = ap.parse_args()

    result: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    # ---- 1) sidecar / 起跑四要素
    sidecar = json.load(open(SIDECAR, encoding="utf-8"))
    result["sidecar"] = sidecar
    result["sidecar_recheck"] = {
        "head_now": os.popen("git rev-parse HEAD").read().strip(),
        "files_now": {f: file_fingerprint(os.path.join(ROOT, f)) for f in VERSION_FILES},
    }
    manifest = json.load(open(os.path.join(A8DIR, "MANIFEST.json"), encoding="utf-8"))
    man = {}
    for name, ent in manifest.items():
        p = os.path.join(A8DIR, name)
        cur = file_fingerprint(p)
        man[name] = {"manifest": ent, "now": cur,
                     "match": bool(cur and cur["size"] == ent["size"]
                                   and cur["sha256"] == ent["sha256"])}
    result["a8_start_manifest"] = man
    result["a8_start_manifest_mtime_local"] = {
        name: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ent["mtime"]))
        for name, ent in manifest.items()}

    # ---- 2) SMAPI 窗口
    lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()
    end_line = 0
    for i, ln in enumerate(lines, 1):
        t = ts_of(ln)
        if t and t <= WINDOW_END:
            end_line = i
    window = sixchain(lines, 0, end_line)
    post = sixchain(lines, end_line, len(lines))
    with open(args.out_window, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines[:end_line]) + "\n")
    copy_lines = open(args.out_window, encoding="utf-8", errors="replace").read().splitlines()
    err = {"ERROR": 0, "Disconnected": 0, "ClosedGame": 0, "Exception": 0}
    for ln in lines[:end_line]:
        for k in err:
            if k in ln:
                err[k] += 1
    result["smapi"] = {
        "source": SMAPI, "source_lines": len(lines), "source_size": os.path.getsize(SMAPI),
        "source_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(SMAPI))),
        "window": {"start_line": 1, "end_line": end_line,
                   "first_time": ts_of(lines[0]) if lines else None,
                   "last_time": ts_of(lines[end_line - 1]) if end_line else None,
                   "next_line_after_window": ({"line": end_line + 1, "time": ts_of(lines[end_line]),
                                               "text": lines[end_line][:160]}
                                              if end_line < len(lines) else None),
                   "lines": end_line},
        "window_file": file_fingerprint(args.out_window),
        "window_prefix_identical": copy_lines == lines[:end_line],
        "window_error_counts": err,
        "sixchain": window,
        "post_window": {"lines": len(lines) - end_line,
                        "first_time": ts_of(lines[end_line]) if end_line < len(lines) else None,
                        "last_time": ts_of(lines[-1]) if lines else None,
                        "sixchain": post},
    }
    with open(args.out_six, "w", encoding="utf-8") as fh:
        json.dump({"window": result["smapi"]["window"], "sixchain": window,
                   "post_window": result["smapi"]["post_window"]},
                  fh, ensure_ascii=False, indent=1)

    # ---- 3) 账本逐日
    rows = load_jsonl(JOURNAL)
    days, finish = day_records(rows)
    detail = {d["day"]: churn_detail(rows, d) for d in days if d.get("verified") is False}
    result["journal"] = {"lines": len(rows), "finish": finish}

    # ---- 4) 存档四件（当前值 —— 不是 A8 终点，只作"现盘状态"）
    result["save_now"] = {name: file_fingerprint(os.path.join(SAVEDIR, name))
                          for name in SAVE_FILES}

    # ---- 5) 当班留存的独立观测快照（scratch/runA8-observe*.json）
    snaps = []
    for name in sorted(f for f in os.listdir(os.path.join(ROOT, "scratch"))
                       if f.startswith("runA8-observe")):
        p = os.path.join(ROOT, "scratch", name)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            snaps.append({"file": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        clock = ((d.get("observe") or {}).get("clock") or {})
        player = ((d.get("observe") or {}).get("player") or {})
        snaps.append({"file": name, "captured_at": d.get("captured_at"),
                      "day_key": d.get("day_key"), "journal_lines": d.get("journal_lines"),
                      "worldSeq": (d.get("observe") or {}).get("worldSeq"),
                      "day": [clock.get("season"), clock.get("day")],
                      "timeOfDay": clock.get("timeOfDay"),
                      "location": player.get("location"), "stamina": player.get("stamina"),
                      "money": player.get("money")})
    result["observations"] = snaps

    daytable = {"journal": file_fingerprint(JOURNAL), "lines": len(rows),
                "finish": finish, "days": days, "failure_detail": detail,
                "observations": result["observations"],
                "smapi_window": result["smapi"]["window"],
                "smapi_window_file": result["smapi"]["window_file"],
                "smapi_window_prefix_identical": result["smapi"]["window_prefix_identical"],
                "smapi_window_error_counts": result["smapi"]["window_error_counts"],
                "save_now": result["save_now"]}
    with open(args.out_day, "w", encoding="utf-8") as fh:
        json.dump(daytable, fh, ensure_ascii=False, indent=1)

    # ---- 打印摘要
    print(f"sidecar: head={sidecar['head'][:12]} pid={sidecar['pid']} "
          f"started_at={sidecar['started_at']} clean={sidecar.get('worktree_clean')}")
    print("A8-start 四件（manifest 原文 / 现盘复算）:")
    for name, v in man.items():
        e = v["manifest"]
        print(f"  {name}: size={e['size']} mtime={result['a8_start_manifest_mtime_local'][name]} "
              f"sha256={e['sha256'][:16]}… 现盘={'MATCH' if v['match'] else 'MISMATCH'}")
    print(f"SMAPI: 源 {len(lines)} 行 / {os.path.getsize(SMAPI)} B；窗口 1..{end_line}"
          f"（{ts_of(lines[0])}→{ts_of(lines[end_line - 1])}，{end_line} 行）")
    print(f"  窗口六串 = {json.dumps(window['counts'], ensure_ascii=False)}  "
          f"配对 {sum(1 for p in window['pairs'] if p['verdict'] == 'PASS')}/{len(window['pairs'])}  "
          f"L16 排除 {len(window['excluded_l16'])}")
    print(f"  窗口后（{len(lines) - end_line} 行）六串 = "
          f"{json.dumps(post['counts'], ensure_ascii=False)}  配对 "
          f"{sum(1 for p in post['pairs'] if p['verdict'] == 'PASS')}/{len(post['pairs'])}")
    keys = ("newday", "before_save", "save_called", "save_task", "completed", "after_save")
    print("  窗口内逐对（行号 / 时刻 / 落盘目标日）:")

    def pair_line(p: dict) -> str:
        ln = "/".join(str((p.get(k) or {}).get("line") or "-") for k in keys)
        tm = "/".join(str((p.get(k) or {}).get("time") or "-") for k in keys)
        tgt = ((p.get("after_save") or {}).get("text") or "").split("starting ")[-1].rstrip(".")
        return f"    #{p['n']:>2} line={ln} time={tm} → {tgt} {p['verdict']}"

    for p in window["pairs"]:
        print(pair_line(p))
    print("  窗口外逐对（废数据，只作 7 次无人落盘的证据）:")
    for p in post["pairs"]:
        print(pair_line(p))
    print("  SMAPI 窗口副本：" + json.dumps(result["smapi"]["window_file"], ensure_ascii=False))
    print("  窗口副本逐行 == 源文件前 %d 行：%s；窗口内错误/断连计数 = %s" % (
        end_line, result["smapi"]["window_prefix_identical"],
        json.dumps(result["smapi"]["window_error_counts"], ensure_ascii=False)))
    print("  当班独立观测快照（scratch/runA8-observe*.json）：")
    for s in result["observations"]:
        print("   " + json.dumps(s, ensure_ascii=False))
    print("  当前存档四件（不是 A8 终点）：" + json.dumps(
        {k: (v and {kk: v[kk] for kk in ('size', 'mtime', 'sha256')}) for k, v in result["save_now"].items()},
        ensure_ascii=False))
    print(f"账本 {len(rows)} 行；day_end {len(days)}；finish={json.dumps(finish['row'], ensure_ascii=False)[:220]}")
    print("\n逐日表（markdown）:")
    print("| # | 游戏日 | 账本行 | ended_by | verified | ok/skip/fail | checks=false | 1格余量阶段 | 失败原因/收尾理由(截) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for i, d in enumerate(days, 1):
        if d.get("end_line") is None:
            continue
        reason = str(d.get("ended_reason") or "").replace("|", "\\|")
        print(f"| {i} | {d['day']} | {d['start_line']}–{d['end_line']} | {d['ended_by']} | "
              f"{d['verified']} | {d['ok_steps']}/{d['skipped_steps']}/{d['failed_steps']} | "
              f"{','.join(d['checks_false'])} | {d['churn_1tile_stages']} | {reason[:120]} |")
    print("\n失败日现场:")
    for day, det in detail.items():
        print(f"  {day}: incomplete_stops={len(det['incomplete_stops'])} "
              f"distinct_tiles={len(det['incomplete_distinct_tiles'])} "
              f"resume_events={len(det['resume_events'])} bursts={len(det['no_progress_bursts'])} "
              f"encircled={len(det['encircled_events'])} unreachable={len(det['unreachable_events'])}")
        if det["incomplete_stops"]:
            lines_ = [x["line"] for x in det["incomplete_stops"]]
            print(f"    1格余量行号 {lines_[0]}..{lines_[-1]}（共 {len(lines_)}） 例: "
                  f"{json.dumps(det['incomplete_stops'][:2], ensure_ascii=False)[:240]}")
        if det["resume_events"]:
            print(f"    resume/work_spot 行号 "
                  f"{[x['line'] for x in det['resume_events']]} attempts="
                  f"{[x.get('attempt') for x in det['resume_events']]}")
        if det["encircled_events"]:
            print(f"    encircled: {json.dumps(det['encircled_events'][:3], ensure_ascii=False)[:300]}")
        if det["unreachable_events"]:
            print(f"    unreachable: {json.dumps(det['unreachable_events'][:5], ensure_ascii=False)[:300]}")

    if args.check_files:
        print("\n五文件现树 SHA256（只读）：")
        for f in VERSION_FILES:
            fp = file_fingerprint(os.path.join(ROOT, f))
            ent = sidecar["files"][f]
            sha_ok = fp["sha256"] == ent["sha256"]
            mtime_ok = abs(fp["mtime_epoch"] - time.mktime(
                time.strptime(ent["mtime"], "%Y-%m-%dT%H:%M:%S.%f"))) < 1.0
            print(f"  {f}: {fp['sha256'][:16]}… size={fp['size']} "
                  f"sha256={'MATCH' if sha_ok else 'MISMATCH'} "
                  f"mtime={'MATCH' if mtime_ok else 'DIFF'}（现盘 {fp['mtime']} / sidecar {ent['mtime']}）")

    print(f"\n已写：\n  {args.out_window}\n  {args.out_six}\n  {args.out_day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
