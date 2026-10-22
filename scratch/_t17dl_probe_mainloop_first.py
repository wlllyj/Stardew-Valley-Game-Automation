# -*- coding: utf-8 -*-
r"""【T16 deputy-lead / D2 语义复核】主循环先买、派发后到的顺序 —— 对抗探针。

作者新增的 test_buy_dispatch_and_main_loop_do_not_double_order 只覆盖
「先 _drive 派发（买中）→ 再 _preconditions 主循环」这一个顺序。
本探针覆盖**反序**：主循环 `_preconditions` 先买中一次，然后同一天派发 buy 意图，
检查
  (a) 是否双买（buy_calls 是否 >1）；
  (b) 派发这一条 buy 意图被记成 executed_steps 几（是否 0 = 记账漏掉这次真买）。

用法：$env:PYTHONUTF8='1'; & <DSH python> scratch\_t17dl_probe_mainloop_first.py [ref]
不带 ref 时对**冻结树**（git archive ref，默认 daceb48）跑；带 `--worktree` 用主工作树。
"""
from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "daceb48"
    if arg == "--worktree":
        tree = REPO
    else:
        tmp = Path(tempfile.mkdtemp(prefix="t17dl_"))
        tar = tmp / "a.tar"
        subprocess.run(["git", "archive", "--format=tar", arg, "-o", str(tar)],
                       cwd=REPO, check=True)
        tree = tmp / "tree"
        tree.mkdir()
        with tarfile.open(tar) as tf:
            tf.extractall(tree)
    print(f"[tree] ref={arg} -> {tree}")

    script = r'''
import sys
sys.path.insert(0, r"{tests}")
sys.path.insert(0, r"{brain}")
from types import SimpleNamespace
import test_longrun as T
import agentfarm.longrun as longrun_mod
from agentfarm.longrun import DayReport, TaskIntent

# ---- 顺序 A：主循环先买（_preconditions），再派发 buy 意图 ----
w = T.FakeWorld(weeds=0, seeds=0, money=5000)
run = T.make_run(w, target_days=1, max_days=1)
run.client, run.worker, run.started = T.FakeClient(w), T._NoLootWorker(w), 0.0
run.allow_buy = True
rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
intent = TaskIntent("buy", "inventory", "\u4e70\u79cd\u5b50", "seeds<2")

run._preconditions(run._snap(), rep)                 # \u4e3b\u5faa\u73af\u5148\u4e70
n_after_main = len(w.buy_calls)
run._plan_intents(SimpleNamespace(intents=[intent], source="llm", boundary="daily"))
acted = run._execute(SimpleNamespace(intents=[intent]), run._snap(), None, rep)
n_total = len(w.buy_calls)
rec = [r for r in run.intent_coverage if r["task"] == "buy"]
print("A main-loop-first: buy_calls after main=%d, after dispatch=%d, acted=%s"
      % (n_after_main, n_total, acted))
print("A buy intent record:", rec)
print("A buy_attempts_today =", run.buy_attempts_today,
      "MAX =", longrun_mod.MAX_BUY_TRIES_PER_DAY)

# ---- 顺序 B：派发先买，再主循环（作者已覆盖，做对照）----
w2 = T.FakeWorld(weeds=0, seeds=0, money=5000)
run2 = T.make_run(w2, target_days=1, max_days=1)
run2.client, run2.worker, run2.started = T.FakeClient(w2), T._NoLootWorker(w2), 0.0
run2.allow_buy = True
rep2 = DayReport(day_key=("spring", 1, 9), started_at=0.0)
run2._plan_intents(SimpleNamespace(intents=[intent], source="llm", boundary="daily"))
acted2 = run2._execute(SimpleNamespace(intents=[intent]), run2._snap(), None, rep2)
run2._preconditions(run2._snap(), rep2)
print("B dispatch-first: buy_calls total=%d acted=%s" % (len(w2.buy_calls), acted2))
'''.format(tests=str(tree / "tests"), brain=str(tree / "brain"))

    env = dict(__import__("os").environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain") + ";" + str(tree / "tests")
    p = subprocess.run([PY, "-c", script], cwd=str(tree / "tests"), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(p.stdout)
    if p.stderr.strip():
        print("---- stderr ----")
        print(p.stderr[-2000:])
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
