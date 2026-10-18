# -*- coding: utf-8 -*-
"""A7/B7 长跑收尾取证（`scratch/run-tools-0739.py` 的参数化升级版，**不动原件**）。

三样收口（Lead m03672 / m04395）：
1) **SMAPI 时点冻结**：源 → 副本 → 双侧 SHA256 + BYTE_IDENTICAL。
   实现：**一次性读源到内存**，用同一份字节写副本、算 SHA ⇒ 避免"先算源再算副本、源继续长"的口径漏洞。
   **默认拒绝覆盖已存在副本**（要覆盖显式 `--refreeze`），防止把真跑窗口被后续 SMAPI 内容冲掉。
2) **六串计数**：NewDay / before save / `SaveGame.Save() called.` / `Synchronizing 'Save' task`（两种写法都数）
   / completed without exceptions / after save；`Save called` 带 L16 假阳性判别式（有 `[HH:MM:SS LEVEL CHANNEL]`
   前缀且不含 ` by AgentFarm ` / `| v0.`），原始/修正双计数都打印。
3) **三检查器同向**：`tools/verify-run3.py` + `tools/analyze-longrun.py` + `scratch/run9-lead-check.py`，
   原文落 `logs/<tag>-{verify,analyze,lead-check}.txt`，打印 rc / 判决行 / ✅❌ 摘要 + 同向判定。

用法（A7 / B7 唯一差异 = `--journal` 与 `--tag`）：
  python scratch\\run-tools-0742.py --tag runA7-0742
  python scratch\\run-tools-0742.py --tag runB7-0742 --journal logs\\longrun-runB7-0742.jsonl
  python scratch\\run-tools-0742.py --tag runA7-0742 --dry-run          # 只打印计划与输入体检
  python scratch\\run-tools-0742.py --tag runA7-0742 --no-freeze        # 用已冻结副本
  python scratch\\run-tools-0742.py --tag runA7-0742 --refreeze         # 显式覆盖副本

约定：`--tag X` ⇒ journal 默认 `logs/X.jsonl`；SMAPI 副本 `logs/X-smapi-window.txt`；
检查器输出 `logs/X-{verify,analyze,lead-check}.txt`；快照默认 `scratch/X-external-snapshots.jsonl`；汇总 `logs/X-tools.json`。

退出码：0 = 取证完成（检查器红只如实记录、不改退出码）
        12 = SMAPI 冻结失败（源不存在 / 副本已存在且未 --refreeze / --no-freeze 但副本缺失）
        13 = --after 晚于 --before
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PY = sys.executable
SMAPI_SRC = os.path.join(os.environ["APPDATA"], "StardewValley", "ErrorLogs", "SMAPI-latest.txt")
TS = re.compile(r"^\[(\d{2}:\d{2}:\d{2})")
DESC_MARKERS = (" by AgentFarm ", "| v0.")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest().upper()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _mtime(path: str) -> str | None:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.stat(path).st_mtime))
    except OSError:
        return None


def freeze_smapi(dst: str, *, refreeze: bool = False) -> dict:
    """一次性读源 → 写副本 → 双侧 SHA256 + 字节一致。默认拒绝覆盖（--refreeze 才覆盖）。"""
    if not os.path.exists(SMAPI_SRC):
        return {"src": SMAPI_SRC, "dst": dst, "ok": False, "error": "源不存在"}
    if os.path.exists(dst) and not refreeze:
        return {"src": SMAPI_SRC, "dst": dst, "ok": False, "frozen": False,
                "error": "副本已存在，拒绝覆盖（要覆盖加 --refreeze）",
                "existing_size": os.stat(dst).st_size, "existing_sha256": sha256_file(dst),
                "existing_mtime": _mtime(dst)}
    with open(SMAPI_SRC, "rb") as fh:
        src_bytes = fh.read()
    src_sha = sha256_bytes(src_bytes)
    src_size = len(src_bytes)
    with open(dst, "wb") as fh:
        fh.write(src_bytes)
    dst_sha = sha256_file(dst)
    st = os.stat(dst)
    return {"src": SMAPI_SRC, "dst": dst, "ok": True, "frozen": True,
            "src_size": src_size, "src_sha256": src_sha,
            "dst_size": st.st_size, "dst_sha256": dst_sha,
            "dst_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            "src_mtime": _mtime(SMAPI_SRC),
            "byte_identical": src_sha == dst_sha and src_size == st.st_size}


CHAIN_PATTERNS = {
    "NewDay": lambda s: "Synchronizing 'NewDay' task" in s,
    "before_save": lambda s: "Context: before save." in s,
    "Save_called": lambda s: ("SaveGame.Save() called." in s and TS.match(s) is not None
                              and not any(m in s for m in DESC_MARKERS)),
    "Save_called_raw": lambda s: ("SaveGame.Save() called." in s and TS.match(s) is not None),
    "Save_task": lambda s: "Synchronizing 'Save' task" in s,
    "Save_task_variant": lambda s: ("Synchronizing 'Save' task" in s
                                    or "Synchronizing 'SaveGame' task" in s),
    "completed": lambda s: "completed without exceptions" in s,
    "after_save": lambda s: "after save, starting" in s,
}


def count_chain(lines: list[str], after: str, before: str) -> dict:
    inwin = []
    for i, s in enumerate(lines, 1):
        m = TS.match(s)
        if not m:
            continue
        t = m.group(1)
        if after <= t <= before:
            inwin.append((i, t, s))
    counts: dict[str, list[int]] = {name: [i for i, _t, s in inwin if fn(s)]
                                    for name, fn in CHAIN_PATTERNS.items()}
    noise = {}
    for kw in ("Warping to Farm", "ERROR", "Disconnected", "ClosedGame", "Disposing",
               "soft_oal", "Exception", "GET /v1/observe", "POST /v1/exec"):
        noise[kw] = sum(1 for _i, _t, s in inwin if kw in s)
    pairs = {
        "NewDay_vs_Save_called": len(counts["NewDay"]) - len(counts["Save_called"]),
        "NewDay_vs_before_save": len(counts["NewDay"]) - len(counts["before_save"]),
        "NewDay_vs_completed": len(counts["NewDay"]) - len(counts["completed"]),
        "NewDay_vs_after_save": len(counts["NewDay"]) - len(counts["after_save"]),
        "l16_false_positive": len(counts["Save_called_raw"]) - len(counts["Save_called"]),
    }
    chain_ok = all(v == 0 for k, v in pairs.items() if k != "l16_false_positive")
    return {"in_window_lines": len(inwin), "total_lines": len(lines), "counts": counts,
            "noise": noise, "pairs": pairs, "chain_ok": chain_ok,
            "after": after, "before": before}


def window_of(lines: list[str]) -> tuple[str, str]:
    stamps = [TS.match(s).group(1) for s in lines if TS.match(s)]
    return (stamps[0], stamps[-1]) if stamps else ("00:00:00", "23:59:59")


def parse_verdicts(name: str, text: str) -> dict:
    out: dict[str, object] = {"raw_lines": len(text.splitlines())}
    lines = text.splitlines()
    if name == "verify-run3":
        for ln in lines:
            s = ln.strip()
            if s.startswith("{") and '"verdict"' in s:
                try:
                    d = json.loads(s)
                    out["verdict"] = d.get("verdict")
                    out["strict_verdict"] = d.get("strict_verdict")
                    out["problems"] = len(d.get("problems") or [])
                    out["history_problems"] = len(d.get("history_problems") or [])
                except Exception:  # noqa: BLE001
                    pass
    elif name == "analyze-longrun":
        for ln in lines:
            if "VERIFIED:" in ln:
                out["verdict_line"] = ln.strip()[:200]
                break
    else:
        marks = [ln.strip() for ln in lines if ("✅" in ln or "❌" in ln)]
        out["mark_lines"] = marks[-8:]
        out["reds"] = sum(1 for ln in marks if "❌" in ln)
    return out


def run_checkers(args, smapi_dst: str) -> list[dict]:
    if not os.path.exists(args.journal):
        print(f"[warn] journal 不存在：{args.journal} ⇒ 三检查器跳过（如实记 null，不猜）")
        return []
    if not os.path.exists(args.snapshots):
        print(f"[warn] 快照不存在：{args.snapshots}（lead-check 会把跨日证据判为无法判定）")
    jobs = [
        ("verify-run3", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "verify-run3.py"),
                         "--journal", args.journal, "--days", str(args.days), "--json"]),
        ("analyze-longrun", [PY, "-X", "utf8", os.path.join(ROOT, "tools", "analyze-longrun.py"),
                             "--journal", args.journal, "--window", str(args.window)]),
        ("lead-check", [PY, "-X", "utf8", os.path.join(ROOT, "scratch", "run9-lead-check.py"),
                        "--journal", args.journal, "--snapshots", args.snapshots, "--smapi", smapi_dst]),
    ]
    results = []
    for name, cmd in jobs:
        out_path = os.path.join(ROOT, "logs", f"{args.tag}-{name}.txt")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ROOT)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(r.stdout or "")
            if r.stderr:
                fh.write("\n--- stderr ---\n" + r.stderr)
        parsed = parse_verdicts(name, r.stdout or "")
        results.append({"name": name, "rc": r.returncode, "out": out_path, "parsed": parsed,
                        "stdout_chars": len(r.stdout or ""),
                        "stderr_tail": (r.stderr or "").strip()[-300:]})
        print(f"[{name}] rc={r.returncode} → {out_path}")
        if parsed.get("verdict") or parsed.get("strict_verdict"):
            print(f"    verdict={parsed.get('verdict')} strict={parsed.get('strict_verdict')} "
                  f"problems={parsed.get('problems')} history={parsed.get('history_problems')}")
        if parsed.get("verdict_line"):
            print(f"    {parsed['verdict_line']}")
        for ln in (parsed.get("mark_lines") or [])[-4:]:
            print(f"    {ln[:180]}")
        if parsed.get("stderr_tail"):
            print(f"    stderr: {parsed['stderr_tail'][:200]}")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="A7/B7 长跑收尾取证（SMAPI 冻结 + 六串 + 三检查器）")
    ap.add_argument("--tag", default="runA7-0742", help="产物前缀（默认 runA7-0742）")
    ap.add_argument("--journal", default=None, help="账本路径（默认 logs/<tag>.jsonl）")
    ap.add_argument("--smapi", default=None, help="SMAPI 副本路径（默认 logs/<tag>-smapi-window.txt）")
    ap.add_argument("--snapshots", default=None, help="外部快照（默认 scratch/<tag>-external-snapshots.jsonl）")
    ap.add_argument("--after", default=None, help="窗口起点 HH:MM:SS（默认整文件首个时间戳）")
    ap.add_argument("--before", default=None, help="窗口终点 HH:MM:SS（默认整文件末个时间戳）")
    ap.add_argument("--days", type=int, default=5, help="verify-run3 --days（默认 5）")
    ap.add_argument("--window", type=int, default=5, help="analyze-longrun --window（默认 5）")
    ap.add_argument("--no-freeze", action="store_true", help="不重新冻结，直接用现有副本")
    ap.add_argument("--refreeze", action="store_true", help="显式覆盖已存在的 SMAPI 副本")
    ap.add_argument("--json", default=None, help="汇总 JSON（默认 logs/<tag>-tools.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划与输入体检，不动任何文件")
    args = ap.parse_args()

    args.journal = args.journal or os.path.join(ROOT, "logs", f"{args.tag}.jsonl")
    smapi_dst = args.smapi or os.path.join(ROOT, "logs", f"{args.tag}-smapi-window.txt")
    args.snapshots = args.snapshots or os.path.join(ROOT, "scratch", f"{args.tag}-external-snapshots.jsonl")
    out_json = args.json or os.path.join(ROOT, "logs", f"{args.tag}-tools.json")

    print("=== 输入体检 ===")
    for label, path in (("journal", args.journal), ("snapshots", args.snapshots),
                        ("smapi_src", SMAPI_SRC), ("smapi_dst", smapi_dst),
                        ("verify-run3", os.path.join(ROOT, "tools", "verify-run3.py")),
                        ("analyze-longrun", os.path.join(ROOT, "tools", "analyze-longrun.py")),
                        ("run9-lead-check", os.path.join(ROOT, "scratch", "run9-lead-check.py"))):
        print(f"  {label:16} exists={os.path.exists(path)}  {path}")

    if args.dry_run:
        print("\n=== 计划（dry-run，不动文件）===")
        print(f"  1) 冻结 SMAPI：{SMAPI_SRC} → {smapi_dst}"
              f"{'（--no-freeze：跳过）' if args.no_freeze else ('（--refreeze：覆盖）' if args.refreeze else '（已存在则拒绝覆盖）')}")
        print(f"  2) 六串计数窗口：{args.after or '<整文件首个时间戳>'} – {args.before or '<整文件末个时间戳>'}")
        print(f"  3) 三检查器：verify-run3 --days {args.days} / analyze-longrun --window {args.window} "
              f"/ run9-lead-check（--snapshots {args.snapshots}）")
        print(f"  4) 汇总：{out_json}")
        print("DRY OK（未写任何文件）")
        return 0

    evidence: dict[str, object] = {"tag": args.tag, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "journal": args.journal, "smapi_dst": smapi_dst,
                                   "snapshots": args.snapshots}

    print("\n=== 1) SMAPI 时点冻结 ===")
    if args.no_freeze:
        if not os.path.exists(smapi_dst):
            print(f"!! --no-freeze 但副本不存在：{smapi_dst}", file=sys.stderr)
            return 12
        freeze = {"src": SMAPI_SRC, "dst": smapi_dst, "ok": True, "no_freeze": True,
                  "dst_size": os.stat(smapi_dst).st_size, "dst_sha256": sha256_file(smapi_dst),
                  "dst_mtime": _mtime(smapi_dst), "byte_identical": None}
    else:
        freeze = freeze_smapi(smapi_dst, refreeze=args.refreeze)
        if not freeze.get("ok"):
            print(f"!! 冻结失败：{freeze.get('error')}", file=sys.stderr)
            return 12
    for k in ("src", "dst", "src_size", "src_sha256", "dst_size", "dst_sha256",
              "dst_mtime", "byte_identical"):
        print(f"  {k:14} = {freeze.get(k)}")
    evidence["smapi_freeze"] = freeze

    print("\n=== 2) 六串计数 ===")
    with open(smapi_dst, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    w0, w1 = window_of(lines)
    after = args.after or w0
    before = args.before or w1
    if args.after and args.before and args.after > args.before:
        print("!! --after 晚于 --before", file=sys.stderr)
        return 13
    chain = count_chain(lines, after, before)
    print(f"  窗口 {after}–{before}：带时间戳行 {chain['in_window_lines']} / 文件总行 {chain['total_lines']}")
    c = chain["counts"]
    for name in ("NewDay", "before_save", "Save_called", "Save_called_raw", "Save_task",
                 "Save_task_variant", "completed", "after_save"):
        print(f"  {name:18} = {len(c[name]):2}  行号 {c[name]}")
    for k, v in chain["pairs"].items():
        print(f"  >>> {k:26} = {v:+d}" if k else "")
    print(f"  >>> 六串配对 ⇒ {'✅ 全部相等' if chain['chain_ok'] else '⚠ 有差值（见上）'}")
    for k, v in chain["noise"].items():
        print(f"  {k:20} = {v}")
    evidence["smapi_chain"] = chain

    print("\n=== 3) 三检查器同向 ===")
    results = run_checkers(args, smapi_dst)
    evidence["checkers"] = results
    if results:
        rcs = {r["name"]: r["rc"] for r in results}
        green = sum(1 for v in rcs.values() if v == 0)
        print(f"\n  rc 汇总：{rcs} ⇒ "
              f"{'全部 rc=0（同向绿）' if green == len(results) else f'{green}/{len(results)} rc=0（不同向，需人判）'}")
        evidence["checkers_same_direction"] = green == len(results)

    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, ensure_ascii=False, indent=2)
    print(f"\n汇总已写：{out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
