# -*- coding: utf-8 -*-
"""A″（runA8-0743）起点基准（只读）。

记录：
  1) 长跑 PID 存活（默认从 logs/longrun-runA8-0743.pid 读，可用 --pid 覆盖）
  2) SMAPI-latest.txt 的**起点行号基准**（总行数 + 末尾带时间戳行 + 六串累计计数）
  3) 账本行数与末事件
  4) 存档四件 size/mtime/SHA256
写 `logs/runA8-0743-smapi-baseline.json`；之后跨日只统计 `line_no > baseline_lines` 的增量。
退出码 0 = 记录成功；2 = SMAPI 读不到；3 = PID 文件缺失（仍会写其余部分）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOGS = os.path.join(ROOT, "logs")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SAVE_FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
PATS = {
    "newday": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "save_called": "SaveGame.Save() called.",
    "save_task": "Synchronizing 'Save' task",
    "completed": "completed without exceptions",
    "after_save": "after save, starting",
}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def l16_real(line: str) -> bool:
    """L16：插件描述行也含关键词，必须有 [HH:MM:SS LVL CHAN] 前缀且不含插件特征。"""
    if TS.match(line) is None:
        return False
    return (" by AgentFarm " not in line) and ("| v0." not in line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--pid-file", default=os.path.join(LOGS, "longrun-runA8-0743.pid"))
    ap.add_argument("--journal", default=os.path.join(LOGS, "longrun-runA8-0743.jsonl"))
    ap.add_argument("--out", default=os.path.join(LOGS, "runA8-0743-smapi-baseline.json"))
    args = ap.parse_args()

    rec: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": None, "pid_alive": None,
                 "pid_file": args.pid_file, "pid_file_exists": os.path.exists(args.pid_file)}

    pid = args.pid
    if pid is None and os.path.exists(args.pid_file):
        try:
            pid = int(open(args.pid_file, encoding="utf-8").read().strip())
        except Exception:  # noqa: BLE001
            pid = None
    rec["pid"] = pid
    if pid:
        try:
            out = os.popen(f'tasklist /FI "PID eq {pid}" /FO CSV /NH').read()
            rec["pid_alive"] = pid is not None and str(pid) in out
        except Exception as exc:  # noqa: BLE001
            rec["pid_alive"] = f"<检测失败：{type(exc).__name__}>"

    # SMAPI 起点基准
    if not os.path.exists(SMAPI):
        print(f"!! SMAPI 不存在：{SMAPI}", file=sys.stderr)
        rc_smapi = 2
        rec["smapi"] = {"exists": False}
    else:
        rc_smapi = 0
        lines = open(SMAPI, encoding="utf-8", errors="replace").read().splitlines()
        ts_lines = [(i, TS.match(s).group(1)) for i, s in enumerate(lines, 1) if TS.match(s)]
        counts = {k: sum(1 for s in lines if v in s) for k, v in PATS.items()}
        # 修正后 save_called（L16 判别）
        counts["save_called_corrected"] = sum(
            1 for s in lines if PATS["save_called"] in s and l16_real(s))
        rec["smapi"] = {"path": SMAPI, "exists": True, "total_lines": len(lines),
                        "size": os.path.getsize(SMAPI),
                        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(SMAPI))),
                        "last_ts_line": ({"line_no": ts_lines[-1][0], "time": ts_lines[-1][1]} if ts_lines else None),
                        "window_starts_at_line": len(lines) + 1,
                        "cumulative_counts": counts}

    # 账本
    if os.path.exists(args.journal):
        jl = open(args.journal, encoding="utf-8", errors="replace").read().splitlines()
        last = {}
        for ln in reversed(jl):
            if ln.strip():
                try:
                    last = json.loads(ln)
                except Exception:  # noqa: BLE001
                    pass
                break
        rec["journal"] = {"path": args.journal, "lines": len(jl),
                          "last_event": last.get("event"), "last_t": last.get("t"),
                          "size": os.path.getsize(args.journal),
                          "mtime": time.strftime("%Y-%m-%d %H:%M:%S",
                                                 time.localtime(os.path.getmtime(args.journal)))}
    else:
        rec["journal"] = {"path": args.journal, "exists": False}

    # 存档四件
    files = {}
    for name in SAVE_FILES:
        p = os.path.join(SAVE_DIR, name)
        if not os.path.exists(p):
            files[name] = None
            continue
        st = os.stat(p)
        files[name] = {"size": st.st_size,
                       "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                       "sha256": sha256(p)}
    rec["saves"] = {"save_dir": SAVE_DIR, "exists": os.path.isdir(SAVE_DIR), "files": files}

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)

    s = rec.get("smapi") or {}
    print(f"PID = {rec['pid']}  alive={rec['pid_alive']}  pid_file_exists={rec['pid_file_exists']}")
    print(f"SMAPI 总行数 = {s.get('total_lines')}  size={s.get('size')}  mtime={s.get('mtime')}")
    print(f"  末条带时间戳行 = {s.get('last_ts_line')}")
    print(f"  **窗口起点行号 = {s.get('window_starts_at_line')}**（此后 line_no >= 该值才算本跑）")
    print(f"  累计六串 = {json.dumps(s.get('cumulative_counts'), ensure_ascii=False)}")
    print(f"账本 = {json.dumps(rec.get('journal'), ensure_ascii=False)}")
    for name, v in files.items():
        print(f"  存档 {name}: {None if v is None else (v['size'], v['mtime'], v['sha256'][:16])}")
    print(f"已写 {args.out}")
    return rc_smapi


if __name__ == "__main__":
    sys.exit(main())
