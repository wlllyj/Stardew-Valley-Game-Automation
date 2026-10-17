#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""task-224 变异矩阵骨架（0.7.39 批次）—— 与 `_t224_probe.py` 配套。

只写 `scratch/`；不碰生产码。照 `_t200_mutate.py` 先例：**在冻结树副本上**做文本变异 → 跑探针/单测/C# 自检 →
报「自报 vs 实测」两列 → 跑完即删变异树。**正式验收必须用 `git archive` 冻结树**（工作树有 dev-coder 在制改动）。

用法（仓库根）：
    $env:PYTHONUTF8="1"
    python scratch\_t224_mutate.py --base scratch/_t224_frozen --check-anchors
    python scratch\_t224_mutate.py --base scratch/_t224_frozen --all
    python scratch\_t224_mutate.py --self-test          # 只验本脚本机械件（不碰仓库）

登记变异（`CASES`）：验收开始时按 task-224 卡面逐条填；每条 5 元组见 `reg()` 说明。
预期覆盖（骨架已留位，见文末 TODO）：
- P0-1：`StepResult.after` 去 before/after kind、护栏 B 去 cleared_tiles ⇒ 探针 P0-1 红
- P0-2：`DEFERRED_KINDS` 加 `tree`（白名单快照红）、`SKIP_KINDS` 加未登记 kind、announce 失效
- P0-3：原因码集加集外码、瓦片不变式失效、ACTIONLESS 去 sleep
- P0-4/5：gaps 非原子写、analyzer 去掉 §8 判红、verify-run3 反而判 §8
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE = REPO / "scratch" / "_t224_probe.py"
MUT_ROOT = REPO / "scratch" / "_t224_mut"

# 不依赖 PYTHONUTF8：Windows 控制台默认 gbk，遇到中文/箭头会崩
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

CASES: list[dict] = []


def reg(name: str, card: str, claimed, kind: str, edits: list[tuple[str, str, str]], note: str = "") -> None:
    """登记一条变异。

    kind:
      - `probe`               → 在变异树跑 `_t224_probe.py`，数 `  FAIL ` 行
      - `unittest:<dotted>`   → 跑指定测试点，数 `FAIL:`/`ERROR:`
      - `csharp`              → 跑 `dotnet run --project mod/AgentFarm.Bridge.Tests`，数 `^FAIL\\s` 行
    edits: [(相对路径, 原文, 替换文)]，原文必须**恰好命中 1 次**（否则判锚点坏）。
    claimed: 作者自报杀数（int 或 "?"）；实测由本脚本给出。
    """
    CASES.append({"name": name, "card": card, "claimed": claimed, "kind": kind,
                  "edits": edits, "note": note})


# ===== 验收开始时在这里登记（骨架阶段为空；下面 TEMPLATES 是待填清单）=====
# reg("m224a_after_no_kind", "218", "?", "probe",
#     [("brain/agentfarm/farmwork.py", "before_kind", "kindx")], "护栏 B 逐格证据失效")
TEMPLATES = [
    # (卡, 建议变异, 目标通道)
    ("218", "StepResult.after 去掉 before/after kind 或 cleared_tiles", "P0-1 护栏 B 逐格证据"),
    ("218", "DEFERRED_KINDS 里塞 tree（白名单快照应红）", "P0-2 白名单快照"),
    ("218", "SKIP_KINDS 加一个未登记 kind（⊆ 断言应红）", "P0-2 一致性约束"),
    ("218", "deferred announce 分支删掉（tiles 缺失时简报不再写暂不支持）", "P0-2 fail-closed announce"),
    ("219", "REASON_CODES 加集外码 / 去掉 unknown_evidence", "P0-3 闭合集"),
    ("219", "瓦片不变式校验改成恒真", "P0-3 单位对账"),
    ("219", "ACTIONLESS_TASKS 去掉 sleep", "P0-3 无动作白名单"),
    ("219", "gaps 写文件改成非原子（直接 write_text）", "P0-4 半写防护"),
    ("220", "analyzer 删掉 §8 判红分支", "P0-5 工具分工"),
    ("220", "verify-run3 反向加 §8 判红", "P0-5 工具分工"),
]


