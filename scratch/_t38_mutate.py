"""【T5.2 / 0.7.48 预置】deputy-lead 的对抗变异跑器（只写 scratch/，不改生产代码）。

用途：对 task-38（slot_relief task-237 字段奇偶补齐）做**四把伪造判据**的实际杀数测量。
两个口径（互相独立）：
  A. 探针口径（字段存在性）：AST 扫 brain/agentfarm/longrun.py 里所有
     `_journal("slot_relief", ...)` 调用，检查 TASK237 字段集是否齐全
     —— 等价于 scratch/smoke-0742.py:680 的 `f'"{k}"' not in json.dumps(r)` 校验（只查"在不在"）。
  B. 定向单测口径：在变异树上跑 dev-coder 新增的
     tests.test_longrun.TestTask38SlotReliefFieldParity，看是否判红。

"修前"＝当前工作树（dev-coder 的修复 + 测试均为未提交在制改动；HEAD 无此二者）。
0.7.48 冻结后把 COMMIT 换成冻结 commit、改用 `git archive` 冻结树重跑同一脚本即可。
禁 `git commit --amend`；本脚本不触碰仓库（只往 temp 复制）。

用法：
  set PYTHONUTF8=1
  python scratch/_t38_mutate.py            # 全部用例
  python scratch/_t38_mutate.py --ref HEAD # 从 HEAD 冻结树取基线（无修复，作为"红前"对照）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
TMP_BASE = Path(os.environ.get("TEMP", r"C:\Users\admin\AppData\Local\Temp")) / "_t38_mut"
LR = "brain/agentfarm/longrun.py"
TEST_ID = "tests.test_longrun.TestTask38SlotReliefFieldParity"
TASK237 = ("demand", "demand_basis", "target_free", "reached")

# --- 四个 slot_relief 写入点（行号按当前工作树；锚点是文本，不依赖行号） -------------
ANCHOR_CLEAR_GATE = 'target_free=SLOT_RELIEF_TARGET_FREE, reached=False, freed=0,'
ANCHOR_CLEAR_GATE_DB = 'demand_basis="space_pressure", trigger="clear_gate",'
ANCHOR_PRESSURE_STUCK = 'reached=False, pressure=True,'
ANCHOR_PRESSURE_STUCK_DB = 'demand_basis="space_pressure", target_free=SLOT_RELIEF_TARGET_FREE,'
ANCHOR_BUY_FULL = 'demand_basis="buy_full", target_free=1, reached=False,'
ANCHOR_MAIN_REACHED = 'reached=bool(reached), pressure=bool(space_pressure),'
ANCHOR_MAIN_DB = 'demand_basis=str(demand_basis), target_free=int(target_free),'

# (name, 说明, [(relpath, old, new)], 预期探针口径, 预期单测口径)
CASES: list[tuple[str, str, list[tuple[str, str, str]], str, str]] = [
    ("C1_drop_reached_arg", "删掉 clear_gate 的 reached 参数（原始缺口复现）",
     [(LR, ANCHOR_CLEAR_GATE, 'target_free=SLOT_RELIEF_TARGET_FREE, freed=0,')],
     "FAIL", "KILL"),
    ("C2_reached_always_true", "clear_gate 的 reached 语义改错（恒 True）",
     [(LR, ANCHOR_CLEAR_GATE, 'target_free=SLOT_RELIEF_TARGET_FREE, reached=True, freed=0,')],
     "PASS", "KILL"),
    ("C2b_main_reached_true", "主通道 reached 语义改错（恒 True，破坏动态判据）",
     [(LR, ANCHOR_MAIN_REACHED, 'reached=True, pressure=bool(space_pressure),')],
     "PASS", "KILL"),
    ("C3a_drop_reached_other_site_pressure", "漏修其它写入点：压力卡死点丢 reached",
     [(LR, ANCHOR_PRESSURE_STUCK, 'pressure=True,')],
     "FAIL", "KILL"),
    ("C3b_drop_reached_other_site_buy_full", "漏修其它写入点：buy_full 点丢 reached",
     [(LR, ANCHOR_BUY_FULL, 'demand_basis="buy_full", target_free=1,')],
     "FAIL", "KILL"),
    ("C4a_demand_basis_buy_full_changed", "改 buy_full 点的 demand_basis 值",
     [(LR, ANCHOR_BUY_FULL, 'demand_basis="space_pressure", target_free=1, reached=False,')],
     "PASS", "KILL"),
    ("C4b_demand_basis_clear_gate_changed", "改 clear_gate 点的 demand_basis 值（本次修复点）",
     [(LR, ANCHOR_CLEAR_GATE_DB, 'demand_basis="buy_full", trigger="clear_gate",')],
     "PASS", "?"),
    ("C4c_demand_basis_main_changed", "改主通道的 demand_basis 值",
     [(LR, ANCHOR_MAIN_DB, 'demand_basis="WRONG", target_free=int(target_free),')],
     "PASS", "?"),
    ("C4d_demand_basis_pressure_changed", "改压力卡死点的 demand_basis 值",
     [(LR, ANCHOR_PRESSURE_STUCK_DB, 'demand_basis="buy_full", target_free=SLOT_RELIEF_TARGET_FREE,')],
     "PASS", "?"),
    ("C5_target_free_value_wrong", "clear_gate 的 target_free 值写错（99）",
     [(LR, ANCHOR_CLEAR_GATE, 'target_free=99, reached=False, freed=0,')],
     "PASS", "?"),
    ("C6_reached_int_zero", "clear_gate 的 reached 写成 int 0（不是 False 单例）",
     [(LR, ANCHOR_CLEAR_GATE, 'target_free=SLOT_RELIEF_TARGET_FREE, reached=0, freed=0,')],
     "PASS", "?"),
]


def slot_relief_calls(src: str) -> list[tuple[int, list[str]]]:
    """AST 找所有 _journal("slot_relief", ...) 调用 → [(行号, [kw 名])]。"""
    tree = ast.parse(src)
    out: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        attr = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        if attr != "_journal" or not node.args:
            continue
        a0 = node.args[0]
        if isinstance(a0, ast.Constant) and a0.value == "slot_relief":
            kws = [k.arg for k in node.keywords if k.arg]
            out.append((node.lineno, kws))
    return out


def probe_check(root: Path) -> tuple[str, list[str]]:
    """探针口径：所有 slot_relief 调用是否都带 TASK237 字段集。"""
    txt = (root / LR).read_text(encoding="utf-8")
    bad: list[str] = []
    n = 0
    for line, kws in slot_relief_calls(txt):
        n += 1
        missing = [k for k in TASK237 if k not in kws]
        if missing:
            bad.append(f"longrun.py:{line} 缺 {missing}")
    return ("FAIL" if bad else "PASS"), [f"slot_relief 调用 {n} 处"] + bad


def run_tests(root: Path) -> tuple[str, str, list[str]]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    p = subprocess.run([PY, "-m", "unittest", TEST_ID, "-v"], cwd=str(root),
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    verdict = "KILL" if "FAILED" in out else "SURVIVE"
    failing = [ln.strip().split(" ")[0] for ln in out.splitlines()
               if ln.startswith(("FAIL:", "ERROR:"))]
    ran = next((ln for ln in out.splitlines() if ln.startswith("Ran ")), "")
    return verdict, f"{ran} | {'FAILED' if verdict == 'KILL' else 'OK'}", failing


def make_tree(tag: str, mutations: list[tuple[str, str, str]], ref: str | None) -> Path:
    dst = TMP_BASE / tag
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    if ref:
        # 从冻结树导出基线（用于对照"修前红"）
        subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref],
                       stdout=open(TMP_BASE / f"{tag}.tar", "wb"), check=True)
        shutil.unpack_archive(str(TMP_BASE / f"{tag}.tar"), str(dst))
    else:
        for d in ("brain", "tests"):
            shutil.copytree(REPO / d, dst / d,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for rel, old, new in mutations:
        p = dst / rel
        txt = p.read_text(encoding="utf-8")
        if txt.count(old) != 1:
            raise SystemExit(f"[{tag}] 锚点不唯一/未命中 ({txt.count(old)} 次): {old!r}")
        p.write_text(txt.replace(old, new), encoding="utf-8")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None, help="从该 git ref 的冻结树取基线（如 HEAD / 冻结 commit）")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    TMP_BASE.mkdir(parents=True, exist_ok=True)
    lines = [f"REPO={REPO}", f"ref={args.ref or '(working tree, 修前)'}", f"python={PY}", ""]

    # 基线（无变异）
    base_tag = "base_" + (args.ref or "worktree").replace("/", "_")
    b = make_tree(base_tag, [], args.ref)
    pv, pdet = probe_check(b)
    tv, tdet, tfail = run_tests(b)
    lines += [f"[基线 {base_tag}] 探针={pv} {pdet}", f"[基线 {base_tag}] 单测={tv} {tdet} {tfail}", ""]
    print("\n".join(lines[-3:]))

    rows = []
    for name, desc, muts, exp_probe, exp_test in CASES:
        if args.only and args.only not in name:
            continue
        try:
            root = make_tree(name, muts, args.ref)
        except SystemExit as e:
            lines.append(f"[{name}] 锚点失败: {e}")
            continue
        pv, pdet = probe_check(root)
        tv, tdet, tfail = run_tests(root)
        rows.append((name, desc, exp_probe, pv, exp_test, tv, tfail, tdet))
        lines.append(f"[{name}] {desc}")
        lines.append(f"    探针口径: 预期{exp_probe} 实测{pv}  {pdet}")
        lines.append(f"    单测口径: 预期{exp_test} 实测{tv}  {tdet}  {tfail}")
        print(f"{name}: probe={pv}(exp {exp_probe}) test={tv}(exp {exp_test}) {tfail}")

    # 汇总
    lines += ["", "=== 自报 vs 实测 ===",
              f"{'用例':38} {'探针预期':8} {'探针实测':8} {'单测预期':8} {'单测实测':8} 判红测试"]
    for name, desc, ep, pv, et, tv, tfail, _ in rows:
        lines.append(f"{name:38} {ep:8} {pv:8} {et:8} {tv:8} {','.join(tfail) or '-'}")

    out = REPO / "scratch" / "_t38_mutate_out.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
