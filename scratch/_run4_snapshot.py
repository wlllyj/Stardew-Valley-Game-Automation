#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""run4 的外部证据快照（Lead 侧，只读 + 追加一行到 scratch 的 jsonl）。

为什么需要它：账本是 longrun 自己写的（`tools\\verify-run3.py` 只是**账本检查器**），
"跨日真的发生了"必须靠账本之外的证据：
  1. 存档 `Saves\\Wahaha_450799035\\{Wahaha_450799035, SaveGameInfo}` 的 size/mtime；
  2. SMAPI 日志里 `Synchronizing 'NewDay'` 与 `SaveGame` 的**累计次数**（起点/终点两次快照做差）；
  3. 游戏进程 PID 是否还活着（脱离式起跑的进程不归 job 管）。

用法（起跑后立刻跑一次，跑完再跑一次，两次做差）：
    python scratch\\_run4_snapshot.py --tag start
    python scratch\\_run4_snapshot.py --tag end
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
SAVE_NAME = "Wahaha_450799035"
OUT = REPO / "scratch" / "run4-external-snapshots.jsonl"


def stat_of(p: Path) -> dict:
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
    ap.add_argument("--journal", default=str(REPO / "logs" / "longrun-3day-llm-run4.jsonl"))
    args = ap.parse_args()

    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    sd = Path(appdata) / "StardewValley" / "Saves" / SAVE_NAME
    smapi = Path(appdata) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
    jp = Path(args.journal)
    pid_file = REPO / "logs" / "run4.pid"

    snap: dict = {"tag": args.tag, "at": datetime.now().isoformat(timespec="seconds")}

    snap["save_main"] = stat_of(sd / SAVE_NAME)
    snap["save_info"] = stat_of(sd / "SaveGameInfo")

    if smapi.exists():
        text = smapi.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        snap["smapi_lines"] = len(lines)
        snap["smapi_newday"] = len(re.findall(r"Synchronizing 'NewDay'", text))
        snap["smapi_save"] = len(re.findall(r"SaveGame\.Save|SaveGameMenu", text))
    else:
        snap["smapi_lines"] = None
        snap["smapi_newday"] = None
        snap["smapi_save"] = None

    if jp.exists():
        rows = [ln for ln in jp.read_text(encoding="utf-8").splitlines() if ln.strip()]
        snap["journal_lines"] = len(rows)
        fin = None
        last = None
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
        snap["journal_lines"] = None
        snap["journal_last_event"] = None
        snap["journal_finish"] = None

    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
    snap["pid"] = pid
    if pid is not None:
        # 只读存活判断：Windows 上 os.kill(pid, 0) 语义不可靠，用 tasklist 更实在
        import subprocess
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10)
            snap["pid_alive"] = str(pid) in (out.stdout or "")
        except Exception as exc:  # noqa: BLE001
            snap["pid_alive"] = f"? {type(exc).__name__}: {exc}"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snap, ensure_ascii=False) + "\n")

    print(json.dumps(snap, ensure_ascii=False, indent=1))
    print(f"\n已追加到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
