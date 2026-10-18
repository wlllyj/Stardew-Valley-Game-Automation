"""task-244 变异矩阵骨架（task-242 交付后填锚点）。

用法：
    python scratch/_t244_mutate.py --base <树> --check-anchors
    python scratch/_t244_mutate.py --base <树> --all
    python scratch/_t244_mutate.py --base <树> --only m242a_xxx

kind:
  - probe        : 变异后跑 `scratch/_t244_probe.py`（数 FAIL 行增量）
  - unittest:<d> : 变异后跑指定 unittest（数 FAIL:/ERROR:）
  - csharp       : 变异后跑 C# 自检（数 ^FAIL\\s 行）
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
COPY = ("brain", "tests", "mod")

# 交付后按实际实现填：每条 = (name, card, claimed, kind, [(relpath, old, new), ...], note)
CASES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = []

TEMPLATES: list[tuple[str, str, str | None, str, list[tuple[str, str, str]], str]] = [
    (
        "m244a_already_counted_as_ok", "242", "作者 m242a 等价", "probe",
        [("brain/agentfarm/longrun.py",
          """            oks = [s for s in ok_all
                   if str(getattr(s, "code", "") or "") != "already"]""",
          """            oks = ok_all""")],
        "把 already 步重新算回 ok（修前形态）",
    ),
    (
        "m244b_unclear_not_recorded", "242", "无（自建）", "probe",
        [("brain/agentfarm/longrun.py", '"unclear": unclear_steps,', '"unclear": 0,')],
        "把 kind 不可判的 ok 步从账本里抹掉（差额重新无痕）",
    ),
    (
        "m244c_already_cause_always_neighbor", "242", "作者 m242d 等价", "probe",
        [("brain/agentfarm/longrun.py",
          'bucket = "cleared_by_neighbor" if key in neighbor_open else "no_target"',
          'bucket = "cleared_by_neighbor"')],
        "already 归因全塞 cleared_by_neighbor（no_target 丢失）",
    ),
    (
        "m244d_ok_tiles_drops_already", "242", "作者 m242c 等价", "probe",
        [("brain/agentfarm/longrun.py",
          "ok_tiles_set = {tuple(s.tile) for s in ok_all if s.tile} & assigned_set",
          "ok_tiles_set = {tuple(s.tile) for s in oks if s.tile} & assigned_set")],
        "瓦片级 ok_tiles 丢掉 already 格（该格掉进 unexecuted）",
    ),
    (
        "m244e_attempted_ok_zero", "242", "无（自建）", "probe",
        [("brain/agentfarm/longrun.py", '"attempted_ok": len(already_steps),',
          '"attempted_ok": 0,')],
        "attempted_ok 不再反映 already 步数（口径自相矛盾）",
    ),
]


def build_mutant(base: Path, dest: Path, edits: list[tuple[str, str, str]]) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in COPY:
        src = base / name
        if src.exists():
            shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns("__pycache__", "obj", "bin"))


def run_probe(tree: Path) -> int:
    env = dict(os.environ, T244_ROOT=str(tree), PYTHONUTF8="1")
    r = subprocess.run([PY, str(REPO / "scratch/_t244_probe.py"), "--only", "B,C"],
                       capture_output=True, text=True, env=env, timeout=900)
    return sum(1 for ln in r.stdout.splitlines() if "  FAIL  " in ln)


def run_unittest(tree: Path, dotted: str) -> int:
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([PY, "-m", "unittest", dotted], cwd=str(tree),
                       capture_output=True, text=True, env=env, timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    return len(re.findall(r"^(FAIL|ERROR):", out, re.M))


def run_csharp(tree: Path) -> int:
    proj = tree / "mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj"
    if not proj.exists():
        return -1
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                       cwd=str(tree), capture_output=True, text=True, env=env, timeout=900)
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
        print(f"\n锚点：{sum(len(c[4]) for c in cases)} 条，坏 {bad} 处")
        return 0 if bad == 0 else 1
    sel = [c for c in cases if (args.all or (args.only and c[0] == args.only)
                                or (args.only and c[0].startswith(args.only)))]
    if not sel:
        print("没有选中的变异（用 --all / --only <name>）")
        return 2
    tmp_root = Path(tempfile.mkdtemp(prefix="_t244_mut_"))
    fails = 0
    print(f"base={base}\ntmp={tmp_root}")
    for name, card, claimed, kind, edits, note in sel:
        tree = tmp_root / name
        build_mutant(base, tree, edits)
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
            print(f"[{'KILLED' if kills > 0 else 'SURVIVED'}] {name}（card {card}）实测杀 {kills} / 自报 {claimed or '无'} :: {note}")
            if kills <= 0:
                fails += 1
    shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"\n合计：{len(sel)} 条，未杀/异常 {fails}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
