# -*- coding: utf-8 -*-
r"""task-171 变异复现装置（只写 scratch/）。

作者的测试 docstring 引用了 `scratch/_t170_mutate.py`，但该文件不存在，
所以由我自己注入 3 个变异并复现"应当变红"的用例集合：

  m170a  tile_ready 判据换回裸 ripe        （期望红 5）
  m170b  去掉 _note_harvest_gave_up 调用    （期望红 3）
  m170c  sleep_guard 不扣 harvest_gave_up   （期望红 1）

做法：把 brain/ + tests/ 拷到独立临时树，注入变异，在临时树里跑
`tests.test_longrun.TestTask170HarvestReady`，解析失败用例名。
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.path.join(HERE, "_t171_mut")
TARGET = "tests.test_longrun.TestTask170HarvestReady"

MUTS = [
    ("m170a", "brain/agentfarm/farmwork.py",
     'return tv.get("ready") is True', 'return bool(tv.get("ripe"))'),
    ("m170b", "brain/agentfarm/longrun.py",
     "self._note_harvest_gave_up(res.steps, rep)", "pass  # m170b mutated"),
    ("m170c", "brain/agentfarm/longrun.py",
     "ripe_f = max(0, ripe_f - len(self.harvest_gave_up))", "ripe_f = ripe_f  # m170c mutated"),
]

out_lines = []


def run_case(name, rel=None, old=None, new=None):
    dst = os.path.join(TMP, name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    shutil.copytree(os.path.join(ROOT, "brain"), os.path.join(dst, "brain"))
    shutil.copytree(os.path.join(ROOT, "tests"), os.path.join(dst, "tests"))
    hits = "-"
    if rel:
        path = os.path.join(dst, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        hits = text.count(old)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text.replace(old, new))
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = os.path.join(dst, "brain")
    proc = subprocess.run(
        [sys.executable, "-W", "error::SyntaxWarning", "-m", "unittest", TARGET, "-v"],
        cwd=dst, env=env, capture_output=True, text=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    fails = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)
    tail = [ln for ln in text.splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))]
    with open(os.path.join(HERE, "_t171_mut_%s.txt" % name), "w", encoding="utf-8") as fh:
        fh.write(text)
    head = "%-6s 命中=%-3s rc=%s  红=%d %s" % (name, hits, proc.returncode, len(fails), tail)
    out_lines.append(head)
    for f in fails:
        out_lines.append("        - " + f)
    return len(fails)


run_case("control")
for name, rel, old, new in MUTS:
    run_case(name, rel, old, new)

print("\n".join(out_lines))
with open(os.path.join(HERE, "_t171_mut_out.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out_lines) + "\n")
