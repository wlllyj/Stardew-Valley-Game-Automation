# -*- coding: utf-8 -*-
"""只读：把彩排日志里 sleep 失败那两行的 receipt 完整打出来（原 grep 输出被截断）。"""
import json
import sys

PATH = r"D:\Deepseek Harness Workspace\星露谷游戏自动化\logs\longrun-rehearsal-0.7.22.jsonl"
WANT = {50, 112}

with open(PATH, "r", encoding="utf-8") as fh:
    for i, line in enumerate(fh, 1):
        if i not in WANT:
            continue
        try:
            rec = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            print(f"--- line {i}: JSON 解析失败 {exc}")
            continue
        print(f"===== line {i} =====")
        print("event   :", rec.get("event"))
        print("t       :", rec.get("t"))
        print("code    :", rec.get("code"))
        print("before  :", json.dumps(rec.get("before"), ensure_ascii=False))
        print("after   :", json.dumps(rec.get("after"), ensure_ascii=False))
        rc = rec.get("receipt")
        print("receipt :", rc if isinstance(rc, str) else json.dumps(rc, ensure_ascii=False))
        print()
sys.stdout.flush()
