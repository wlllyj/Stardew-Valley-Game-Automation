# -*- coding: utf-8 -*-
"""【task-240b】腾格后同轮买种子的变异实测装置（在 `git archive HEAD` 冻结树上复跑）。

用法（必须 DSH python + PYTHONUTF8=1；跑之前先把 task-240b 的修复+测试落库，
否则冻结树上没有被测对象）：
  $env:PYTHONUTF8="1"; & <DSH python> "scratch\\_t240b_mutate.py"

变异对象 = `brain/agentfarm/longrun.py` 里 task-240b 的那 5 行（腾格成功 ⇒ 重取快照 +
`_observe_free_slots` + `_preconditions` + `continue`）。每条变异把被钉住的行为改坏一项，
`tests.test_longrun.TestTask240bReliefThenBuy` 必须至少一条用例变红。
锚点命中数 != 期望值 ⇒ ADAPTER-ERROR（**不当 PASS**）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")

#: task-240b 修复体（当前工作树/冻结树里必须**恰好命中 1 次**）
BLOCK = """                obs = self._snap_or(obs)
                last_obs = obs
                self._observe_free_slots(rep, obs)
                obs = self._preconditions(obs, rep)
                continue"""

# (名字, 原文, 变异后, 期望命中数, [定向用例模块...])
MUTANTS = [
    (
        "M1_revert_fix",
        BLOCK,
        "                continue",
        "整段删回旧接线（腾格成功直接 continue）⇒ 同一轮不买种子",
        1,
        ["tests.test_longrun.TestTask240bReliefThenBuy"],
    ),
    (
        "M2_stale_obs",
        BLOCK,
        """                last_obs = obs
                self._observe_free_slots(rep, obs)
                obs = self._preconditions(obs, rep)
                continue""",
        "不重取快照（拿腾格前的 stale obs 进 _preconditions）⇒ free=0 buy_full 白撞",
        1,
        ["tests.test_longrun.TestTask240bReliefThenBuy"],
    ),
    (
        "M3_drop_observe",
        BLOCK,
        """                obs = self._snap_or(obs)
                last_obs = obs
                obs = self._preconditions(obs, rep)
                continue""",
        "丢掉同轮 `_observe_free_slots` ⇒ 空格 trace 迟一轮才刷新",
        1,
        ["tests.test_longrun.TestTask240bReliefThenBuy"],
    ),
    (
        "M4_no_continue",
        BLOCK,
        """                obs = self._snap_or(obs)
                last_obs = obs
                self._observe_free_slots(rep, obs)
                obs = self._preconditions(obs, rep)
""",
        "丢掉 continue（跌落主循环那句 _preconditions）⇒ 同一轮连调两次",
        1,
        ["tests.test_longrun.TestTask240bReliefThenBuy"],
    ),
]

TARGET = "brain/agentfarm/longrun.py"
COUNT_RE = re.compile(r"Ran (\d+) tests?")
BAD_RE = re.compile(r"^(?:FAIL|ERROR): ", re.M)


def run_tests(tree: Path, mods: list[str]):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    p = subprocess.run([PY, "-m", "unittest", *mods],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    m = COUNT_RE.search(out)
    ran = int(m.group(1)) if m else -1
    failed = len(BAD_RE.findall(out))
    ok = bool(re.search(r"^OK\b", out, re.M))
    return ran, failed, ok, out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="t240b_"))
    tree = tmp / "tree"
    tree.mkdir()
    tar = tmp / "frozen.tar"
    subprocess.run(["git", "archive", "--format=tar", "HEAD", "-o", str(tar)],
                   cwd=str(REPO), check=True)
    with tarfile.open(tar) as tf:
        tf.extractall(tree)
    print(f"[tree] {tree}（git archive HEAD）")

    f = tree / TARGET
    src = f.read_text(encoding="utf-8")
    if src.count(BLOCK) != 1:
        print(f"!! 冻结树上 task-240b 修复体命中 {src.count(BLOCK)} 次（期望 1）"
              "——先落库再跑本装置")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    mods = sorted({m for *_, ms in MUTANTS for m in ms})
    ran, failed, ok, out = run_tests(tree, mods)
    print(f"[baseline] Ran {ran} / failed={failed} / OK={ok}")
    if not ok:
        print(out[-4000:])
        print("!! 冻结树基线不是绿的 —— 装置不可信，中止")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    results = []
    for name, old, new, why, want, ms in MUTANTS:
        n = src.count(old)
        if n != want:
            results.append((name, "ADAPTER-ERROR", f"锚点命中 {n} 次（期望 {want}）", 0, 0))
            print(f"[{name}] ADAPTER-ERROR 锚点命中 {n} 次（期望 {want}）")
            continue
        f.write_text(src.replace(old, new), encoding="utf-8", newline="")
        try:
            ran, failed, ok, out = run_tests(tree, ms)
        finally:
            f.write_text(src, encoding="utf-8", newline="")
        verdict = "KILL" if (failed > 0 or not ok) else "ALIVE(测试没盯住!)"
        results.append((name, verdict, f"Ran {ran} failed={failed}", failed, ran))
        print(f"[{name}] {verdict}  Ran={ran} failed={failed}  （{why}）")
        if verdict.startswith("ALIVE"):
            print(out[-2500:])

    print("\n================ 变异实测汇总（task-240b） ================")
    for name, verdict, detail, failed, ran in results:
        print(f"{verdict:14s} {name:20s} {detail}")
    killed = sum(1 for _, v, _, _, _ in results if v == "KILL")
    print(f"杀数 = {killed} / {len(results)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
