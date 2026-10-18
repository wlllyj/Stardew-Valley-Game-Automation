#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""【0.7.46 / task-31 预热】变异两列表模板（作者自报 vs 我方副本实测）。

机制继承 `scratch/_t0745b_mutate.py`：在**冻结树/HEAD 的临时副本**里做文本变异，
原树零改动；判杀器 = 定向单测（任一红即 KILLED），冻结后接正式 probe 的判据段。

现在只对 0.7.46 冻结前已落袋的卡做**形式演示**（task-26/task-27 的真实锚点）；
task-28/25/33 的锚点要等冻结树，先置 enabled=False（--check-anchors 会单列 pending）。

用法（PYTHONUTF8=1）：
    python scratch/_t0746_prep_mut.py --check-anchors
    python scratch/_t0746_prep_mut.py --only m26
    python scratch/_t0746_prep_mut.py --all
    python scratch/_t0746_prep_mut.py --base <冻结树> --check-anchors   # 冻结后
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
COPY = ("brain", "tests", "tools")

# 定向单测杀器（每张卡一个类；冻结后加 task-28/25/33 的类）
UNITTESTS = {
    "26": "tests.test_longrun.TestTask26ResumeBudget",
    "27": "tests.test_longrun.TestTask27EnclosedBatch",
    "28": "tests.test_longrun.TestTask28InventoryDiscipline",   # 待冻结核实类名
    "25": "tests.test_longrun.TestTask25BackpackUpgrade",       # 待冻结核实类名
    "33": "tests.test_longrun.TestTask33TalkPrimitive",         # 待冻结核实类名
}

# 作者自报（release 文档登记的汇总口径；逐条自报数脚本里没有独立出处）
CLAIMED = {
    "26": "3/3（release 登记）",
    "27": "8/8（release 登记）",
    "28": "待作者报",
    "25": "待作者报",
    "33": "待作者报",
}

CASES: list[dict] = [
    {
        "name": "m26_claim_always_exhausted",
        "card": "26",
        "enabled": True,
        "edits": [(
            "brain/agentfarm/longrun.py",
            '        claim_exhausted = (int(snap["executable"]) == 0\n'
            '                           and int(snap.get("malformed", 0)) == 0)',
            '        claim_exhausted = True',
        )],
        "note": "预算用尽/还有 7 格可执行时仍宣称 resume_exhausted（不写 budget 变体）",
    },
    {
        "name": "m26_budget_evidence_dropped",
        "card": "26",
        "enabled": True,
        "edits": [(
            "brain/agentfarm/longrun.py",
            '            resume_walk_attempts=self.resume_walk_attempts,',
            '            resume_walk_attempts=None,',
        )],
        "note": "budget 收工不再记尝试计数 ⇒ 预算耗尽不可审计/与无目标混淆",
    },
    {
        "name": "m27_prefilter_off",
        "card": "27",
        "enabled": True,
        "edits": [(
            "brain/agentfarm/longrun.py",
            '            pool = self._prefilter_known_enclosed(task, obs, pool)',
            '            pool = pool',
        )],
        "note": "挡死格不再前置过滤 ⇒ till 12 格重回 unreachable（吃掉 bound，0.7.45 形态）",
    },
    {
        "name": "m27_encircled_bucket_off",
        "card": "27",
        "enabled": True,
        "edits": [(
            "brain/agentfarm/longrun.py",
            "            if t in self.encircled_day or not self._known_enclosed(obs, t):",
            "            if True:",
        )],
        "note": "预过滤判据被短路 ⇒ encircled 归类失效但代码不报错",
    },
    # ---- 冻结后补锚点：现在显式禁用，防冻结后漏填 ----
    {
        "name": "m28_wood_whitelist_restored",
        "card": "28",
        "enabled": False,
        "edits": [],
        "note": "冻结后锚点：售材候选/白名单重新收 (O)388；判红=满包压力卖建材",
    },
    {
        "name": "m28_inventory_blocked_shortcircuit",
        "card": "28",
        "enabled": False,
        "edits": [],
        "note": "冻结后锚点：四门槛短路为 True；判红=缺证据仍 inventory_blocked 放行",
    },
    {
        "name": "m25_direct_backpack_write",
        "card": "25",
        "enabled": False,
        "edits": [],
        "note": "冻结后锚点：answerDialogue 成功路径改成直接 increaseBackpackSize/Money 写入",
    },
    {
        "name": "m25_bag_count_criterion",
        "card": "25",
        "enabled": False,
        "edits": [],
        "note": "冻结后锚点：成功判据从 inventoryCount 差分改回 len(inventory) 增量（旧判据复活）",
    },
    {
        "name": "m33_talk_synthesizes_input",
        "card": "33",
        "enabled": False,
        "edits": [],
        "note": "冻结后锚点：talk 原语绕过 NPC.checkAction 改合成键鼠/直写 NPC 字段",
    },
]


