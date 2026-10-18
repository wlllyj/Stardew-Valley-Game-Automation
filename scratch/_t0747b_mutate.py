# -*- coding: utf-8 -*-
"""【task-37 / 0.7.47】deputy-lead 独立变异自检（副本跑）。

机制：把冻结树 brain/tests/tools/mod/logs/scratch 复制到临时副本 → 文本变异 → 跑
① 我方探针 `scratch/_t0747b_probe.py --only B,C`（出现 FAIL 即杀）
② 定向 unittest（红即杀）。
只在副本上改，绝不碰冻结树/仓库工作树。

用法（PYTHONUTF8=1）：
  python scratch/_t0747b_mutate.py --check-anchors
  python scratch/_t0747b_mutate.py --all
  python scratch/_t0747b_mutate.py --only m37a
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
PROBE = REPO / "scratch" / "_t0747b_probe.py"
PY = sys.executable
BASE = pathlib.Path(os.environ.get("T0747B_BASE") or (pathlib.Path(os.environ["TEMP"]) / "t0747_frozen"))
COMMIT = os.environ.get("T0747B_COMMIT", "a03a564")

TARGETS_ROOT = "tests.test_longrun.TestTask35BackpackGate"
TARGETS_T25 = "tests.test_longrun.TestTask25BackpackUpgrade"

# (name, card, claimed, files->[(relpath, old, new)], unittests, note)
CASES: list[tuple[str, str, int, list[tuple[str, str, str]], list[str], str]] = [
    ("m37a_default_back_on", "task-35", 0, [
        ("brain/agentfarm/longrun.py",
         "    backpack_upgrade_enabled: bool = False,",
         "    backpack_upgrade_enabled: bool = True,"),
    ], [TARGETS_ROOT, TARGETS_T25],
     "默认值改回 True ⇒ 默认就会发 talk/购买（B1/C1 应杀）"),
    ("m37b_disabled_branch_removed", "task-35", 0, [
        ("brain/agentfarm/longrun.py",
         "        if not self.backpack_upgrade_enabled:\n"
         '            self._backpack_skip(rep, "disabled", obs)\n'
         "            return False\n",
         "        if False:\n"
         '            self._backpack_skip(rep, "disabled", obs)\n'
         "            return False\n"),
    ], [TARGETS_ROOT],
     "删掉默认关闭分支 ⇒ 关闭时照发 talk（B1/C2 应杀）"),
    ("m37c_drop_double_diff", "task-35", 0, [
        ("brain/agentfarm/longrun.py",
         "        if money_ok and cap_ok:",
         '        if talk.get("applied"):'),
    ], [TARGETS_ROOT, TARGETS_T25],
     "开启后丢双差分 ⇒ 信回执 applied（B2b/C3 应杀）"),
    ("m37d_skip_trace_dropped", "task-35", 0, [
        ("brain/agentfarm/longrun.py",
         '        if (why in ("cannot_afford", "talk_unavailable", "disabled")\n'
         "                and not self.backpack_skip_noted):",
         '        if (False and why in ("cannot_afford", "talk_unavailable", "disabled")\n'
         "                and not self.backpack_skip_noted):"),
    ], [TARGETS_ROOT],
     "disabled 不留 buy skipped 痕迹 ⇒ 日终无法区分跳过与失败（B1b/B1c 应杀）"),
    ("m37e_env_relaxed", "task-35", 0, [
        ("tools/run-longrun.py",
         'BACKPACK_ENV_TRUTHY = ("1", "true", "yes", "on")',
         'BACKPACK_ENV_TRUTHY = ("1", "true", "yes", "on", "2")'),
    ], [TARGETS_ROOT],
     "env 真值表放宽（\"2\" 也当开）⇒ opt-in 面失控（C5 应杀）"),
    ("m37f_version_mismatch", "task-35", 0, [
        ("brain/agentfarm/bridge.py",
         'MOD_VERSION_EXPECTED = "0.7.47"',
         'MOD_VERSION_EXPECTED = "0.7.46"'),
    ], [],
     "bridge/manifest 版本不一致 ⇒ 版本载体口径被破坏（C6 应杀）"),
]


def _copy_tree(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("brain", "tests", "tools", "mod", "logs", "scratch"):
        s = src / name
        if s.is_dir():
            shutil.copytree(s, dst / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _run_probe(tree: pathlib.Path) -> tuple[int, int, str]:
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "T0747_ROOT": str(tree),
                "T0747_COMMIT": COMMIT, "PYTHONPATH": str(tree / "brain")})
    proc = subprocess.run([PY, str(PROBE), "--only", "B,C"], cwd=str(REPO),
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    out = (proc.stdout or "") + (proc.stderr or "")
    fails = sum(1 for ln in out.splitlines() if ln.startswith("  FAIL "))
    return proc.returncode, fails, out


def _run_unittest(tree: pathlib.Path, targets: list[str]) -> tuple[bool, int, list[str], str]:
    if not targets:
        return True, 0, [], ""
    env = dict(os.environ)
    env.update({"PYTHONUTF8": "1", "PYTHONPATH": str(tree / "brain")})
    proc = subprocess.run([PY, "-m", "unittest", "-v", *targets], cwd=str(tree),
                          env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    failures = re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)
    ok = bool(ran) and "OK" in out and proc.returncode == 0
    return ok, int(ran.group(1)) if ran else 0, failures, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--base", default="")
    args = ap.parse_args()

    base = pathlib.Path(args.base) if args.base else BASE
    if not (base / "brain" / "agentfarm" / "longrun.py").is_file():
        print(f"× 基线树不可用：{base}")
        return 2
    print(f"基线 = {base}（冻结树冷冻内容；变异只在临时副本）")
    print(f"COMMIT = {COMMIT}")

    if args.check_anchors:
        bad = 0
        for name, _card, _claimed, changes, _tests, _note in CASES:
            for rel, old, _new in changes:
                text = (base / rel).read_text(encoding="utf-8")
                n = text.count(old)
                mark = "OK" if n == 1 else "×"
                if n != 1:
                    bad += 1
                print(f"[{mark}] {name} :: {rel} 锚点出现 {n} 次（要求 1）")
        print(f"\n锚点核对：{'全部通过' if bad == 0 else f'{bad} 处异常'}")
        return 0 if bad == 0 else 1

    selected = [c for c in CASES if args.all or (args.only and args.only in c[0])]
    if not selected:
        print("没有匹配的变异（用 --all 或 --only m37x）")
        return 2

    with tempfile.TemporaryDirectory(prefix="t37-mutate-") as tmp:
        work = pathlib.Path(tmp) / "work"
        _copy_tree(base, work)
        print(f"副本 = {work}")
        all_tests = sorted({t for c in CASES for t in c[4]})
        rc0, fails0, _out0 = _run_probe(work)
        ok0, ran0, red0, _o = _run_unittest(work, all_tests)
        if fails0 or not ok0:
            print(f"× 基线不是绿的：probe FAIL={fails0} unittest OK={ok0} Ran {ran0} red={len(red0)}")
            return 2
        print(f"[baseline] OK（probe B,C FAIL=0；定向 unittest Ran {ran0} OK）")

        killed = survived = 0
        outcomes = []
        for name, card, claimed, changes, tests, note in selected:
            case_dir = pathlib.Path(tmp) / f"case_{name}"
            _copy_tree(work, case_dir)
            applied = True
            for rel, old, new in changes:
                target = case_dir / rel
                original = target.read_text(encoding="utf-8")
                if original.count(old) != 1:
                    applied = False
                    print(f"[{name}] × 锚点失效（{rel}: {original.count(old)} 次）")
                    break
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
            if not applied:
                outcomes.append((name, "ANCHOR_FAIL", card, claimed))
                continue
            rc, fails, out = _run_probe(case_dir)
            uok, uran, ured, uout = _run_unittest(case_dir, tests)
            if fails > 0 or not uok:
                killed += 1
                how = []
                if fails:
                    how.append(f"probe FAIL×{fails}")
                if not uok:
                    names = "、".join(f.split(".")[-1] for f in ured[:4]) or "（见输出）"
                    how.append(f"unittest 红 {len(ured)} 条：{names}")
                print(f"[{name}] killed（{'；'.join(how)}）—— {note}")
                outcomes.append((name, "KILLED", card, claimed))
            else:
                survived += 1
                print(f"[{name}] SURVIVED（probe FAIL=0，Ran {uran} OK）—— {note}")
                outcomes.append((name, "SURVIVED", card, claimed))

        print("\n===== 结果汇总 =====")
        for name, state, card, claimed in outcomes:
            print(f"{state:10s} {name:30s} {card} 作者自报={claimed}")
        total = len(selected)
        print(f"\n合计：{killed}/{total} 条变异被杀；未杀 {survived}；异常 {total - killed - survived}")
        return 0 if survived == 0 and (total - killed - survived) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
