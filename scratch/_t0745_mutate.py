"""task-15（0.7.45 day_justified 口径）变异矩阵 —— deputy 独立实测杀数。

作者自报的 4/4 不算证据：本脚本在**冻结树临时副本**里做文本变异，冻结树零改动；
判杀器 = 我方 `scratch/_t0745_probe.py` 的 B/C 段独立重放 + 作者定向单测
（任一红即算杀死；报告两列并列，不把作者单测当唯一判据）。

用法：
    python scratch/_t0745_mutate.py --base <冻结树> --check-anchors
    python scratch/_t0745_mutate.py --base <冻结树> --all
    python scratch/_t0745_mutate.py --base <冻结树> --only m0745a
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
COPY = ("brain", "tests", "tools")

# 每条 = (name, card, claimed, kind, [(relpath, old, new), ...], note)
CASES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = [
    (
        "m0745a_justified_without_evidence", "15", "无（我方自建，独立于作者 m1/m3）", "probe",
        [("brain/agentfarm/longrun.py",
          "        return pending_executable is not None and int(pending_executable) == 0",
          "        return True")],
        "resume_exhausted 收工不查可执行面证据 ⇒ 账本旧账直接洗成 day_justified",
    ),
    (
        "m0745b_dead_end_back_to_guard_caliber", "15", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          "        pending = self._ledger_pending()",
          "        pending = self._pending_work()")],
        "卡1/5 兜底改用剔除后的守卫口径 ⇒ 永远 []、兜底路径变死代码（A8 冬 9/14 形态回潮）",
    ),
    (
        "m0745c_blind_fail_open", "15", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          '            return {**base, "executable": len(guard_tiles), "unobserved": 0}',
          '            return {**base, "executable": 0, "unobserved": len(guard_tiles)}')],
        "观测不可用时把「没看到」当「没有」 ⇒ fail-closed 方向被反转（day_justified 会放行）",
    ),
    (
        "m0745d_guard_counts_stalled", "15", "无（我方自建，独立于作者 m2）", "probe",
        [("brain/agentfarm/longrun.py",
          '            if t in self.resume_stall_tiles:\n'
          '                # 【task-15 / 0.7.45】换片机制"回去看过、拿不出目标"的格今天也不算这片地的活\n'
          '                # （否则守卫被 0.7.44 冒烟冬 27 的 217 格旧账钉死；日终在 pending_stalled 留痕）。\n'
          '                continue',
          '            if t in self.resume_stall_tiles:\n'
          '                pass  # mutation: 停滞格仍算活（两口径混用）')],
        "守卫口径不剔除停滞格 ⇒ 217 旧账又把换片判据钉死（两口径重新混用）",
    ),
    (
        "m0745e_justified_off_by_one", "15", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          "        return pending_executable is not None and int(pending_executable) == 0",
          "        return pending_executable is not None and int(pending_executable) <= 1")],
        "证据门槛从 0 放宽到 ≤1 ⇒ 还剩 1 格真活也判「今天没活」（洗白）",
    ),
]


def build_mutant(base: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in COPY:
        src = base / name
        if src.exists():
            shutil.copytree(src, dest / name,
                            ignore=shutil.ignore_patterns("__pycache__", "obj", "bin"))


def run_probe(tree: Path) -> int:
    env = dict(os.environ, T0745_ROOT=str(tree), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, str(REPO / "scratch/_t0745_probe.py"), "--only", "B,C"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=900)
    return sum(1 for ln in r.stdout.splitlines() if "  FAIL  " in ln)


def run_unittest(tree: Path, dotted: str) -> int:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=str(tree / "brain"))
    r = subprocess.run([PY, "-m", "unittest", dotted], cwd=str(tree),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    return len(re.findall(r"^(FAIL|ERROR):", out, re.M))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(REPO))
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--unittest", default="tests.test_longrun.TestTask15PendingCaliber")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if args.list:
        for c in CASES:
            print(c[0], c[1], c[5])
        return 0
    if args.check_anchors:
        bad = 0
        for name, _card, _claimed, _kind, edits, _note in CASES:
            for rel, old, _new in edits:
                text = (base / rel).read_text(encoding="utf-8", errors="replace")
                n = text.count(old)
                if n != 1:
                    bad += 1
                print(f"[{'OK' if n == 1 else f'BAD({n})'}] {name} :: {rel} :: {old[:40]}")
        print(f"\n锚点：{sum(len(c[4]) for c in CASES)} 条，坏 {bad} 处")
        return 0 if bad == 0 else 1
    sel = [c for c in CASES if (args.all or (args.only and c[0].startswith(args.only)))]
    if not sel:
        print("没有选中的变异（用 --all / --only <name>）")
        return 2
    base_probe = run_probe(base)
    base_unit = run_unittest(base, args.unittest)
    base_probe_ok = base_probe == 0 and base_unit == 0
    print(f"base={base}\n基线自检：probe FAIL={base_probe} unittest FAIL/ERROR={base_unit}"
          f" ⇒ {'OK' if base_probe_ok else '基线不绿，终止'}")
    if not base_probe_ok:
        return 3
    tmp_root = Path(tempfile.mkdtemp(prefix="_t0745_mut_"))
    fails = 0
    for name, card, claimed, _kind, edits, note in sel:
        tree = tmp_root / name
        build_mutant(base, tree)
        for rel, old, new in edits:
            p = tree / rel
            text = p.read_text(encoding="utf-8", errors="replace")
            if text.count(old) != 1:
                print(f"[ANCHOR-FAIL] {name} :: {rel}")
                fails += 1
                break
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
        else:
            probe_kills = run_probe(tree)
            unit_kills = run_unittest(tree, args.unittest)
            kills = probe_kills + unit_kills
            print(f"[{'KILLED' if kills > 0 else 'SURVIVED'}] {name}（card {card}）"
                  f"实测杀 probe={probe_kills} unittest={unit_kills} / 自报 {claimed or '无'}"
                  f" :: {note}")
            if kills <= 0:
                fails += 1
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\n合计：{len(sel)} 条，未杀/异常 {fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
