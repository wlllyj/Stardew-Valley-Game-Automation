r"""task-190 自建变异矩阵 + C6c「作者自报变异映射」实测复核。

只写 `scratch/`：每个 case 把 `brain/` + `tests/` + `mod/` 拷到 `scratch/_t190_mut/<case>`，
做**纯文本**变异，然后跑对应测量：

* brain 变异 ⇒ 跑 `scratch/_t190_probe.py`（`T190_ROOT=<tree>`），数红了哪几条；
* Mod 变异 ⇒ ①跑 C# 自检工程（数 `FAIL  ` 行）②跑 `tests.test_longrun.TestTask188UseToolActed`（数 failures）。

作者在 `e612464` 里自报：m188a ⇒ C# 杀 7；m188b ⇒ 杀 8；m188c/m188d/m188e ⇒ 契约各杀 1。
本脚本独立实测这三组数字（C6c），不符就当面列出来。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
PY = sys.executable
SRC = WS
MUT = WS / "scratch" / "_t190_mut"
PROBE = WS / "scratch" / "_t190_probe.py"
BRAIN = "brain/agentfarm/farmwork.py"
RULES = "mod/AgentFarm.Bridge/ClumpRules.cs"
SKILLS = "mod/AgentFarm.Bridge/Skills.cs"
USETOOL = "mod/AgentFarm.Bridge/UseToolSkill.cs"

PURE_BODY = ('            if (tileChanged == true) return "tile";\n'
             '            if (readyFlipped == true || readySourceChanged == true) return "ready";\n'
             '            if (readyDropped == true) return "readyCrops";\n'
             '            if (inventoryGrew == true) return "inventory";\n'
             '            return null;')

MUTANTS: dict[str, list[tuple[str, str, str]]] = {
    "control": [],
    # ── 我的四个通道变异（brain / scratch/_t190_probe.py 抓）──
    "m190a_f1_tile_seen_always": [
        (BRAIN, "tile_seen = tv is not None", "tile_seen = True")],
    "m190b_f3_whitelist_unbound": [
        (BRAIN, "if gained and tile_level_evidence:", "if gained:")],
    "m190c_f5_wording": [
        (BRAIN, 'ready_note = "farm.readyCrops 无法判定（字段缺失/该 Mod 版本不提供）"',
         'ready_note = "farm.readyCrops 没下降"')],
    "m190d_r2_no_wait": [
        (BRAIN, "while tile_level_evidence and not gained and loot_waits < LOOT_CONFIRM_TRIES:",
         "while False:")],
    "m190e_r2_wording": [
        (BRAIN, "                if tile_level_evidence:\n                    # 【task-189 / R2】",
         "                if False:\n                    # 【task-189 / R2】")],
    # ── 作者自报的五条（task-188，C6c 复核）──
    "m188a_pure_always_tile": [(RULES, PURE_BODY, '            return "tile";')],
    "m188b_pure_always_null": [(RULES, PURE_BODY, '            return null;')],
    "m188c_wrapper_acted_true": [
        (SKILLS, "resp.Acted = ClumpRules.Acted(evidence);", "resp.Acted = true;")],
    "m188d_wrapper_no_evidence": [
        (SKILLS, "resp.ActedEvidence = evidence;", "resp.ActedEvidence = null;")],
    "m188e_reason_empty_text": [
        (USETOOL, "该格原本是 {this.OriginalText()}", "该格原本是 （空）")],
    # 我自己的站点（`OriginalText()` 兜底值）：测作者"纯文本契约"能不能抓到 —— GAP 观察项
    "m188e2_originaltext_early_return": [
        (USETOOL, "if (!string.IsNullOrWhiteSpace(this._whatBefore)) return this._whatBefore;",
         'return "（空）";')],
}

CLAIMS = {"m188a_pure_always_tile": 7, "m188b_pure_always_null": 8,
          "m188c_wrapper_acted_true": 1, "m188d_wrapper_no_evidence": 1,
          "m188e_reason_empty_text": 1}
# GAP 观察项：只记录实测（不按"自报值"判达标）
GAP_ONLY = {"m188e2_originaltext_early_return"}


def build(case: str, patches: list[tuple[str, str, str]]) -> tuple[Path, list[str]]:
    dst = MUT / case
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    for top in ("brain", "tests", "mod", "docs"):
        shutil.copytree(SRC / top, dst / top, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "_t190_mut", "bin", "obj"))
    notes: list[str] = []
    for rel, old, new in patches:
        path = dst / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            notes.append(f"PATCH-MISS {rel}: {old[:50]!r}")
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return dst, notes


def run_probe(tree: Path) -> tuple[str, list[str]]:
    env = dict(os.environ, T190_ROOT=str(tree), PYTHONUTF8="1")
    proc = subprocess.run([PY, "-W", "error::SyntaxWarning", str(PROBE)],
                          cwd=str(WS), capture_output=True, text=True, timeout=3600, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"汇总：PASS=(\d+) FAIL=(\d+) SKIP=(\d+)", out)
    fails = [l.strip() for l in out.splitlines() if l.strip().startswith("FAIL ")]
    tail = f"rc={proc.returncode} " + (f"PASS={m.group(1)} FAIL={m.group(2)}" if m else "no-summary")
    return tail, fails


def run_cstests(tree: Path) -> tuple[str, int]:
    proj = tree / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"
    proc = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                          cwd=str(tree), capture_output=True, text=True, timeout=1800)
    out = (proc.stdout or "") + (proc.stderr or "")
    n_fail = len(re.findall(r"^FAIL\s", out, re.M))
    return f"rc={proc.returncode} C#杀{n_fail}", n_fail


def run_contract(tree: Path) -> tuple[str, list[str]]:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(tree))
    proc = subprocess.run([PY, "-m", "unittest", "tests.test_longrun.TestTask188UseToolActed", "-v"],
                          cwd=str(tree), capture_output=True, text=True, timeout=900, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = re.findall(r"^(test_\w+) \(.*\) \.\.\. FAIL", out, re.M)
    return f"rc={proc.returncode} 契约杀{len(fails)}", fails


def main() -> int:
    rows = []
    for case, patches in MUTANTS.items():
        tree, notes = build(case, patches)
        if case == "control":
            tail, fails = run_probe(tree)
            _, c_fail = run_cstests(tree)
            _, k_fail = run_contract(tree)
            ok = not fails and c_fail == 0 and not k_fail
            rows.append((case, f"probe[{tail}] C#杀{c_fail} 契约杀{len(k_fail)}", "✅" if ok else "❌"))
            print(f"{case:34s} {rows[-1][1]}  {rows[-1][2]}")
            continue
        if case.startswith("m190"):
            tail, fails = run_probe(tree)
            rows.append((case, f"{tail}；红={[f.split()[1] for f in fails]}", "✅" if fails else "❌"))
        else:                                    # 作者自报的 Mod 变异
            _, c_fail = run_cstests(tree)
            _, k_fails = run_contract(tree)
            got = c_fail if case in ("m188a_pure_always_tile", "m188b_pure_always_null") else len(k_fails)
            if case in GAP_ONLY:
                rows.append((case, f"C#杀{c_fail} 契约杀{len(k_fails)} ⇒ 实测杀 {got}"
                                    f"（GAP 观察项：文本契约不覆盖该站点）", "✅"))
            else:
                claim = CLAIMS[case]
                mark = "✅" if got >= 1 else "❌"
                verdict = "符合" if got == claim else f"**不符（自报 {claim}）**"
                rows.append((case, f"C#杀{c_fail} 契约杀{len(k_fails)} ⇒ 实测杀 {got} {verdict}", mark))
        print(f"{case:34s} {rows[-1][1]}  {rows[-1][2]}")
        if notes:
            print(f"    ⚠ {notes}")
    bad = [r for r in rows if r[2] != "✅"]
    print(f"\n== 变异矩阵：{len(rows)} case，未达标 {len(bad)} ==")
    for b in bad:
        print(f"   ❌ {b[0]}: {b[1]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
