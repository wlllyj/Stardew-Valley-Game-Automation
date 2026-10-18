# -*- coding: utf-8 -*-
"""夹具：假 stop-game（供 tools/run-guardian.py 离线自测；**绝不碰真游戏**）。

行为：把 argv/时刻写到 `$GUARDIAN_FAKE_RECEIPT`，打印一行，按 `$GUARDIAN_FAKE_RC` 退出。
Guardian 自测用它证明「判据成立 ⇒ 真的调用了 stop 脚本」；不发任何桥请求、不 taskkill。
"""
from __future__ import annotations

import json
import os
import sys
import time

ARGV = sys.argv[1:]
RECEIPT = os.environ.get("GUARDIAN_FAKE_RECEIPT", "")
RC = int(os.environ.get("GUARDIAN_FAKE_RC", "0") or "0")

print(f"[fake-stop] called argv={ARGV} cwd={os.getcwd()} rc={RC}")
if RECEIPT:
    payload = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "argv": sys.argv,
               "cwd": os.getcwd(), "rc": RC,
               "note": "fixture only：不请求桥、不 taskkill、不碰存档"}
    with open(RECEIPT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
sys.exit(RC)