def sh(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 1800):
    e = {k: v for k, v in os.environ.items()}
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


IGNORE = shutil.ignore_patterns("__pycache__", "_t224_mut", "_t224_*", "*.pyc", ".git")


def build_mutant(case: dict, base: Path, *, fixtures: bool = False) -> Path:
    dest = MUT_ROOT / case["name"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=IGNORE)
    for rel, old, new in case["edits"]:
        p = dest / rel
        if not p.is_file():
            raise SystemExit(f"[{case['name']}] 变异文件不存在：{rel}")
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"[{case['name']}] 锚点命中 {n} 次（要求恰好 1 次）：{rel} :: {old[:60]!r}")
        p.write_text(text.replace(old, new), encoding="utf-8")
    if fixtures:
        logs = dest / "logs"
        logs.mkdir(exist_ok=True)
        for f in (REPO / "logs").glob("*.jsonl"):
            shutil.copy2(f, logs / f.name)
        for f in (REPO / "logs").glob("*.json"):
            shutil.copy2(f, logs / f.name)
        for f in (REPO / "scratch").glob("_ledger_*.jsonl"):
            shutil.copy2(f, dest / "scratch" / f.name)
    return dest


def run_case(case: dict, base: Path) -> dict:
    tree = build_mutant(case, base, fixtures=True)
    out: dict = {"name": case["name"], "card": case["card"], "kind": case["kind"],
                 "claimed": case["claimed"], "killed": 0, "lines": []}
    try:
        if case["kind"] == "probe":
            env = {"PYTHONUTF8": "1", "T224_ROOT": str(tree), "T224_ONLY": ""}
            r = sh([sys.executable, str(PROBE)], REPO, env=env)
            fails = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("  FAIL ")]
            out["killed"] = len(fails)
            out["lines"] = fails[:10]
        elif case["kind"].startswith("unittest:"):
            dotted = case["kind"].split(":", 1)[1]
            env = {"PYTHONUTF8": "1", "PYTHONPATH": f"{tree}{os.pathsep}{tree / 'brain'}"}
            r = sh([sys.executable, "-m", "unittest", dotted], tree, env=env)
            lines = (r.stdout + r.stderr).splitlines()
            hit = [ln for ln in lines if ln.startswith("FAIL:") or ln.startswith("ERROR:")]
            out["killed"] = len(hit)
            out["lines"] = hit[:10]
        elif case["kind"] == "csharp":
            proj = tree / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"
            r = sh(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"], tree)
            lines = (r.stdout + r.stderr).splitlines()
            hit = [ln for ln in lines if ln.startswith("FAIL ")]
            out["killed"] = len(hit)
            out["lines"] = hit[:10]
        else:
            raise SystemExit(f"未知 kind：{case['kind']}")
    finally:
        if tree.exists():
            shutil.rmtree(tree, ignore_errors=True)
    return out


def _verdict(row: dict) -> str:
    if row["claimed"] in ("?", None):
        return "一致（无自报）"
    try:
        return "一致" if int(row["killed"]) == int(row["claimed"]) else "**不符**"
    except (TypeError, ValueError):
        return "?"


def print_table(rows: list[dict]) -> None:
    print("\n== 变异实测（自报 vs 实测）==")
    print(f"{'case':34s} {'card':5s} {'kind':38s} {'自报':>4s} {'实测':>4s}  判定")
    for r in rows:
        print(f"{r['name']:34s} {r['card']:5s} {r['kind']:38s} {str(r['claimed']):>4s} "
              f"{str(r['killed']):>4s}  {_verdict(r)}")
        for ln in r["lines"]:
            print("      └ " + ln[:140])
    bad = sum(1 for r in rows if _verdict(r) == "**不符**")
    print(f"\n合计 {len(rows)} 条；自报/实测不符 {bad} 条")


def check_anchors(base: Path, card: str | None) -> int:
    bad_n = 0
    total = 0
    for case in CASES:
        if card and case["card"] != card:
            continue
        for rel, old, _new in case["edits"]:
            total += 1
            p = base / rel
            if not p.is_file():
                print(f"  [锚点坏] {case['name']} :: 文件缺失 {rel}")
                bad_n += 1
                continue
            n = p.read_text(encoding="utf-8").count(old)
            if n != 1:
                print(f"  [锚点坏] {case['name']} :: {rel} 命中 {n} 次 :: {old[:60]!r}")
                bad_n += 1
    print(f"锚点校验：{total} 处、坏 {bad_n} 处")
    return bad_n


def self_test() -> int:
    """只验机械件：临时目录建树、改一字、锚点命中/未命中、表输出。"""
    tmp = Path(tempfile.mkdtemp(prefix="t224selftest_"))
    try:
        base = tmp / "base"
        (base / "brain").mkdir(parents=True)
        sample = base / "brain" / "x.py"
        sample.write_text("VALUE = 1\nOTHER = 2\n", encoding="utf-8")
        probe_case = {"name": "selfcase", "card": "self", "claimed": "?", "kind": "probe",
                      "edits": [("brain/x.py", "VALUE = 1", "VALUE = 99")]}
        # 1) 锚点命中逻辑
        n_ok = (base / "brain/x.py").read_text(encoding="utf-8").count("VALUE = 1")
        print(("PASS" if n_ok == 1 else "FAIL") + " self-test 锚点命中 1 次")
        # 2) 坏锚点应被检出（用 check_anchors 的等价逻辑）
        bad = (base / "brain/x.py").read_text(encoding="utf-8").count("NOPE")
        print(("PASS" if bad == 0 else "FAIL") + " self-test 坏锚点命中 0 次（应报坏）")
        # 3) build_mutant 会改文件（用 MUT_ROOT 临时指向 tmp）
        global MUT_ROOT
        old_root = MUT_ROOT
        MUT_ROOT = tmp / "mut"
        try:
            tree = build_mutant(probe_case, base)
            changed = (tree / "brain/x.py").read_text(encoding="utf-8")
            print(("PASS" if "VALUE = 99" in changed else "FAIL") + " self-test build_mutant 生效")
            print(("PASS" if tree.exists() else "FAIL") + " self-test 变异树已建")
            shutil.rmtree(tree, ignore_errors=True)
        finally:
            MUT_ROOT = old_root
        # 4) 不一致锚点应抛 SystemExit（用出现 2 次的 "=" 模拟重复锚点）
        dup = dict(probe_case, name="dup", edits=[("brain/x.py", "=", "==")])
        try:
            build_mutant(dup, base)
            print("FAIL self-test 重复锚点未报错")
        except SystemExit:
            print("PASS self-test 重复锚点报错符合预期")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="task-224 变异矩阵骨架")
    ap.add_argument("--base", help="冻结树根（git archive 解出来的目录）")
    ap.add_argument("--card", help="只跑某张卡（218/219/220…）")
    ap.add_argument("--only", action="append", default=[], help="只跑指定变异名（可多次）")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if a.list:
        print(f"已登记变异 {len(CASES)} 条：")
        for c in CASES:
            print(f"  {c['name']:34s} card={c['card']} kind={c['kind']} claimed={c['claimed']}")
        print("\n待填清单（card, 变异, 目标通道）：")
        for card, mut, chan in TEMPLATES:
            print(f"  [{card}] {mut}  →  期望红在：{chan}")
        return 0
    base = Path(a.base).resolve() if a.base else None
    if base is None or not base.is_dir():
        print("需要 --base <冻结树>（或 --self-test / --list）")
        return 2
    if a.check_anchors:
        return 1 if check_anchors(base, a.card) else 0
    if not CASES:
        print("CASES 为空（骨架阶段）。验收开始时按 TEMPLATES 逐条 reg() 登记后重跑。")
        print("先 --check-anchors 校验，再 --all。")
        return 0
    todo = [c for c in CASES if (not a.card or c["card"] == a.card)
            and (not a.only or c["name"] in a.only)]
    rows = []
    for c in todo:
        try:
            rows.append(run_case(c, base))
        except SystemExit as exc:
            print(f"  [跳过] {exc}")
    print_table(rows)
    return 0 if not rows else (0 if sum(1 for r in rows if _verdict(r) == "**不符**") == 0 else 1)


if __name__ == "__main__":
    sys.exit(main())