def prepare_base() -> Path:
    """从 HEAD 取 brain/tests/tools 到临时树（与作者脚本同口径）。"""
    root = Path(tempfile.mkdtemp(prefix="_t0746_base_"))
    tar_bytes = subprocess.run(
        ["git", "-C", str(REPO), "archive", "--format=tar", "HEAD", *COPY],
        capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        tar.extractall(root, filter="data")
    return root


def copy_tree(base: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in COPY:
        src = base / name
        if src.exists():
            shutil.copytree(src, dest / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def run_unittest(tree: Path, card: str) -> tuple[int, bool]:
    target = UNITTESTS.get(card)
    if not target:
        return 0, False
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=str(tree / "brain"))
    r = subprocess.run([PY, "-m", "unittest", target], cwd=str(tree),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    fails = len(re.findall(r"^(FAIL|ERROR):", out, re.M))
    ran = re.search(r"^Ran (\d+) tests?", out, re.M)
    ok = "OK" in out and r.returncode == 0
    return fails, bool(ran) and ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="冻结树路径；缺省用 git archive HEAD 的 brain/tests/tools")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.list:
        for c in CASES:
            print(f"{c['name']}  card={c['card']}  {'enabled' if c['enabled'] else 'PENDING'}"
                  f"  claimed={CLAIMED.get(c['card'], '?')}  :: {c['note']}")
        return 0

    base = Path(args.base).resolve() if args.base else prepare_base()
    print(f"base={base}")

    if args.check_anchors:
        bad, pending = 0, 0
        for c in CASES:
            if not c["enabled"]:
                pending += 1
                print(f"[PENDING] {c['name']}（冻结后补锚点）")
                continue
            for rel, old, _new in c["edits"]:
                text = (base / rel).read_text(encoding="utf-8", errors="replace")
                n = text.count(old)
                bad += int(n != 1)
                print(f"[{'OK' if n == 1 else f'BAD({n})'}] {c['name']} :: {rel} :: {old[:52]!r}")
        print(f"\n锚点：enabled {len(CASES) - pending} 条，坏 {bad} 处；pending {pending} 条")
        return 0 if bad == 0 else 1

    sel = [c for c in CASES if c["enabled"] and (args.all or (args.only and c["name"].startswith(args.only)))]
    if not sel:
        print("没有选中的变异（用 --all / --only <name>；pending 条目冻结后再跑）")
        return 2

    print("\n== 基线自检 ==")
    base_ok = True
    for card in sorted({c["card"] for c in sel}):
        fails, ok = run_unittest(base, card)
        print(f"  {UNITTESTS.get(card)}：FAIL/ERROR={fails} Ran+OK={ok}")
        base_ok = base_ok and ok and fails == 0
    if not base_ok:
        print("基线不绿，终止")
        return 3

    tmp_root = Path(tempfile.mkdtemp(prefix="_t0746_mut_"))
    fails_total = 0
    for c in sel:
        tree = tmp_root / c["name"]
        copy_tree(base, tree)
        bad = False
        for rel, old, new in c["edits"]:
            p = tree / rel
            text = p.read_text(encoding="utf-8", errors="replace")
            if text.count(old) != 1:
                print(f"[ANCHOR-FAIL] {c['name']} :: {rel}（出现 {text.count(old)} 次）")
                fails_total += 1
                bad = True
                break
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
        if bad:
            continue
        kills, ok = run_unittest(tree, c["card"])
        state = "KILLED" if kills > 0 else "SURVIVED"
        print(f"[{state}] {c['name']}（card {c['card']}）实测杀={kills} / 自报 {CLAIMED.get(c['card'])}"
              f" :: {c['note']}")
        if kills <= 0:
            fails_total += 1
    shutil.rmtree(tmp_root, ignore_errors=True)
    if not args.base:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n合计：{len(sel)} 条，未杀/异常 {fails_total}")
    return 0 if fails_total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
