r"""task-183 变异装置（自建）。

作者 docstring 里提到的 `scratch/_t181_mutate.py` / `_t182_mutate.py` **不存在**（task-171/178 同一模式），
所以由我按卡面要求自建：每个变异把 `brain/`、`tests/`、`mod/` 拷进 `scratch/_t183_mut/<case>/`，
在**副本**上做一处字面改动，再在副本里跑这 4 个类，数红（FAIL/ERROR）条数：

    tests.test_farmwork.TestTask181HarvestEvidence
    tests.test_longrun.TestTask176HarvestMethodSourceAndActed
    tests.test_longrun.TestTask182ActedEvidenceAndRules
    tests.test_longrun.TestTask182ClumpRulesBehaviour

用法：`& $py scratch\_t183_mutate.py`（可选 `--case m183a`；`--keep` 保留副本树）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUT = ROOT / "scratch" / "_t183_mut"

TESTS = [
    "tests.test_farmwork.TestTask181HarvestEvidence",
    "tests.test_longrun.TestTask176HarvestMethodSourceAndActed",
    "tests.test_longrun.TestTask182ActedEvidenceAndRules",
    "tests.test_longrun.TestTask182ClumpRulesBehaviour",
]

FW = "brain/agentfarm/farmwork.py"
RULES = "mod/AgentFarm.Bridge/ClumpRules.cs"

# 期望红条数（我按代码路径推断；`None` = 只测不判）
EXPECT = {
    "control": 0,
    "m183a_crop_gone_only": 2,      # 判据退回"只看 crop 消失" ⇒ 再生作物/仅计数下降两类假阴
    "m183b_capacity_as_free": 2,    # 拿容量字段当空槽 ⇒ 背包满那两条
    "m183c_loot_single_qid": 1,     # loot 只记 1 个 qid
    "m183d_receipt_first": 2,       # 回执优先（老行为）：再生作物假阴 + 回执 acted=false 直接判死
    "m183e_clumprules_early_null": 1,   # GAP-1 replay：field 兜底被 null 短路
    "m183f_nit1_gate_removed": 2,   # NIT-1 闸被删
}


def _sub_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"[变异失败] 锚点未命中 {path.name} :: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _line_index(path: Path, stripped: str) -> tuple[list[str], int, str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip() == stripped:
            return lines, i, ln[:len(ln) - len(ln.lstrip())]
    raise SystemExit(f"[变异失败] 行锚点未命中 {path.name} :: {stripped!r}")


def _sub_line(path: Path, stripped: str, body: str) -> None:
    lines, i, indent = _line_index(path, stripped)
    lines[i] = indent + body + "\n"
    path.write_text("".join(lines), encoding="utf-8")


def _del_line(path: Path, stripped: str) -> None:
    lines, i, _indent = _line_index(path, stripped)
    del lines[i]
    path.write_text("".join(lines), encoding="utf-8")


def _insert_after(path: Path, stripped: str, body: str) -> None:
    lines, i, indent = _line_index(path, stripped)
    lines.insert(i + 1, indent + body + "\n")
    path.write_text("".join(lines), encoding="utf-8")


# ─────────────────────────── 各变异 ───────────────────────────
def m183a(root: Path) -> None:
    _sub_line(root / FW, "if evidence:", "if crop_gone:")


def m183b(root: Path) -> None:
    _sub_file(root / FW, 'return max(0, int(cap) - len(inv)), "ok"',
              'return max(0, int(cap)), "ok"')


def m183c(root: Path) -> None:
    _sub_line(root / FW, "for qid, n in (after or {}).items():",
              "for qid, n in list((after or {}).items())[:1]:")


def m183d(root: Path) -> None:
    _sub_file(root / FW, '            acted = receipt.get("acted")',
              '            acted = receipt.get("acted")\n'
              '            if acted is False:\n'
              '                r.code = "failed"\n'
              '                r.reason = "回执优先（变异）"\n'
              '                return r')


def m183e(root: Path) -> None:
    """GAP-1 replay：游戏分支之后插 `return (null, null);`（等价兜底被短路）。"""
    _insert_after(root / RULES,
                  'if (gameSaid.HasValue) return (gameSaid.Value, "game");',
                  "return (null, null);")


def m183f(root: Path) -> None:
    _del_line(root / RULES,
              "if (forageCrop.Value && whichForageCrop == null) return (null, null);")


MUTATORS = {
    "control": None,
    "m183a_crop_gone_only": m183a,
    "m183b_capacity_as_free": m183b,
    "m183c_loot_single_qid": m183c,
    "m183d_receipt_first": m183d,
    "m183e_clumprules_early_null": m183e,
    "m183f_nit1_gate_removed": m183f,
}


def _copy_tree(case: Path) -> None:
    if case.exists():
        shutil.rmtree(case, ignore_errors=True)
    case.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "bin", "obj", "_t183_mut", "_t178_mut",
                                    "_t171_mut", "_t166_pre", "_t166_mut", "_t150_pre149",
                                    "_t159_pre", "_t135_*")
    for sub in ("brain", "tests", "mod"):
        shutil.copytree(ROOT / sub, case / sub, ignore=ignore)


def run_case(name: str, keep: bool = False) -> tuple[int, list[str], str]:
    case = MUT / name
    _copy_tree(case)
    mutator = MUTATORS[name]
    if mutator is not None:
        mutator(case)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(case), str(case / "brain")])
    proc = subprocess.run([sys.executable, "-m", "unittest", "-v", *TESTS], cwd=str(case),
                          env=env, capture_output=True, text=True, timeout=2700)
    out = (proc.stdout or "") + (proc.stderr or "")
    reds = [ln.strip().split(" ")[0] for ln in out.splitlines()
            if (" ... FAIL" in ln or " ... ERROR" in ln)]
    ran = next((ln.strip() for ln in out.splitlines() if ln.strip().startswith("Ran ")), "?")
    tail = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(("OK", "FAILED"))]
    if not keep:
        shutil.rmtree(case, ignore_errors=True)
    summary = f"{ran} | {tail[-1] if tail else '?'} | 红 {len(reds)}"
    return len(reds), reds, summary


def main(argv: list[str]) -> int:
    only = None
    keep = "--keep" in argv
    if "--case" in argv:
        only = argv[argv.index("--case") + 1]
    names = [only] if only else list(MUTATORS)
    print(f"task-183 变异装置 · 根 = {ROOT}\n")
    bad = 0
    for name in names:
        red, reds, summary = run_case(name, keep=keep)
        exp = EXPECT.get(name)
        verdict = "—"
        if exp is not None:
            ok = red == exp
            verdict = "符合期望" if ok else f"**与期望({exp})不符**"
            if not ok:
                bad += 1
        print(f"[{name}] {summary}  {verdict}")
        for r in reds:
            print(f"      red: {r}")
    print(f"\n== 期望不符的变异数：{bad} ==")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
