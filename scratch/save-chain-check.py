# -*- coding: utf-8 -*-
"""日切保存守卫：SMAPI 六串配对检查（离线，只读文件，不碰桥/游戏）。

用途：验收"每一次跨日都必须落盘"。六串 = 
  ① `Synchronizing 'NewDay' task`      ② `Context: before save.`
  ③ `SaveGame.Save() called.`          ④ `Synchronizing 'Save' task`
  ⑤ `completed without exceptions`     ⑥ `Context: after save`

判据（Lead m04100 / task-236 口径）：
  * `NewDay > Save called`                  ⇒ **FAIL（末次跨日未落盘）**，退出码 1
  * `NewDay == Save called == after save`   ⇒ **PASS**，退出码 0
  * 缺 SMAPI / 窗口里没有带时间戳的行 / 六串互相不一致但又不构成上面两条
                                           ⇒ **无法判定**，退出码 2（缺失≠通过）
另给一条**顺序判据**（比计数更硬）：最后一次 `NewDay` 的行号若晚于最后一次
`SaveGame.Save() called.` 的行号 ⇒ 末次跨日后没有任何保存调用 ⇒ 同样 FAIL。

`SaveGame.Save() called.` 的假阳性判别式（L16：SMAPI 插件描述里就写着这句话）：
  有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 **且** 不含 ` by AgentFarm ` / `| v0.`
两条都满足才算一次真调用；原始计数与修正计数都会打印。

用法
----
  python scratch\\save-chain-check.py --smapi logs\\run10h-smapi-window.txt --journal logs\\longrun-smoke-0740.jsonl
  python scratch\\save-chain-check.py --smapi <窗口> --journal <账本> --save-dir "%APPDATA%\\StardewValley\\Saves\\Wahaha_450799035"
  python scratch\\save-chain-check.py --smapi <窗口> --after 12:14:00 --before 12:24:30 --out scratch\\save-chain.json
  python scratch\\save-chain-check.py --selftest

退出码：0 = PASS / 1 = FAIL / 2 = 无法判定 / 3 = 输入缺失（文件不存在）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})(?:\.\d+)?\s+([A-Z]+)\s+([^\]]+)\]")
L16_AGENTFARM_MARK = " by AgentFarm "
L16_VERSION_MARK = "| v0."

PATTERNS = {
    "newday": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save.",
    "save_called": "SaveGame.Save() called.",
    "save_task": "Synchronizing 'Save' task",
    "completed": "completed without exceptions",
    "after_save": "Context: after save",
}

SAVE_FILES = ("Wahaha_450799035", "SaveGameInfo", "Wahaha_450799035_old", "SaveGameInfo_old")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def is_real_save_called(line: str) -> bool:
    """L16 判别式：必须有 [HH:MM:SS LEVEL CHANNEL] 前缀，且不含插件描述特征。"""
    if TS.match(line) is None:
        return False
    if L16_AGENTFARM_MARK in line or L16_VERSION_MARK in line:
        return False
    return True


def scan(smapi_path: str, after: str | None, before: str | None) -> dict:
    lines = open(smapi_path, encoding="utf-8", errors="replace").read().splitlines()
    win = []
    for idx, line in enumerate(lines, 1):
        m = TS.match(line)
        if not m:
            continue
        t = m.group(1)
        if after and t < after:
            continue
        if before and t > before:
            continue
        win.append((idx, t, line))

    hits: dict[str, list] = {k: [] for k in PATTERNS}
    raw_save_called = []
    for idx, t, line in win:
        for key, needle in PATTERNS.items():
            if needle in line:
                if key == "save_called":
                    raw_save_called.append((idx, t))
                    if not is_real_save_called(line):
                        continue
                hits[key].append((idx, t))
    return {"total_lines": len(lines), "window_lines": len(win), "hits": hits,
            "save_called_raw": raw_save_called, "window": [after, before]}


def judge(scan_res: dict) -> dict:
    h = scan_res["hits"]
    n_new = len(h["newday"])
    n_save = len(h["save_called"])
    n_after = len(h["after_save"])
    n_before = len(h["before_save"])
    n_task = len(h["save_task"])
    n_done = len(h["completed"])

    last_new = h["newday"][-1][0] if h["newday"] else None
    last_save = h["save_called"][-1][0] if h["save_called"] else None
    last_after = h["after_save"][-1][0] if h["after_save"] else None

    reasons: list[str] = []
    if n_new == 0:
        verdict, code = "无法判定", 2
        reasons.append("窗口内没有 `Synchronizing 'NewDay' task`（没有跨日，或窗口没覆盖到）")
    elif last_save is not None and last_new is not None and last_new > last_save:
        verdict, code = "FAIL", 1
        reasons.append(f"末次 NewDay 行号 {last_new} 晚于最后一次 Save called 行号 {last_save} ⇒ 末次跨日后没有保存调用")
    elif n_new > n_save:
        verdict, code = "FAIL", 1
        reasons.append(f"NewDay {n_new} > Save called {n_save} ⇒ 有跨日没落盘（差 {n_new - n_save}）")
    elif n_new == n_save == n_after:
        verdict, code = "PASS", 0
    else:
        verdict, code = "无法判定", 2
        reasons.append(f"六串不一致且不构成已知 FAIL 形态：NewDay {n_new} / Save called {n_save} / after save {n_after}")

    if verdict == "PASS" and not (n_before == n_new and n_task == n_new and n_done == n_new):
        reasons.append(f"PASS 但六串不齐：before {n_before} / save task {n_task} / completed {n_done}（各应为 {n_new}）")
    return {"verdict": verdict, "exit_code": code, "counts": {
        "newday": n_new, "before_save": n_before, "save_called": n_save,
        "save_called_raw": len(scan_res["save_called_raw"]),
        "save_task": n_task, "completed": n_done, "after_save": n_after},
        "lines": {k: [i for i, _t in v] for k, v in h.items()},
        "times": {k: [t for _i, t in v] for k, v in h.items()},
        "last_newday_line": last_new, "last_save_called_line": last_save, "last_after_save_line": last_after,
        "reasons": reasons}


def save_listing(save_dir: str) -> dict:
    out = {}
    if not save_dir or not os.path.isdir(save_dir):
        return {"save_dir": save_dir, "exists": False, "files": {}}
    for name in SAVE_FILES:
        p = os.path.join(save_dir, name)
        if not os.path.exists(p):
            out[name] = None
            continue
        st = os.stat(p)
        out[name] = {"size": st.st_size,
                     "mtime": __import__("time").strftime("%Y-%m-%d %H:%M:%S", __import__("time").localtime(st.st_mtime)),
                     "sha256": sha256(p)}
    return {"save_dir": save_dir, "exists": True, "files": out}


def journal_brief(path: str | None) -> dict:
    if not path or not os.path.exists(path):
        return {"journal": path, "exists": False}
    recs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    recs.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
    fin = [r for r in recs if r.get("event") == "finish"]
    de = [r for r in recs if r.get("event") == "day_end"]
    return {"journal": path, "exists": True, "lines": len(recs),
            "day_end": len(de), "finish": fin[-1] if fin else None,
            "day_end_verified": [r.get("verified") for r in de]}


# ------------------------------------------------------------------ 自测
def _mk(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def selftest() -> int:
    ok = True
    tmp = tempfile.mkdtemp(prefix="savechain-")
    try:
        l16 = ("[12:00:00 INFO  SMAPI]    AgentFarm Bridge 0.7.40 by AgentFarm | v0.7.40"
               "（改动日志里写着 SaveGame.Save() called.）")
        # 夹具 A：FAIL —— NewDay 3 但只有 2 次 Save called（0.7.40 现场形态）
        a = os.path.join(tmp, "fail.txt")
        _mk(a, [
            "[12:14:43 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:14:44 TRACE SMAPI] Context: before save.",
            "[12:14:44 TRACE game] SaveGame.Save() called.",
            "[12:14:44 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:14:45 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:14:46 TRACE SMAPI] Context: after save, starting fall 27 Y1.",
            "[12:18:20 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:18:21 TRACE SMAPI] Context: before save.",
            "[12:18:21 TRACE game] SaveGame.Save() called.",
            "[12:18:21 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:18:22 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:18:23 TRACE SMAPI] Context: after save, starting fall 28 Y1.",
            l16,
            "[12:20:40 TRACE SMAPI] Synchronizing 'NewDay' task...",
        ])
        r = judge(scan(a, None, None))
        print(f"[selftest A] verdict={r['verdict']} counts={r['counts']}")
        if r["verdict"] != "FAIL" or r["exit_code"] != 1:
            print("!! 夹具 A 应为 FAIL"); ok = False
        if r["counts"]["save_called"] != 2 or r["counts"]["save_called_raw"] != 3:
            print("!! 夹具 A：修正后 save_called 应为 2、原始应为 3（L16 那条只在原始计数里）"); ok = False

        # 夹具 B：PASS —— 3/3/3，六串齐全
        b = os.path.join(tmp, "pass.txt")
        _mk(b, [
            "[12:14:43 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:14:44 TRACE SMAPI] Context: before save.",
            "[12:14:44 TRACE game] SaveGame.Save() called.",
            "[12:14:44 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:14:45 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:14:46 TRACE SMAPI] Context: after save, starting fall 27 Y1.",
            "[12:18:20 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:18:21 TRACE SMAPI] Context: before save.",
            "[12:18:21 TRACE game] SaveGame.Save() called.",
            "[12:18:21 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:18:22 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:18:23 TRACE SMAPI] Context: after save, starting fall 28 Y1.",
            l16,
            "[12:20:40 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:23:53 TRACE SMAPI] Context: before save.",
            "[12:23:53 TRACE game] SaveGame.Save() called.",
            "[12:23:53 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:23:54 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:23:56 TRACE SMAPI] Context: after save, starting winter 1 Y1.",
        ])
        r = judge(scan(b, None, None))
        print(f"[selftest B] verdict={r['verdict']} counts={r['counts']}")
        if r["verdict"] != "PASS" or r["exit_code"] != 0:
            print("!! 夹具 B 应为 PASS"); ok = False

        # 夹具 C：无法判定 —— 窗口里没有带时间戳的行
        c = os.path.join(tmp, "empty.txt")
        _mk(c, ["no timestamps here", "still nothing"])
        r = judge(scan(c, None, None))
        print(f"[selftest C] verdict={r['verdict']}")
        if r["verdict"] != "无法判定" or r["exit_code"] != 2:
            print("!! 夹具 C 应为无法判定"); ok = False

        # 夹具 D：顺序判据 —— NewDay 在最后一次 Save called 之后（计数相等也必须 FAIL）
        d = os.path.join(tmp, "order.txt")
        _mk(d, [
            "[12:14:43 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:14:44 TRACE SMAPI] Context: before save.",
            "[12:14:44 TRACE game] SaveGame.Save() called.",
            "[12:14:44 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:14:45 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:20:40 TRACE SMAPI] Synchronizing 'NewDay' task...",
            "[12:20:41 TRACE SMAPI] Context: before save.",
            "[12:20:41 TRACE game] SaveGame.Save() called.",
            "[12:20:41 TRACE SMAPI] Synchronizing 'Save' task...",
            "[12:20:42 TRACE game] SaveGame.Save() completed without exceptions.",
            "[12:23:53 TRACE SMAPI] Synchronizing 'NewDay' task...",
        ])
        r = judge(scan(d, None, None))
        print(f"[selftest D] verdict={r['verdict']} last_new={r['last_newday_line']} last_save={r['last_save_called_line']}")
        if r["verdict"] != "FAIL":
            print("!! 夹具 D 应为 FAIL（顺序判据）"); ok = False

        print(f"\nSELFTEST {'PASS' if ok else 'FAIL'}（A/B/C/D 四个夹具：一红一绿 + 无法判定 + 顺序判据）")
        return 0 if ok else 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smapi", help="SMAPI 窗口文件（冻结副本）")
    ap.add_argument("--journal", help="脑账本 JSONL（可选）")
    ap.add_argument("--save-dir", help="存档目录（可选，只陈述不判红）")
    ap.add_argument("--after", help="窗口起点 HH:MM:SS（含）")
    ap.add_argument("--before", help="窗口终点 HH:MM:SS（含）")
    ap.add_argument("--out", help="结果 JSON 输出路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.smapi:
        print("需要 --smapi（或 --selftest）", file=sys.stderr)
        return 3
    if not os.path.exists(args.smapi):
        print(f"没有这个 SMAPI 窗口文件：{args.smapi} ⇒ 无法判定", file=sys.stderr)
        return 3

    res = scan(args.smapi, args.after, args.before)
    verdict = judge(res)
    saves = save_listing(args.save_dir) if args.save_dir else {"save_dir": None, "exists": False, "files": {}}
    jb = journal_brief(args.journal)

    print("=== 六串配对（日切保存守卫）===")
    print(f"SMAPI 窗口文件 = {args.smapi}")
    print(f"文件总行 = {res['total_lines']} / 窗口内带时间戳行 = {res['window_lines']} (窗口 {args.after or '-'}–{args.before or '-'})")
    c = verdict["counts"]
    print(f"[1] NewDay                        = {c['newday']:2} 行号 {verdict['lines']['newday']}")
    print(f"[2] Context: before save          = {c['before_save']:2} 行号 {verdict['lines']['before_save']}")
    print(f"[3] SaveGame.Save() called         = {c['save_called']:2} 行号 {verdict['lines']['save_called']}（原始 {c['save_called_raw']}，L16 假阳性 {c['save_called_raw'] - c['save_called']}）")
    print(f"[4] Synchronizing 'Save' task      = {c['save_task']:2} 行号 {verdict['lines']['save_task']}")
    print(f"[5] completed without exceptions   = {c['completed']:2} 行号 {verdict['lines']['completed']}")
    print(f"[6] Context: after save            = {c['after_save']:2} 行号 {verdict['lines']['after_save']}")
    print(f"末次 NewDay 行 {verdict['last_newday_line']} / 末次 Save called 行 {verdict['last_save_called_line']} / 末次 after save 行 {verdict['last_after_save_line']}")
    for r in verdict["reasons"]:
        print(f"  · {r}")
    print(f"\nVERDICT: {verdict['verdict']}（退出码 {verdict['exit_code']}）")

    if saves["exists"]:
        print(f"\n=== 存档四件（{saves['save_dir']}，只陈述不判红）===")
        for name, meta in saves["files"].items():
            if meta is None:
                print(f"  {name:24} <缺失>")
            else:
                print(f"  {name:24} {meta['size']:>9} B / {meta['mtime']} / {meta['sha256'][:16]}…")
        last_after_t = verdict["times"]["after_save"][-1] if verdict["times"]["after_save"] else None
        main_meta = saves["files"].get("Wahaha_450799035")
        if last_after_t and main_meta:
            print(f"  陈述：SMAPI 末次 after save 时刻 {last_after_t}；主档 mtime {main_meta['mtime']}"
                  f"（同一天内 smapi 晚于存档 = 存档可能是最后一次 after save 之前的；跨天则不可直接比）")
    if jb.get("exists"):
        print(f"\n=== 账本 === {jb['lines']} 行 / day_end {jb['day_end']} / verified {jb['day_end_verified']} / finish {bool(jb['finish'])}")

    payload = {"smapi": args.smapi, "journal": args.journal, "save_dir": args.save_dir,
               "window": [args.after, args.before], "scan_summary": {k: res[k] for k in ("total_lines", "window_lines")},
               "verdict": verdict, "saves": saves, "journal_brief": jb}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\n已写出 {args.out}")
    return verdict["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
