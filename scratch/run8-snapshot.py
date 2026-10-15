#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run8 的外部证据快照（只读 + 追加一行到 scratch\\run8-external-snapshots.jsonl）。

由 `scratch\\run6-snapshot.py` 复制而来（task-89 硬要求），默认口径改成 run8 / 0.7.27。
字段与 `scratch\\run6-snapshot.py` / `scratch\\run5-snapshot.py` 对齐：
  tag / at / written_at / note
  save_main, save_info                      —— 存档 size+mtime（可被 --save-* 覆盖以补写 start 行）
  smapi_lines, smapi_total_lines, smapi_newday, smapi_save, smapi_counts_filter
                                             smapi_save = `SaveGame.Save|SaveGameMenu`（沿 run6/run7 口径，含菜单行）
                                             smapi_before_save / smapi_save_called = `Context: before save.` / `SaveGame.Save() called.` 的精确计数
  journal_lines, journal_lines_at_start, journal_last_event, journal_finish
  pid, pid_alive                            —— 取自起跑器写的 logs\\longrun-3day-llm-run8.pid，回退 logs\\run8.pid；tasklist 复核
  bridge_info                               —— bridge.json 原文关键字段 + mtime（游戏在跑时才有）
  version_sidecar                           —— 起跑器写的 <journal>.version.json（HEAD/被测文件 SHA256+mtime/PID/起跑时刻/工作树）
  console, console_err                      —— <journal>.console.log / <journal>.console.err.log 的行数与字节数
  expected_mod_version / mod_version_matches —— 默认对 0.7.27 回显对照

起跑前（在起跑器之后立刻跑，或按 --smapi-before 精确回溯）：
    python scratch\\run8-snapshot.py --tag start
    python scratch\\run8-snapshot.py --tag start --smapi-before 21:10:00 \
        --save-size <B> --save-info-size <B> --save-mtime <iso> --journal-lines 0
收工：
    python scratch\\run8-snapshot.py --tag end
自检（不污染真文件）：
    python scratch\\run8-snapshot.py --tag selftest --out scratch\\_run8-snapshot-selftest.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
SAVE_NAME = "Wahaha_450799035"
OUT_DEFAULT = REPO / "scratch" / "run8-external-snapshots.jsonl"
DEFAULT_JOURNAL = REPO / "logs" / "longrun-3day-llm-run8.jsonl"
EXPECTED_MOD_VERSION_DEFAULT = "0.7.27"
# 起跑器 tools/start-detached-longrun.py 把 PID 写在 <journal>.pid（= logs\longrun-3day-llm-run8.pid）；
# 手工起跑那条路沿用 logs\run8.pid。两个都认，优先起跑器的那个。
PID_CANDIDATES = (REPO / "logs" / "longrun-3day-llm-run8.pid", REPO / "logs" / "run8.pid")


def stat_of(p: Path, size_override=None, mtime_override=None) -> dict:
    if size_override is not None or mtime_override is not None:
        return {"exists": True, "size": size_override, "mtime": mtime_override, "overridden": True}
    try:
        st = p.stat()
    except OSError:
        return {"exists": False, "size": None, "mtime": None}
    return {
        "exists": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds"),
    }


