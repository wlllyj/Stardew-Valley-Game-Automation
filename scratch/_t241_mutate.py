# -*- coding: utf-8 -*-
"""【task-241】季节感知买种子的变异实测装置（在 `git archive HEAD` 冻结树上复跑）。

用法（必须 DSH python + PYTHONUTF8=1；跑之前 T-2 的修复+测试必须已落库，
否则冻结树上没有被测对象）：
  $env:PYTHONUTF8="1"; & <DSH python> "scratch\\_t241_mutate.py"

变异对象 = `brain/agentfarm/longrun.py` 里 task-241 的「季节感知选品」三处：
  ① 冬季早退闸门（`if season == "winter": ... return changed`）；
  ② 跨季残留货架失效（捕获季节不符即丢弃，强制重探当季新鲜货架）；
  ③ 冬季诚实信号（`seed_dead_today = "winter_no_seeds"`）。
每条变异把被钉住的行为改坏一项，`tests.test_longrun.TestTask241SeasonAwareSeedBuy`
必须至少一条用例变红。锚点命中数 != 期望值 ⇒ ADAPTER-ERROR（**不当 PASS**）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")

#: ① 冬季早退闸门（当前工作树/冻结树里必须**恰好命中 1 次**）
WINTER_GATE = '        if season == "winter":'
#: ② 跨季残留货架失效（恰好命中 1 次）
STALE_GUARD = (
    '            if self.shop_offers_season and self.shop_offers_season != season:\n'
    '                self.shop_offers = []\n'
    '                self.shop_offers_season = ""'
)
#: ③ 冬季诚实信号（恰好命中 1 次）
WINTER_SIGNAL = '            self.seed_dead_today = "winter_no_seeds"'

# (名字, 原文, 变异后, 为什么改坏, 期望命中数, [定向用例模块...])
MUTANTS = [
    (
        "M1_winter_gate_off",
        WINTER_GATE,
        '        if False:  # MUTANT: 关掉冬季早退 ⇒ 冬季落到探/买逻辑',
        "冬季不再早退 ⇒ 冬季会拿春种 472 去探/买（run6 那种白撞 item_not_sold）",
        1,
        ["tests.test_longrun.TestTask241SeasonAwareSeedBuy"],
    ),
    (
        "M2_stale_shelf_kept",
        STALE_GUARD,
        '            pass  # MUTANT: 不丢弃跨季残留货架 ⇒ 直接拿上季清单买隔季种',
        "跨季残留货架不失效 ⇒ 春末 Parsnip 清单在夏初被直接买（item_not_sold）",
        1,
        ["tests.test_longrun.TestTask241SeasonAwareSeedBuy"],
    ),
    (
        "M3_winter_signal_wrong",
        WINTER_SIGNAL,
        '            self.seed_dead_today = "no_seed_for_sale"  # MUTANT: 冬季信号不诚实',
        "冬季信号写成 no_seed_for_sale ⇒ 账本无法区分『冬季无种』与『真买不到』",
        1,
        ["tests.test_longrun.TestTask241SeasonAwareSeedBuy"],
    ),
]

TARGET = "brain/agentfarm/longrun.py"
COUNT_RE = re.compile(r"Ran (\d+) tests?")
BAD_RE = re.compile(r"^(?:FAIL|ERROR): ", re.M)


def run_tests(tree: Path, mods: list[str]):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    p = subprocess.run([PY, "-m", "unittest", *mods],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    m = COUNT_RE.search(out)
    ran = int(m.group(1)) if m else -1
    failed = len(BAD_RE.findall(out))
    ok = bool(re.search(r"^OK\b", out, re.M))
    return ran, failed, ok, out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="t241_"))
    tree = tmp / "tree"
    tree.mkdir()
    tar = tmp / "frozen.tar"
    subprocess.run(["git", "archive", "--format=tar", "HEAD", "-o", str(tar)],
                   cwd=str(REPO), check=True)
    with tarfile.open(tar) as tf:
        tf.extractall(tree)
    print(f"[tree] {tree}（git archive HEAD）")

    f = tree / TARGET
    src = f.read_text(encoding="utf-8")
    anchors = [(WINTER_GATE, 1), (STALE_GUARD, 1), (WINTER_SIGNAL, 1)]
    bad = False
    for a, want in anchors:
        if src.count(a) != want:
            print(f"!! 锚点命中 {src.count(a)} 次（期望 {want}）——先落库 T-2 再跑本装置")
            bad = True
    if bad:
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    mods = sorted({m for *_, ms in MUTANTS for m in ms})
    ran, failed, ok, out = run_tests(tree, mods)
    print(f"[baseline] Ran {ran} / failed={failed} / OK={ok}")
    if not ok:
        print(out[-4000:])
        print("!! 冻结树基线不是绿的 —— 装置不可信，中止")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    results = []
    for name, old, new, why, want, ms in MUTANTS:
        n = src.count(old)
        if n != want:
            results.append((name, "ADAPTER-ERROR", f"锚点命中 {n} 次（期望 {want}）", 0, 0))
            print(f"[{name}] ADAPTER-ERROR 锚点命中 {n} 次（期望 {want}）")
            continue
        f.write_text(src.replace(old, new), encoding="utf-8", newline="")
        try:
            ran, failed, ok, out = run_tests(tree, ms)
        finally:
            f.write_text(src, encoding="utf-8", newline="")
        verdict = "KILL" if (failed > 0 or not ok) else "ALIVE(测试没盯住!)"
        results.append((name, verdict, f"Ran {ran} failed={failed}", failed, ran))
        print(f"[{name}] {verdict}  Ran={ran} failed={failed}  （{why}）")
        if verdict.startswith("ALIVE") or ran == -1:
            print(out[-2500:])

    print("\n================ 变异实测汇总（task-241） ================")
    for name, verdict, detail, failed, ran in results:
        print(f"{verdict:14s} {name:20s} {detail}")
    killed = sum(1 for _, v, _, _, _ in results if v == "KILL")
    print(f"杀数 = {killed} / {len(results)}")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
