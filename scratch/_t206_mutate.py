"""task-206 变异矩阵：自己建变异、实测杀几条（作者 m205a-d 无定义/无脚本 ⇒ 只能自建对照）。

用法：
  python scratch/_t206_mutate.py --list
  python scratch/_t206_mutate.py --all        # 跑全部（brain 变异跑探针、Mod 变异跑 C# 自检）
  python scratch/_t206_mutate.py --only m206c
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "scratch", "_t206_post")
MUT_ROOT = os.path.join(ROOT, "scratch", "_t206_mut")
PY = sys.executable

IGNORE = shutil.ignore_patterns(".git", "__pycache__", "_t206_mut", "_t206_probe_out*")

# (name, kind, relpath, old, new, 说明)
CASES = [
    ("m206a", "probe", "brain/agentfarm/longrun.py",
     "        if task in self._tool_suspended_stages(obs):\n            return []\n",
     "        if False:\n            return []\n",
     "升级暂停失效：暂停阶段照旧派活（应红 G2/暂停类）"),
    ("m206b", "probe", "brain/agentfarm/longrun.py",
     "        tmap = FarmWorker.tiles_of(obs)\n        for tv in tmap.values():\n"
     "            if not tv.get(\"crop\") or tv.get(\"dead\"):\n                continue\n"
     "            if not tv.get(\"watered\"):\n                return False\n"
     "            if tile_ready(tv):\n                return False\n",
     "        tmap = FarmWorker.tiles_of(obs)\n",
     "due 去掉「紧急农活优先」挡板（应红 F4a）"),
    ("m206c", "probe", "brain/agentfarm/farmwork.py",
     "        if appeared or tier_up or money_down:\n",
     "        if True:\n",
     "升级判据恒 ok（回执洗白）（应红 B1a）"),
    ("m206d", "probe", "brain/agentfarm/farmwork.py",
     "        if being_after is None or (tier_after >= 0 and tier_before >= 0 and tier_after > tier_before):\n",
     "        if True:\n",
     "取回判据恒 ok（应红 B2a）"),
    ("m206e", "probe", "brain/agentfarm/farmwork.py",
     "        if free_status == \"ok\" and free <= 0:\n",
     "        if False:\n",
     "取回不再 fail-closed 背包满（应红 F6a）"),
    ("m206f", "probe", "brain/agentfarm/longrun.py",
     "        if plan.get(\"action\") not in (\"upgrade\", \"pickup\"):\n            return False\n",
     "        if plan.get(\"action\") is None:\n            return False\n",
     "due 把 wait/need_slot 也算「该去」（应红 D1/D2 或 F 留痕）"),
    ("m206g", "csharp", "mod/AgentFarm.Bridge/ToolUpgradeRules.cs",
     "        if (s.ShopReadOnly) return StatusReadOnly;\n",
     "        if (s.ShopReadOnly && false) return StatusReadOnly;\n",
     "read_only 自检失效（应被 C# 自检杀）"),
    ("m206h", "csharp", "mod/AgentFarm.Bridge/ToolUpgradeRules.cs",
     "Tier == tierBefore + 1",
     "Tier >= tierBefore",
     "选择条目放宽到任意等级（应被 C# 自检杀）"),
    ("m206i", "csharp", "mod/AgentFarm.Bridge/ToolUpgradeRules.cs",
     "        if (upgradeAppeared) return EvidenceToolBeingUpgraded;\n"
     "        if (tradeReduced) return EvidenceTradeItem;\n",
     "        if (tradeReduced) return EvidenceTradeItem;\n"
     "        if (upgradeAppeared) return EvidenceToolBeingUpgraded;\n",
     "证据优先级颠倒（应被 C# 自检杀）"),
    ("m206j", "csharp", "mod/AgentFarm.Bridge/ToolUpgradeRules.cs",
     "        if (k == \"wateringcan\") return \"can\";\n",
     "        if (k == \"wateringcan\") return \"wateringcan\";\n",
     "kind 归一化失效（应被 C# 自检杀）"),
]

BASELINE_FAIL_TAGS = {"F1c2", "F1e", "F3a", "F3c"}


def apply_edit(tree: str, rel: str, old: str, new: str) -> None:
    path = os.path.join(tree, rel)
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"锚点命中 {n} 次（要求恰好 1）：{rel} :: {old[:60]!r}")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(src.replace(old, new, 1))


def run_probe(tree: str) -> tuple[int, list[str]]:
    env = dict(os.environ)
    env["T206_ROOT"] = tree
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run([PY, "-W", "error::SyntaxWarning", os.path.join(ROOT, "scratch", "_t206_probe.py")],
                          cwd=ROOT, env=env, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = re.findall(r"^\s*FAIL (\S+)", out, re.M)
    return proc.returncode, fails


def run_csharp(tree: str) -> tuple[int, list[str]]:
    proj = os.path.join(tree, "mod", "AgentFarm.Bridge.Tests", "AgentFarm.Bridge.Tests.csproj")
    proc = subprocess.run(["dotnet", "run", "--project", proj, "-c", "Release", "--nologo"],
                          cwd=tree, capture_output=True, text=True, timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = re.findall(r"^\s*FAIL\s+(\S+)", out, re.M)
    return proc.returncode, fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    if args.list:
        for c in CASES:
            print(f"{c[0]:8s} {c[1]:7s} {c[2]:45s} {c[5]}")
        return 0
    cases = [c for c in CASES if args.all or c[0] == args.only]
    if not cases:
        print("选 --all 或 --only <name>")
        return 2
    os.makedirs(MUT_ROOT, exist_ok=True)
    # 基线：control 树
    ctrl_code, ctrl_fails = run_probe(BASE)
    ctrl_cs_code, _ = run_csharp(BASE)
    print(f"control: probe rc={ctrl_code} FAIL={ctrl_fails} | csharp rc={ctrl_cs_code}")
    results = []
    for name, kind, rel, old, new, desc in cases:
        tree = os.path.join(MUT_ROOT, name)
        if os.path.isdir(tree):
            shutil.rmtree(tree, ignore_errors=True)
        shutil.copytree(BASE, tree, ignore=IGNORE)
        try:
            apply_edit(tree, rel, old, new)
        except SystemExit as exc:
            print(f"{name}: 锚点失败 {exc}")
            results.append((name, kind, "ANCHOR-FAIL", 0))
            shutil.rmtree(tree, ignore_errors=True)
            continue
        if kind == "probe":
            rc, fails = run_probe(tree)
            killed = sorted(set(fails) - BASELINE_FAIL_TAGS)
            print(f"{name}: probe rc={rc} FAIL={fails} 新增红={killed}")
            results.append((name, kind, killed, len(killed)))
        else:
            rc, fails = run_csharp(tree)
            print(f"{name}: csharp rc={rc} 杀={len(fails)} {fails[:8]}")
            results.append((name, kind, fails, len(fails)))
        shutil.rmtree(tree, ignore_errors=True)
    print("\n=== 汇总（自报 vs 实测）===")
    for name, kind, info, n in results:
        print(f"{name:8s} {kind:7s} 杀={n} {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
