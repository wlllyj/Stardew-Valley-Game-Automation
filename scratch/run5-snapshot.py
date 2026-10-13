#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run5 的外部件证据快照（只读 + 追加一行到 scratch\\run5-external-snapshots.jsonl）。

与 `scratch\\_run4_snapshot.py` 同字段（tag/at/save_main/save_info/smapi_lines/smapi_newday/smapi_save/
journal_lines/journal_last_event/journal_finish/pid/pid_alive），另加 `written_at` 与 `note`，用于**补写**
错过时刻的 start 行：`--smapi-before HH:MM:SS` 只统计早于该时刻的 SMAPI 行（于是 start 行的累计计数是
**精确回溯**，不是估算），存档字段用 `--save-*` 覆盖。

    python scratch\\run5-snapshot.py --tag start --smapi-before 20:06:57 \
        --save-size 3658556 --save-info-size 25825 --save-mtime 2026-10-13T20:03:44.986 --journal-lines 0
    python scratch\\run5-snapshot.py --tag end
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
OUT = REPO / "scratch" / "run5-external-snapshots.jsonl"
PID_FILE = REPO / "logs" / "run5.pid"
DEFAULT_JOURNAL = REPO / "logs" / "longrun-3day-llm-run5.jsonl"


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="snap")
    ap.add_argument("--journal", default=str(DEFAULT_JOURNAL))
    ap.add_argument("--smapi-before", default=None, help="只统计时间戳早于 HH:MM:SS 的 SMAPI 行")
    ap.add_argument("--save-size", type=int, default=None)
    ap.add_argument("--save-info-size", type=int, default=None)
    ap.add_argument("--save-mtime", default=None)
    ap.add_argument("--journal-lines", type=int, default=None)
    ap.add_argument("--note", default=None)
    args = ap.parse_args()

    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    sd = Path(appdata) / "StardewValley" / "Saves" / SAVE_NAME
    smapi = Path(appdata) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"

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
        snap["smapi_save"] = len(re.findall(r"SaveGame\.Save|SaveGameMenu", text))
        snap["smapi_total_lines"] = len(lines)
    else:
        snap["smapi_lines"] = snap["smapi_newday"] = snap["smapi_save"] = None
        snap["smapi_counts_filter"] = None

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
    if args.journal_lines is not None:
        snap["journal_lines_at_start"] = args.journal_lines

    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
    snap["pid"] = pid
    snap["pid_alive"] = None
    if pid is not None:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10)
            snap["pid_alive"] = str(pid) in (out.stdout or "")
        except Exception as exc:  # noqa: BLE001
            snap["pid_alive"] = f"? {type(exc).__name__}: {exc}"

    snap["written_at"] = datetime.now().isoformat(timespec="seconds")
    if args.note:
        snap["note"] = args.note

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")
    print(json.dumps(snap, ensure_ascii=False, indent=1))
    print(f"\n已追加到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
