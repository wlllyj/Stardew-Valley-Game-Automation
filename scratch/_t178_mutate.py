# -*- coding: utf-8 -*-
r"""task-178 变异复现装置（只写 scratch/）。

作者的 `scratch/_t176_mutate.py` 已被删除（测试类 docstring 里有名无实），
所以我自建等价变异，验证 task-176 的护栏不是空转：
  m178a  HarvestMethodOf 退回"按字段名读"        （期望：源码契约 + 镰刀行为红）
  m178b  反射不可用时 `Ready` 直接返回 (null,null)（期望：fields 相关红 ⇒ fail-closed 过头会被抓）
  m178c  去掉 `JsonIgnoreCondition.Never`         （期望：无条件出键的契约红）
  m178d  `acted` 退回 checkAction 返回值           （期望：acted 契约红）

必须把 **brain + tests + mod** 一起拷进临时树：前 5 条用例是读 `mod/AgentFarm.Bridge/*.cs`
的源码契约用例，只拷 brain+tests 会假绿。
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = os.path.join(HERE, "_t178_mut")
TARGET = "tests.test_longrun.TestTask176HarvestMethodSourceAndActed"
MOD = os.path.join("mod", "AgentFarm.Bridge")

MUTS = [
    ("m178a", os.path.join(MOD, "CropMeta.cs"),
     "switch (crop.GetHarvestMethod())",
     'return ReadMember(crop, "HarvestMethod")?.ToString();\n                switch (crop.GetHarvestMethod())'),
    ("m178b", os.path.join(MOD, "CropMeta.cs"),
     'if (direct != null) return (direct, "game");',
     'if (direct != null) return (direct, "game");\n            return (null, null);  // m178b'),
    ("m178c", os.path.join(MOD, "Contracts.cs"),
     "[JsonIgnore(Condition = JsonIgnoreCondition.Never)]",
     "[JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]"),
    ("m178d", os.path.join(MOD, "Skills.cs"),
     "bool acted = err == null && observedChange;",
     "bool acted = err == null && handled;  // m178d"),
]

out = []


def run_case(name, rel=None, old=None, new=None):
    dst = os.path.join(TMP, name)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    # 只拷 brain/tests/mod：**不要拷 scratch**（里面已有本装置的临时树 ⇒ 会递归自我复制）。
    ignore = shutil.ignore_patterns("__pycache__", "_t178_mut", "_t171_mut", "_t166_pre")
    for sub in ("brain", "tests"):
        src = os.path.join(ROOT, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, sub), ignore=ignore)
    shutil.copytree(os.path.join(ROOT, "mod"), os.path.join(dst, "mod"), ignore=ignore)
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
    proc = subprocess.run([sys.executable, "-m", "unittest", TARGET, "-v"],
                          cwd=dst, env=env, capture_output=True, text=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    fails = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)
    dist = []
    for f in fails:
        if f not in dist:
            dist.append(f)
    tail = [ln for ln in text.splitlines() if ln.startswith(("Ran ", "OK", "FAILED"))]
    with open(os.path.join(HERE, "_t178_mut_%s.txt" % name), "w", encoding="utf-8") as fh:
        fh.write(text)
    out.append("%-6s 命中=%-3s rc=%s 红=%d（去重 %d）%s" % (name, hits, proc.returncode, len(fails),
                                                          len(dist), tail))
    for f in dist:
        out.append("        - " + f)
    return len(fails)


run_case("control")
for name, rel, old, new in MUTS:
    run_case(name, rel, old, new)

print("\n".join(out))
with open(os.path.join(HERE, "_t178_mut_out.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
