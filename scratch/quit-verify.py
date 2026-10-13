# -*- coding: utf-8 -*-
"""退出前后取证（只读 + 一次 tasklist；不写任何游戏状态）。

用法：python scratch\\quit-verify.py --label 退出前
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time

BRIDGE_JSON = os.path.join(os.environ["APPDATA"], "StardewValley", "AgentFarm", "bridge.json")
SAVE_DIR = os.path.join(os.environ["APPDATA"], "StardewValley", "Saves", "Wahaha_450799035")
SMAPI = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
PORT = 17890


def procs(image: str) -> list[int]:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        return [f"tasklist失败:{exc}"]  # type: ignore[list-item]
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("info:"):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].replace('"', "").lower() == image.lower():
            pids.append(int(parts[1].replace('"', "")))
    return pids


def port_open() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    print("=" * 68)
    print(f"[{args.label}] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"游戏进程 StardewModdingAPI = {procs('StardewModdingAPI.exe')}")
    print(f"python 进程                = {procs('python.exe')}")
    print(f"端口 {PORT} 监听            = {port_open()}")
    if os.path.exists(BRIDGE_JSON):
        st = os.stat(BRIDGE_JSON)
        with open(BRIDGE_JSON, encoding="utf-8") as fh:
            raw = fh.read()
        print(f"bridge.json = 存在 mtime={time.strftime('%H:%M:%S', time.localtime(st.st_mtime))} "
              f"size={st.st_size} 内容={raw[:400]}")
    else:
        print("bridge.json = **不存在（已删除）**")

    print("存档三条读数：")
    if os.path.isdir(SAVE_DIR):
        for name in sorted(os.listdir(SAVE_DIR)):
            p = os.path.join(SAVE_DIR, name)
            if os.path.isfile(p):
                st = os.stat(p)
                print(f"   {name:24} size={st.st_size:9} mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}.{st.st_mtime_ns % 1_000_000_000:09d}")
    else:
        print("   （存档目录不存在）")

    if os.path.exists(SMAPI):
        st = os.stat(SMAPI)
        with open(SMAPI, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        print(f"SMAPI-latest.txt 行数={len(lines)} mtime={time.strftime('%H:%M:%S', time.localtime(st.st_mtime))}")
        print("SMAPI 尾部 10 行：")
        for ln in lines[-10:]:
            print(f"   {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
