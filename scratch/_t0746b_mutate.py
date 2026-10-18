# -*- coding: utf-8 -*-
"""【task-31 / 0.7.46】deputy-lead 独立变异自检（副本跑）。

机制：把冻结树 brain/tests/tools/mod 复制到临时副本 → 文本变异 → 跑
① 我方探针 `scratch/_t0746b_probe.py --only B,C`（出现 FAIL 即杀）
② 定向 unittest（红即杀）。
只在副本上改，绝不碰冻结树/仓库工作树。

用法（PYTHONUTF8=1）：
  python scratch/_t0746b_mutate.py --check-anchors
  python scratch/_t0746b_mutate.py --all
  python scratch/_t0746b_mutate.py --only m31a
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
PROBE = REPO / "scratch" / "_t0746b_probe.py"
PY = sys.executable
BASE = pathlib.Path(os.environ.get("T0746B_BASE") or (pathlib.Path(os.environ["TEMP"]) / "t0746_frozen"))
COMMIT = os.environ.get("T0746B_COMMIT", "737c4a5")

# (name, card, claimed, files->[(relpath, old, new)], unittests, note)
CASES: list[tuple[str, str, int, list[tuple[str, str, str]], list[str], str]] = [
    ("m31a_malformed_veto_off", "task-22", 0, [
        ("brain/agentfarm/longrun.py",
         "    if int(malformed_tiles) > 0:\n        return False",
         "    if False:\n        return False"),
    ], ["tests.test_longrun.TestTask22MalformedTiles"],
     "删 malformed 一票否决 ⇒ 残客观测可被洗白放行"),
    ("m31b_malformed_back_to_unobserved", "task-22", 0, [
        ("brain/agentfarm/longrun.py",
         '            if not tv.get("crop") and not kind and t not in tillable:\n'
         "                malformed += 1\n"
         "                malformed_tiles.append(tuple(t))\n"
         "                continue",
         '            if False:\n'
         "                malformed += 1\n"
         "                malformed_tiles.append(tuple(t))\n"
         "                continue"),
    ], ["tests.test_longrun.TestTask22MalformedTiles", "tests.test_longrun.TestTask15PendingCaliber"],
     "残缺记录归回 unobserved ⇒ malformed=0（NIT-1 原形复活）"),
    ("m31c_resume_threshold_cleared", "task-15", 0, [
        ("brain/agentfarm/longrun.py",
         '        return (ended_by == "sleep" and pending_executable is not None\n'
         "                and int(pending_executable) == 0)",
         "        return True"),
    ], ["tests.test_longrun.TestTask15PendingCaliber"],
     "resume_exhausted 门槛清空 ⇒ exec>0 也判 day_justified"),
    ("m31d_inventory_unconditional", "task-28", 0, [
        ("brain/agentfarm/longrun.py", "        accepted = not gaps", "        accepted = True"),
    ], ["tests.test_longrun.TestTask28BagEvidence"],
     "满包闸不看证据一律认 ⇒ inventory_blocked 无条件放行"),
    ("m31e_wood_back_to_sellable", "task-28", 0, [
        ("brain/agentfarm/farmwork.py",
         'SURPLUS_MATERIAL_IDS = frozenset({\n    "92",    # Sap（树液，树桶副产品）\n    "766",   # Slime（史莱姆掉落）\n})',
         'SURPLUS_MATERIAL_IDS = frozenset({\n    "92",    # Sap（树液，树桶副产品）\n    "766",   # Slime（史莱姆掉落）\n    "388",   # Wood（变异：建材加回白名单）\n})'),
    ], ["tests.test_longrun.TestTask28BagEvidence"],
     "Wood(388) 加回可卖白名单 ⇒ 满包压力下可卖建材"),
    ("m31f_sell_bypass_shipitem", "task-28", 0, [
        ("brain/agentfarm/farmwork.py",
         "            self.c.sell(slot, whitelist=allow, timeout_ms=timeout_ms)",
         '            self.player_of(obs)["inventory"].clear()  # 变异：绕过 Farm.shipItem 直改观测'),
    ], ["tests.test_longrun.TestTask28BagEvidence"],
     "绕过桥 sell（Farm.shipItem）直改背包 ⇒ 无限造腾格"),
    ("m31g_backpack_trust_receipt", "task-25", 0, [
        ("brain/agentfarm/longrun.py", "        if money_ok and cap_ok:", "        if True:"),
    ], ["tests.test_longrun.TestTask25BackpackUpgrade"],
     "背包升级信回执不查观测差分 ⇒ 钱没扣也报成功"),
    ("m31h_loot_cap_relaxed", "task-28", 0, [
        ("brain/agentfarm/longrun.py",
         "CLEAR_LOOT_LOSS_MAX_STEPS = 5", "CLEAR_LOOT_LOSS_MAX_STEPS = 50"),
    ], ["tests.test_longrun.TestTask28BagEvidence"],
     "清障丢失上界 5→50 ⇒ loot_lost_steps 无界"),
    ("m31i_checks_polluted", "task-28", 0, [
        ("brain/agentfarm/longrun.py",
         "        rep.checks = {",
         '        rep.checks = {\n            "pending_malformed": int(rep.pending_malformed),'),
    ], ["tests.test_longrun.TestTask28BagEvidence", "tests.test_longrun.TestTask15PendingCaliber"],
     "新字段塞进 checks ⇒ 10 键口径被污染"),
    ("m31j_unreachable_bound_raised", "task-27", 0, [
        ("brain/agentfarm/longrun.py",
         "        unreachable_bound = max(5, int(0.2 * bound_basis_steps))",
         "        unreachable_bound = max(5, int(0.5 * bound_basis_steps))"),
    ], ["tests.test_longrun.TestTask27EnclosedBatch"],
     "抬高 unreachable bound 20%→50% ⇒ 把真走不到洗成界内"),
    ("m31k_talk_writes_money", "task-33", 0, [
        ("mod/AgentFarm.Bridge/TalkSkill.cs",
         "found.checkAction(who, loc);",
         "Game1.player.Money += 1;  // 变异：talk 内直写钱\n                    found.checkAction(who, loc);"),
    ], [],
     "talk 内直写 Money ⇒ 作弊面（C10 应杀）"),
    ("m31l_bar_back_to_sellable", "task-28", 0, [
        ("brain/agentfarm/farmwork.py",
         'SLOT_RELIEF_HIGH_VALUE_IDS = frozenset({\n'
         '    "535", "536", "537", "538", "749",   # Geode / Frozen / Magma / Omni Geode\n'
         '    "72",    # Diamond\n'
         '    "74",    # Prismatic Shard\n'
         "})",
         'SLOT_RELIEF_HIGH_VALUE_IDS = frozenset({\n'
         '    "535", "536", "537", "538", "749",   # Geode / Frozen / Magma / Omni Geode\n'
         '    "72",    # Diamond\n'
         '    "74",    # Prismatic Shard\n'
         '    "334",   # 变异：锭类（永不卖）塞进可卖表\n'
         "})"),
        ("brain/agentfarm/farmwork.py",
         "        if bare in SLOT_RELIEF_NEVER_SELL_IDS:\n"
         "            continue                          # 升级材料/任务相关",
         "        if False:\n"
         "            continue                          # 变异：永不卖保护关掉"),
    ], ["tests.test_longrun.TestTask28BagEvidence"],
     "锭类 334 塞进可卖表 + 拆掉永不卖守卫（双保险两处同破）⇒ 升级材料可被卖"),
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
    env.update({"PYTHONUTF8": "1", "T0746B_ROOT": str(tree),
                "T0746B_COMMIT": COMMIT, "PYTHONPATH": str(tree / "brain")})
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
        for name, card, _claimed, changes, _tests, _note in CASES:
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
        print("没有匹配的变异（用 --all 或 --only m31x）")
        return 2

    with tempfile.TemporaryDirectory(prefix="t31-mutate-") as tmp:
        work = pathlib.Path(tmp) / "work"
        _copy_tree(base, work)
        print(f"副本 = {work}")
        rc0, fails0, _out0 = _run_probe(work)
        ok0, ran0, red0, _o = _run_unittest(work, sorted({t for c in CASES for t in c[4]}))
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
            print(f"{state:10s} {name:34s} {card} 作者自报={claimed}")
        total = len(selected)
        print(f"\n合计：{killed}/{total} 条变异被杀；未杀 {survived}；异常 {total - killed - survived}")
        return 0 if survived == 0 and (total - killed - survived) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
