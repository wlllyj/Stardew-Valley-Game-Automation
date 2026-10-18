"""task-23（0.7.45 合并回归：task-15 + task-16 + task-22）变异矩阵 —— deputy 独立实测杀数。

作者自报的 4/4、5/5、3/3 不算证据：本脚本在**冻结树临时副本**里做文本变异，冻结树零改动；
判杀器 = 我方 `scratch/_t0745b_probe.py` 的 B/C 段独立重放 + 作者三张卡的定向单测
（任一红即算杀死；报告两列并列，不把作者单测当唯一判据）。

用法：
    python scratch/_t0745b_mutate.py --base <冻结树> --check-anchors
    python scratch/_t0745b_mutate.py --base <冻结树> --all
    python scratch/_t0745b_mutate.py --base <冻结树> --only m23a
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
UNITTESTS = (
    "tests.test_longrun.TestTask15PendingCaliber",
    "tests.test_longrun.TestTask16InventoryFull",
    "tests.test_longrun.TestTask22MalformedTiles",
)

# 每条 = (name, card, claimed, kind, [(relpath, old, new), ...], note)
CASES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = [
    (
        "m23a_malformed_veto_removed", "22", "作者 m3（同点位、我方独立实现）", "probe",
        [("brain/agentfarm/longrun.py",
          "    if int(malformed_tiles) > 0:\n        return False",
          "    if False:\n        return False")],
        "malformed 一票否决被关掉 ⇒ 残客观测（NIT-1 原形）仍可被 day_justified 洗白",
    ),
    (
        "m23b_malformed_back_to_unobserved", "22", "作者 m1（同点位）", "probe",
        [("brain/agentfarm/longrun.py",
          '            if not tv.get("crop") and not kind and t not in tillable:\n'
          '                malformed += 1\n'
          '                continue',
          '            if False:\n'
          '                malformed += 1\n'
          '                continue')],
        "残缺记录改回 unobserved ⇒ exec=0 ⇒ fail-open 复活",
    ),
    (
        "m23c_honest_threshold_opened", "15", "无（我方自建，独立于作者 m1/m3）", "probe",
        [("brain/agentfarm/longrun.py",
          "        return pending_executable is not None and int(pending_executable) == 0",
          "        return True")],
        "resume_exhausted 收工不查可执行面证据 ⇒ 旧账直接洗成 day_justified",
    ),
    (
        "m23d_obs_missing_fail_open", "22", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          '            return {**base, "executable": len(guard_tiles), "unobserved": 0, "malformed": 0}',
          '            return {**base, "executable": 0, "unobserved": 0, "malformed": 0}')],
        "整张观测缺失时把「没看到」当「没有」 ⇒ fail-closed 被反转",
    ),
    (
        "m23e_clear_loot_detection_off", "16", "作者 m2（同点位）", "probe",
        [("brain/agentfarm/farmwork.py",
          'loot_risk = free_status0 == "ok" and int(free0) <= 0',
          'loot_risk = False')],
        "满包清障不再留 loot_lost ⇒ 掉落被吞、账本看不见",
    ),
    (
        "m23f_free_slots_uses_capacity", "16", "作者 m1（同点位）", "probe",
        [("brain/agentfarm/farmwork.py",
          'return max(0, int(cap) - len(inv)), "ok"',
          'return max(0, int(cap)), "ok"')],
        "空格口径不看已用格 ⇒ 永远「有空」⇒ 满包/腾格链路失效",
    ),
    (
        "m23g_pressure_channel_off", "16", "作者 m3（同点位）", "probe",
        [("brain/agentfarm/longrun.py",
          "        if need <= 0 and not space_pressure:",
          "        if need <= 0:")],
        "压力腾格通道被关 ⇒ 空格=0 但需求=0 时不再自救",
    ),
    (
        "m23h_buy_before_free_off", "16", "作者 m5（同点位）", "probe",
        [("brain/agentfarm/longrun.py",
          '        if fs_status == "ok" and int(free_slots) < 1:\n'
          '            if (seeds_total == 0 and money >= self.seed_price',
          '        if False:\n'
          '            if (seeds_total == 0 and money >= self.seed_price')],
        "买种前不腾格 ⇒ 满包买种失败被当普通失败（task-16 倒退）",
    ),
    (
        "m23i_checks_payload_polluted", "15/16/22", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          "        rep.checks = {\n",
          '        rep.checks = {\n            "pending_malformed": int(rep.pending_malformed),\n')],
        "新字段塞进 checks ⇒ 10 键语义被污染（A9 判定面被改写）",
    ),
    (
        "m23j_malformed_evidence_dropped", "22", "无（我方自建）", "probe",
        [("brain/agentfarm/longrun.py",
          "                pending_executable=rep.pending_executable,\n"
          "                malformed_tiles=rep.pending_malformed),",
          "                pending_executable=rep.pending_executable,\n"
          "                malformed_tiles=0),")],
        "day_justified 不把 malformed 证据交给判据 ⇒ 一票否决在调用点被绕过",
    ),
    (
        "m23k_burst_back_to_stuck_text", "15", "作者 m4（新锚点；原脚本锚点已随 task-22 过期）", "probe",
        [("brain/agentfarm/longrun.py",
          "                        self._resume_exhausted(\n"
          "                            obs, rep, plot=self._resume_plot(obs),\n"
          '                            where="plot_exhausted_burst")',
          '                        self._do_sleep(obs, rep, "stuck:变异 burst 收尾")')],
        "冬26 同秒 burst 收尾改回 stuck: 文案 ⇒ 有界 ≠ 可放行被破坏（0.7.44 形态）",
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
    env = dict(os.environ, T0745B_ROOT=str(tree), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, str(REPO / "scratch/_t0745b_probe.py"), "--only", "B,C"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=1200)
    return sum(1 for ln in r.stdout.splitlines() if "  FAIL " in ln)


def run_unittest(tree: Path) -> int:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=str(tree / "brain"))
    fails = 0
    for dotted in UNITTESTS:
        r = subprocess.run([PY, "-m", "unittest", dotted], cwd=str(tree),
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=900)
        out = (r.stdout or "") + (r.stderr or "")
        fails += len(re.findall(r"^(FAIL|ERROR):", out, re.M))
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(REPO))
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--list", action="store_true")
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
                print(f"[{'OK' if n == 1 else f'BAD({n})'}] {name} :: {rel} :: {old[:40]!r}")
        print(f"\n锚点：{sum(len(c[4]) for c in CASES)} 条，坏 {bad} 处")
        return 0 if bad == 0 else 1
    sel = [c for c in CASES if (args.all or (args.only and c[0].startswith(args.only)))]
    if not sel:
        print("没有选中的变异（用 --all / --only <name>）")
        return 2
    base_probe = run_probe(base)
    base_unit = run_unittest(base)
    base_ok = base_probe == 0 and base_unit == 0
    print(f"base={base}\n基线自检：probe FAIL={base_probe} unittest FAIL/ERROR={base_unit}"
          f" ⇒ {'OK' if base_ok else '基线不绿，终止'}")
    if not base_ok:
        return 3
    tmp_root = Path(tempfile.mkdtemp(prefix="_t0745b_mut_"))
    fails = 0
    for name, card, claimed, _kind, edits, note in sel:
        tree = tmp_root / name
        build_mutant(base, tree)
        anchor_bad = False
        for rel, old, new in edits:
            p = tree / rel
            text = p.read_text(encoding="utf-8", errors="replace")
            if text.count(old) != 1:
                print(f"[ANCHOR-FAIL] {name} :: {rel}")
                fails += 1
                anchor_bad = True
                break
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
        if anchor_bad:
            continue
        probe_kills = run_probe(tree)
        unit_kills = run_unittest(tree)
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