def bridge_info(path: Path) -> dict | None:
    """只读 bridge.json：port/pid/modVersion/gameVersion/smapiVersion/startedAt + 文件 mtime。"""
    try:
        st = path.stat()
    except OSError:
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:  # noqa: BLE001
        return {"parse_error": f"{type(exc).__name__}: {exc}",
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
    keep = ("schema", "port", "pid", "modVersion", "gameVersion", "smapiVersion", "startedAt")
    out = {k: obj.get(k) for k in keep}
    out["mtime"] = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="milliseconds")
    out["_keys"] = sorted(obj.keys())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="snap")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--journal", default=str(DEFAULT_JOURNAL))
    ap.add_argument("--pid-file", default="", help="留空则自动认 logs\\longrun-3day-llm-run8.pid → logs\\run8.pid")
    ap.add_argument("--smapi-before", default=None, help="只统计时间戳早于 HH:MM:SS 的 SMAPI 行")
    ap.add_argument("--save-size", type=int, default=None)
    ap.add_argument("--save-info-size", type=int, default=None)
    ap.add_argument("--save-mtime", default=None)
    ap.add_argument("--journal-lines", type=int, default=None, help="补写 start 行时用它记 journal_lines_at_start")
    ap.add_argument("--expected-mod-version", default=EXPECTED_MOD_VERSION_DEFAULT,
                    help="对照版本口径（run8 默认 0.7.27）")
    ap.add_argument("--note", default=None)
    args = ap.parse_args()

    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    ro = Path(appdata) / "StardewValley"
    sd = ro / "Saves" / SAVE_NAME
    smapi = ro / "ErrorLogs" / "SMAPI-latest.txt"
    bridge = ro / "AgentFarm" / "bridge.json"

    snap: dict = {"tag": args.tag, "at": datetime.now().isoformat(timespec="seconds")}
    snap["save_main"] = stat_of(sd / SAVE_NAME, args.save_size, args.save_mtime)
    snap["save_info"] = stat_of(sd / "SaveGameInfo", args.save_info_size, args.save_mtime)

    if smapi.exists():
        lines = smapi.read_text(encoding="utf-8", errors="replace").splitlines()
        if args.smapi_before:
            pat = re.compile(r"^\[(\d\d:\d\d:\d\d)")
            kept = [ln for ln in lines if (m := pat.match(ln)) and m.group(1) <= args.smapi_before]
            snap["smapi_lines"] = len(kept)
            snap["smapi_counts_filter"] = f"timestamp <= {args.smapi_before}"
        else:
            kept = lines
            snap["smapi_lines"] = len(lines)
            snap["smapi_counts_filter"] = None
        text = "\n".join(kept)
        snap["smapi_newday"] = len(re.findall(r"Synchronizing 'NewDay'", text))
        # smapi_save 沿用 run6/run7 口径（`SaveGame.Save|SaveGameMenu`，会含菜单行）；
        # 另给两个精确计数，避免与 task-47 的“日切保存是否走完”混淆。
        snap["smapi_save"] = len(re.findall(r"SaveGame\.Save|SaveGameMenu", text))
        snap["smapi_before_save"] = len(re.findall(r"Context: before save\.", text))
        snap["smapi_save_called"] = len(re.findall(r"SaveGame\.Save\(\) called\.", text))
        snap["smapi_total_lines"] = len(lines)
        snap["smapi_mtime"] = stat_of(smapi)["mtime"]
    else:
        snap["smapi_lines"] = snap["smapi_newday"] = snap["smapi_save"] = None
        snap["smapi_before_save"] = snap["smapi_save_called"] = None
        snap["smapi_total_lines"] = None
        snap["smapi_counts_filter"] = None
        snap["smapi_mtime"] = None

    jp = Path(args.journal)
    if jp.exists():
        rows = [ln for ln in jp.read_text(encoding="utf-8").splitlines() if ln.strip()]
        snap["journal_lines"] = len(rows)
        last = fin = None
        for ln in rows:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            last = r.get("event")
            if r.get("event") == "finish":
                fin = r
        snap["journal_last_event"] = last
        snap["journal_finish"] = fin
    else:
        snap["journal_lines"] = snap["journal_last_event"] = snap["journal_finish"] = None
    snap["journal_path"] = str(jp)
    if args.journal_lines is not None:
        snap["journal_lines_at_start"] = args.journal_lines

    pid = None
    chosen_pid_file = None
    for cand in ((Path(args.pid_file),) if args.pid_file else PID_CANDIDATES):
        if cand.exists():
            chosen_pid_file = cand
            try:
                pid = int(cand.read_text(encoding="utf-8").strip())
            except ValueError:
                pid = None
            break
    snap["pid_file"] = str(chosen_pid_file) if chosen_pid_file else None
    snap["pid_file_candidates"] = [str(p) for p in (PID_CANDIDATES if not args.pid_file else (Path(args.pid_file),))]
    snap["pid"] = pid
    snap["pid_alive"] = None
    if pid is not None:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10)
            snap["pid_alive"] = str(pid) in (out.stdout or "")
        except Exception as exc:  # noqa: BLE001
            snap["pid_alive"] = f"? {type(exc).__name__}: {exc}"

    snap["bridge_info"] = bridge_info(bridge)
    if args.expected_mod_version:
        got = (snap["bridge_info"] or {}).get("modVersion")
        snap["expected_mod_version"] = args.expected_mod_version
        snap["mod_version_matches"] = (got == args.expected_mod_version) if got else None

    # 起跑器 sidecar（HEAD / 被测文件 SHA256+mtime / PID / 起跑时刻 / 工作树）—— 有则原样带上，便于"版本四要素"一句话引用
    sidecar_path = jp.with_suffix(".version.json")
    if sidecar_path.exists():
        try:
            sc = json.loads(sidecar_path.read_text(encoding="utf-8", errors="replace"))
            snap["version_sidecar"] = {
                "path": str(sidecar_path),
                "head": sc.get("head"),
                "pid": sc.get("pid"),
                "started_at": sc.get("started_at"),
                "worktree_clean": sc.get("worktree_clean"),
                "git_status_short": sc.get("git_status_short"),
                "files": {k: {"sha256": (v or {}).get("sha256"), "mtime": (v or {}).get("mtime")}
                          for k, v in (sc.get("files") or {}).items()},
            }
        except (OSError, json.JSONDecodeError) as exc:  # noqa: BLE001
            snap["version_sidecar"] = {"path": str(sidecar_path), "parse_error": f"{type(exc).__name__}: {exc}"}
    else:
        snap["version_sidecar"] = None

    for key, suffix in (("console", ".console.log"), ("console_err", ".console.err.log")):
        p = jp.with_suffix(suffix)
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="replace")
            snap[key] = {
                "path": str(p),
                "bytes": p.stat().st_size,
                "lines": len(txt.splitlines()),
                "tail": txt.splitlines()[-3:],
            }
        else:
            snap[key] = None

    snap["written_at"] = datetime.now().isoformat(timespec="seconds")
    if args.note:
        snap["note"] = args.note

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print(json.dumps(snap, ensure_ascii=False, indent=1))
    print(f"\n已追加到 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
