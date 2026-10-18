"""task-4/5/6（0.7.44 三卡）变异矩阵骨架（deputy 独立实测杀数）。

状态：**骨架**——锚点等 dev-coder 交付后按冻结树实际实现填（每卡 ≥2 条，覆盖卡面红线）。
作者自报的杀数不算证据：本脚本在冻结树的**临时副本**里做文本变异，冻结树零改动。

用法：
    python scratch/_t0744_mutate.py --base <冻结树> --check-anchors   # 锚点自检
    python scratch/_t0744_mutate.py --base <冻结树> --all             # 全跑
    python scratch/_t0744_mutate.py --base <冻结树> --only m0744a_xxx

kind:
  - probe         : 变异后跑 `scratch/_t0744_probe.py --only B,C`（数 FAIL 行增量）
  - unittest:<d>  : 变异后跑指定 unittest（数 FAIL:/ERROR:）
  - csharp        : 变异后跑 C# 自检（数 ^FAIL\\s 行）

交付后填锚点的候选语义（占位提示，不是证据）：
  task-4（换片/诚实收工）：
    a) 把"换片拿不出目标"退回 stuck（而不是 resume_exhausted/继续换片）
    b) 换片坐标不校验可执行性（拿挡死格/陈旧账本当目标）
    c) resume_exhausted 被当成 justified/no_work 放进白名单（洗白）
  task-5（挡死格不进下一轮 + leftover 拆口径）：
    d) `_stage_tiles` 不再剔除当天 blocked/encircled/unreachable 的格（重复分配）
    e) leftover 拆分字段不落账（可执行/物理挡死重新混在一起）
    f) 放宽 no_unmet_stages/护栏 B（拿豁免或 already 洗白）
  task-6（checks 快照 + 预算/浇水口径）：
    g) `slept_by_us` 仍取 stuck 之前的旧快照（sleep 成功后仍 false）
    h) 只因预算延后仍写 `watered_outdoor=true`（dry=0 同真）
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

# 已填（卡 1 / task-4，冻结树 b702708，2026-10-18）：每条 = (name, card, claimed, kind,
# [(relpath, old, new), ...], note)。判杀器 = 我方 `_t0744_probe.py` 的 B6 卡 1 独立重放。
CASES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = [
    (
        "m0744a_switch_ignores_avoid_area", "4", "无（我方自建，独立于作者 m1）", "probe",
        [("brain/agentfarm/longrun.py",
          "            rank = (0 if area != avoid_area else 1) if avoid_area else 0",
          "            rank = 0")],
        "换片不再优先『别的片』（avoid_area 失效）⇒ 又会走回同一片空转",
    ),
    (
        "m0744b_exhaust_written_as_stuck", "4", "无（我方自建，独立于作者 m2）", "probe",
        [("brain/agentfarm/longrun.py",
          '        why = (f"resume_exhausted:回片区 {len(self.resume_stall_tiles)} 格都回去看过、',
          '        why = (f"stuck:回片区 {len(self.resume_stall_tiles)} 格都回去看过、')],
        "把『真没有可执行目标』写回 stuck ⇒ 缺陷误报复发",
    ),
    (
        "m0744c_encircled_treated_as_executable", "4", "无（我方自建，独立于作者 m3）", "probe",
        [("brain/agentfarm/longrun.py",
          "        skip = set(self.resume_stall_tiles) | set(self.encircled_day)",
          "        skip = set(self.resume_stall_tiles)")],
        "被围住的格当成可执行目标 ⇒ 拿 encircled 当『他片可做』",
    ),
    (
        "m0744d_stall_not_marked", "4", "无（我方自建，独立于作者 m4）", "probe",
        [("brain/agentfarm/longrun.py",
          "        self.resume_stall_tiles |= marked",
          "        pass  # mutation: 不记停滞")],
        "回去看过没产出的邻域不记停滞 ⇒ 下一轮又走回同一片",
    ),
]
TEMPLATES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = []


def build_mutant(base: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in COPY:
        src = base / name
        if src.exists():
            shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns("__pycache__", "obj", "bin"))


def run_probe(tree: Path) -> int:
    env = dict(os.environ, T744_ROOT=str(tree), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, str(REPO / "scratch/_t0744_probe.py"), "--only", "B,C"],
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


def run_csharp(tree: Path) -> int:
    proj = tree / "mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj"
    if not proj.exists():
        return -1
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                       cwd=str(tree), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    return len(re.findall(r"^FAIL\s", out, re.M))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(REPO))
    ap.add_argument("--only")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    cases = CASES if CASES else TEMPLATES
    if args.list:
        for c in cases:
            print(c[0], c[1], c[3], c[5])
        if not cases:
            print("（锚点未填：0 条）")
        return 0
    if args.check_anchors:
        bad = 0
        for name, _card, _claimed, _kind, edits, _note in cases:
            for rel, old, _new in edits:
                text = (base / rel).read_text(encoding="utf-8", errors="replace")
                n = text.count(old)
                mark = "OK" if n == 1 else f"BAD({n})"
                if n != 1:
                    bad += 1
                print(f"[{mark}] {name} :: {rel} :: {old[:50]}")
        print(f"\n锚点：{sum(len(c[4]) for c in cases)} 条，坏 {bad} 处"
              + ("" if cases else "（待 dev-coder 交付后填；当前 0 条）"))
        return 0 if bad == 0 else 1
    sel = [c for c in cases if (args.all or (args.only and c[0] == args.only)
                                or (args.only and c[0].startswith(args.only)))]
    if not sel:
        print("没有选中的变异（用 --all / --only <name>）——锚点尚未填写（交付后填）")
        return 2
    tmp_root = Path(tempfile.mkdtemp(prefix="_t0744_mut_"))
    fails = 0
    print(f"base={base}\ntmp={tmp_root}")
    for name, card, claimed, kind, edits, note in sel:
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
            if kind == "probe":
                kills = run_probe(tree)
            elif kind.startswith("unittest:"):
                kills = run_unittest(tree, kind.split(":", 1)[1])
            elif kind == "csharp":
                kills = run_csharp(tree)
            else:
                kills = -1
            print(f"[{'KILLED' if kills > 0 else 'SURVIVED'}] {name}（card {card}）"
                  f"实测杀 {kills} / 自报 {claimed or '无'} :: {note}")
            if kills <= 0:
                fails += 1
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\n合计：{len(sel)} 条，未杀/异常 {fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
