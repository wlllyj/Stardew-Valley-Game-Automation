#!/usr/bin/env python
"""脱离式起跑长跑（run6 及以后）—— 让长跑活过 agent 回合边界。

## 为什么必须有这个脚本（条目 040/041 的教训）

`pwsh` 工具的托管后台作业（`run_in_background: true`）会在 **agent 回合边界**被连根 teardown：
run4 因此只跑了 13 秒 —— 账本停在 `t=12.85s`、没有 `day_end`/`finish`、`job_output` 查无此作业、
stdout 不可恢复（探针实测：回合结束后第 4 拍就不再写盘）。所以长跑必须用**独立进程**起，
之后只按 PID + 文件只读轮询，**绝不用 `job_output` 跑长跑**。

## 它做什么 / 不做什么

做：①拒绝重复起跑（PID 还活着就退 3）②可选的 `--preflight-expect` 前置体检（红灯不跑）
③`subprocess.Popen(..., DETACHED_PROCESS)` 起 `tools/run-longrun.py`，stdout/stderr 各自落文件
④写 PID 文件 + 版本四要素 sidecar（HEAD / 被测文件 SHA256+mtime / PID+起跑时刻 / 工作树状态）
⑤体检 N 秒后打印 console 尾部与账本行数，然后**返回**（进程继续跑）。

不做：不判达标、不关框、不替游戏做选择、不杀进程、不轮询到结束（那是 machine-runner 的只读职责）。

## 用法

    python tools/start-detached-longrun.py --journal logs/run6.jsonl --expect-version 0.7.25
    python tools/start-detached-longrun.py --health-seconds 0 --dry-run     # 只体检环境，不起跑
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# 控制台/管道编码兜底：Windows 上（尤其 cp1252 的 Store Python）打印中文会 UnicodeEncodeError，
# 起跑器本身必须能在任何 shell 下把四要素打出来。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - 老 Python/被重定向的流
        pass

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PYTHON = r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
# 让子进程脱离父进程的控制台/进程组，父进程（agent 回合）结束不会连带收掉它
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

_TRACKED_FILES = (
    "brain/agentfarm/longrun.py",
    "brain/agentfarm/farmwork.py",
    "brain/agentfarm/bridge.py",
    # run6 起「版本四要素」必须含 Mod 产物：dll 是真正跑在游戏里的那份，manifest 是版本号来源。
    "mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll",
    "mod/AgentFarm.Bridge/manifest.json",
)


def _alive(pid: int) -> bool:
    """Windows 下判断 PID 是否还活着（不依赖 psutil）。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()
    except OSError:
        return ""


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True, timeout=20)
        return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def version_four_elements(pid: int | None, started_at: str) -> dict:
    """版本四要素：HEAD / 被测文件 SHA256+mtime / PID+起跑时刻 / 工作树是否干净。"""
    files = {}
    for rel in _TRACKED_FILES:
        p = _ROOT / rel
        files[rel] = {
            "sha256": _sha256(p) if p.exists() else "",
            "mtime": _dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat() if p.exists() else "",
        }
    dirty = [line for line in _git("status", "--short").splitlines() if line.strip()]
    return {
        "head": _git("rev-parse", "HEAD"),
        "files": files,
        "pid": pid,
        "started_at": started_at,
        "git_status_short": dirty,
        "worktree_clean": not dirty,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="脱离式起跑长跑（活过 agent 回合边界）")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--max-minutes", type=int, default=150)
    ap.add_argument("--max-days", type=int, default=9)
    ap.add_argument("--journal", default="logs/run6.jsonl")
    ap.add_argument("--pid-file", default="")
    ap.add_argument("--python", default=_DEFAULT_PYTHON)
    ap.add_argument("--health-seconds", type=int, default=90)
    ap.add_argument("--expect-version", default="")
    ap.add_argument("--dry-run", action="store_true", help="只做前置体检与要素记录，不起跑")
    args = ap.parse_args(argv)

    journal = Path(args.journal)
    if not journal.is_absolute():
        journal = _ROOT / journal
    pid_file = Path(args.pid_file) if args.pid_file else journal.with_suffix(".pid")
    if not pid_file.is_absolute():
        pid_file = _ROOT / pid_file
    console = journal.with_suffix(".console.log")
    errlog = journal.with_suffix(".console.err.log")
    sidecar = journal.with_suffix(".version.json")

    if not Path(args.python).exists():
        print(f"[x] 找不到 python：{args.python}")
        return 2
    runner = _ROOT / "tools" / "run-longrun.py"
    if not runner.exists():
        print("[x] 缺 tools/run-longrun.py")
        return 2

    journal.parent.mkdir(parents=True, exist_ok=True)

    # ① 拒绝重复起跑
    if pid_file.exists():
        old = pid_file.read_text(encoding="utf-8", errors="replace").strip()
        if old.isdigit() and _alive(int(old)):
            print(f"[x] 已有长跑在跑：PID={old} ⇒ 不要重复起跑（先确认它是否卡住，再决定）")
            return 3
        print(f"[i] 旧 PID 文件（{old or '空'}）里的进程已不在，按残留处理")

    # ② 可选前置体检
    if args.expect_version:
        cmd = [args.python, "-u", "tools/preflight.py", "--expect", args.expect_version,
               "--save-baseline", "logs/" + journal.stem + "-baseline.json"]
        print(f"[i] 前置体检：{' '.join(cmd)}")
        rc = subprocess.run(cmd, cwd=_ROOT).returncode
        if rc != 0:
            print(f"[x] preflight 红（exit {rc}）⇒ 不起跑；先解决它再来")
            return 4

    started_at = _dt.datetime.now().isoformat(timespec="seconds")
    elements = version_four_elements(None, started_at)
    print("[i] 版本四要素（起跑前）：")
    print(f"    HEAD      = {elements['head']}")
    for rel, meta in elements["files"].items():
        print(f"    {rel} = {meta['sha256'][:16]}… mtime {meta['mtime']}")
    print(f"    工作树干净 = {elements['worktree_clean']}"
          + (f"（{len(elements['git_status_short'])} 项未提交）" if not elements["worktree_clean"] else ""))
    if args.dry_run:
        print("[i] --dry-run：不起跑")
        return 0

    # ③ 脱离式起跑
    argv_child = [args.python, "-u", "tools/run-longrun.py",
                  "--days", str(args.days), "--size", str(args.size),
                  "--max-minutes", str(args.max_minutes), "--max-days", str(args.max_days),
                  "--journal", str(journal.relative_to(_ROOT)).replace("\\", "/")]
    # run9(run A)/run10(run B) 的"演进对照"要能证明两次**只差 journal 路径**：
    # 把子进程命令行原文写进 sidecar（判决不看它，只用于取证）。注意本起跑器**不传**
    # `--boundary-llm`/`--no-boundary-llm` ⇒ 走 `tools/run-longrun.py` 的默认（LLM 开）；
    # 想关掉必须显式改这里或直接调用 run-longrun.py（run9/run10 绝不许关）。
    elements["argv"] = list(argv_child)
    elements["boundary_llm"] = True  # run-longrun.py:50 的默认；本脚本不覆盖它
    # 子进程环境显式写死：PYTHONUTF8=1（账本/console 里全是中文）+ PYTHONPATH=<root>/brain，
    # 这样"起跑器被在哪个 shell、带不带 PYTHONPATH"调用都不影响长跑的 import 与编码。
    child_env = dict(os.environ)
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    _brain = str(_ROOT / "brain")
    _pp = child_env.get("PYTHONPATH", "")
    child_env["PYTHONPATH"] = _brain if not _pp else (_brain + os.pathsep + _pp)
    out_fh = open(console, "w", encoding="utf-8")
    err_fh = open(errlog, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            argv_child, cwd=_ROOT, env=child_env, stdout=out_fh, stderr=err_fh,
            stdin=subprocess.DEVNULL,
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP, close_fds=True,
        )
    finally:
        out_fh.close()
        err_fh.close()

    pid_file.write_text(str(proc.pid), encoding="ascii")
    elements["pid"] = proc.pid
    sidecar.write_text(json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ 已脱离式起跑")
    print(f"    PID       = {proc.pid}")
    print(f"    起跑时刻  = {started_at}")
    print(f"    命令      = {' '.join(argv_child)}")
    print(f"    账本      = {journal.relative_to(_ROOT)}")
    print(f"    console   = {console.relative_to(_ROOT)} / stderr {errlog.relative_to(_ROOT)}")
    print(f"    四要素    = {sidecar.relative_to(_ROOT)}")

    # ④ 体检（只看，不判定）
    if args.health_seconds > 0:
        print(f"\n⏳ 体检 {args.health_seconds} 秒（进程继续跑，与本回合无关）...")
        time.sleep(args.health_seconds)

    alive = _alive(proc.pid)
    lines = len([ln for ln in journal.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]) \
        if journal.exists() else 0
    err_bytes = errlog.stat().st_size if errlog.exists() else 0
    print("\n—— 体检结果 ——")
    print(f"存活       : {alive}")
    print(f"账本行数   : {lines}")
    print(f"stderr 字节: {err_bytes}")
    if console.exists():
        tail = console.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
        print("console 尾部：")
        for ln in tail:
            print(f"  {ln}")
    if err_bytes:
        print("stderr 尾部：")
        for ln in errlog.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]:
            print(f"  {ln}")

    if not alive:
        print(f"\n[!] 进程已退出（起跑后 {args.health_seconds} 秒内）—— 把 console/stderr 原文报 Lead，"
              f"不要自行重跑")
        return 5
    print("\n后续只做只读轮询：PID 存活 / console 尾部 / 账本行数与尾条；"
          "出现 finish 或 PID 消失立刻报 Lead；跑完先别退游戏。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
