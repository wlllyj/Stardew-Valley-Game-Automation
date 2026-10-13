#!/usr/bin/env python
"""发布前的一体化闸门（Lead 专用，只读检查，不改任何东西）。

为什么需要它：本项目有四个"版本/状态"必须同时对上，少一个就会在真机上浪费一轮：
  1) mod/AgentFarm.Bridge/manifest.json 的 Version
  2) brain/agentfarm/bridge.py 的 MOD_VERSION_EXPECTED
  3) 编译产物 mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll 是否比源码新
  4) 全量单测是否 OK、工作树是否干净（要提交的东西不能被漏掉）

用法：
    python tools\\check-release.py                 # 只看版本号是否互相一致
    python tools\\check-release.py --expect 0.7.22  # 断言版本必须等于 0.7.22
    python tools\\check-release.py --skip-tests      # 跳过单测（快速看版本）
退出码：0 = 四项全绿；1 = 有红项；2 = 环境/参数问题。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "mod" / "AgentFarm.Bridge" / "manifest.json"
BRIDGE_PY = REPO / "brain" / "agentfarm" / "bridge.py"
DLL = REPO / "mod" / "AgentFarm.Bridge" / "bin" / "Release" / "AgentFarm.Bridge.dll"
MOD_DIR = REPO / "mod" / "AgentFarm.Bridge"
BRAIN_DIR = REPO / "brain" / "agentfarm"
TESTS_DIR = REPO / "tests"


def say(ok: bool | None, label: str, detail: str = "") -> None:
    mark = "✅" if ok is True else ("❌" if ok is False else "⚠️")
    line = f"{mark} {label}"
    if detail:
        line += f" —— {detail}"
    print(line, flush=True)


def check_versions(expect: str | None) -> tuple[bool, str, str]:
    """返回 (是否全绿, manifest 版本, bridge.py 版本)。"""
    if not MANIFEST.is_file():
        say(False, "manifest.json 存在", str(MANIFEST))
        return False, "", ""
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        say(False, "manifest.json 可解析", f"{type(exc).__name__}: {exc}")
        return False, "", ""
    mver = str(manifest.get("Version", "")).strip()

    if not BRIDGE_PY.is_file():
        say(False, "bridge.py 存在", str(BRIDGE_PY))
        return False, mver, ""
    text = BRIDGE_PY.read_text(encoding="utf-8")
    hit = re.search(r'MOD_VERSION_EXPECTED\s*=\s*"([^"]+)"', text)
    bver = hit.group(1) if hit else ""

    ok = bool(mver) and bool(bver) and mver == bver
    say(ok, "manifest Version == brain MOD_VERSION_EXPECTED", f"manifest={mver or '?'} / brain={bver or '?'}")
    if expect is not None:
        ok2 = mver == expect and bver == expect
        say(ok2, f"版本 == 期望值 {expect}", f"manifest={mver or '?'} / brain={bver or '?'}")
        ok = ok and ok2
    return ok, mver, bver


def check_dll() -> bool:
    if not DLL.is_file():
        say(False, "编译产物存在", str(DLL))
        return False
    dll_t = DLL.stat().st_mtime
    sources = [p for p in MOD_DIR.rglob("*.cs") if "bin" not in p.parts and "obj" not in p.parts]
    newest = max(sources, key=lambda p: p.stat().st_mtime) if sources else None
    if newest is None:
        say(None, "Mod 源码扫描", "没找到 .cs（异常）")
        return False
    fresh = dll_t >= newest.stat().st_mtime
    say(
        fresh,
        "dll 不比源码旧",
        f"dll={time.strftime('%H:%M:%S', time.localtime(dll_t))} / 最新源码={newest.name} "
        f"{time.strftime('%H:%M:%S', time.localtime(newest.stat().st_mtime))}",
    )
    return fresh


def run_py_compile() -> bool:
    files = sorted(list(BRAIN_DIR.glob("*.py")) + list(TESTS_DIR.glob("*.py")))
    if not files:
        say(False, "py_compile 目标文件", "没找到 .py")
        return False
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", *[str(p) for p in files]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    ok = proc.returncode == 0
    say(ok, f"py_compile（{len(files)} 个文件）", (proc.stderr or "").strip()[:300])
    return ok


def run_tests() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    ran = re.search(r"Ran (\d+) tests?", blob)
    n = ran.group(1) if ran else "?"
    ok = proc.returncode == 0 and "OK" in blob and "FAILED" not in blob
    tail = ""
    for line in reversed(blob.strip().splitlines()):
        if line.strip():
            tail = line.strip()
            break
    say(ok, f"全量单测（Ran {n} tests）", tail[:300])
    return ok


def check_git() -> tuple[bool, int]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        say(None, "git status", "git 不可用")
        return False, -1
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    clean = not lines
    detail = "工作树干净" if clean else f"{len(lines)} 项未提交：" + "; ".join(lines[:6]) + (" …" if len(lines) > 6 else "")
    say(clean, "工作树干净（要提交的不能被漏掉）", detail[:400])
    return clean, len(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="发布前闸门：版本一致性 + 编译 + 单测 + 工作树")
    ap.add_argument("--expect", default=None, help="断言版本必须等于这个值（例如 0.7.22）")
    ap.add_argument("--skip-tests", action="store_true", help="跳过全量单测")
    args = ap.parse_args()

    # 自配 stdout 编码：冻结链在 cp1252 控制台（未设 PYTHONUTF8）会因中文/emoji 抛
    # UnicodeEncodeError（2026-10-14 `_bump-mod-version.py` 实测同类崩法）。
    # 与 tools\preflight.py / run-longrun.py 同口径：别指望调用方记得设环境变量。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not REPO.is_dir():
        print(f"仓库根不存在：{REPO}")
        return 2

    print(f"仓库：{REPO}")
    results = []
    ok_v, _, _ = check_versions(args.expect)
    results.append(ok_v)
    results.append(check_dll())
    results.append(run_py_compile())
    if not args.skip_tests:
        results.append(run_tests())
    else:
        print("⚠️ 已跳过全量单测（--skip-tests）")
    git_clean, _ = check_git()
    results.append(git_clean)

    hard_fail = any(r is False for r in results)
    print()
    print("结论：" + ("❌ 有红项，不要装机/不要起跑" if hard_fail else "✅ 四项全绿，可以进入部署步骤"))
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
