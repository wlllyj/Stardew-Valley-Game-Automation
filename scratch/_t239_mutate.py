"""task-239 变异矩阵：实测作者自报杀数（0.7.41 的 236/237；238 待落地后补）。

做法（照前几批）：
- 从 `--base`（默认本仓库工作树；正式验收必须给 `git archive` 冻结树）拷出
  `brain/ tools/ tests/ mod/ scratch/save-chain-check.py` 到 `%TEMP%/_t239_mut/<case>`；
- 每条变异做**纯文本替换**，锚点必须**恰好命中 1 次**（否则该 case 记 ERROR）；
- 跑 `scratch/_t239_probe.py --tree <变异树> --only C`，数 `  FAIL  ` 行数 = 杀条数；
- control 先跑（期望 0 杀），任何变异杀数 ≥1 记 KILLED，否则记为"未杀（GAP）"。

用法：
    python scratch/_t239_mutate.py --list
    python scratch/_t239_mutate.py --check-anchors --base <冻结树>
    python scratch/_t239_mutate.py --all --base <冻结树>
    python scratch/_t239_mutate.py --only m236b_no_event_guard --base <冻结树>
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PROBE = HERE / "_t239_probe.py"
PY = sys.executable
COPY_DIRS = ["brain", "tools", "tests", "mod"]
COPY_FILES = ["scratch/save-chain-check.py"]

# (name, card, claimed(作者自报，None=无自报), edits[(rel, old, new)], note)
CASES: list[dict] = [
    dict(name="m236a_no_cleanup_call", card="236", claimed=None,
         edits=[("brain/agentfarm/longrun.py",
                 "        cleanup = self._cleanup_modals_before_finish()\n",
                 '        cleanup = {"attempts": 0, "menu": None, "stuck": False}\n')],
         note="收尾守卫整个不调（finish 前不关框）"),
    dict(name="m236b_no_event_guard", card="236", claimed=None,
         edits=[("brain/agentfarm/longrun.py",
                 '            if ui.get("eventUp") is True:\n                result["skipped"] = "event_up"\n',
                 '            if False and ui.get("eventUp") is True:  # noqa\n                result["skipped"] = "event_up"\n')],
         note="去掉收尾路径的 eventUp 守卫 ⇒ 会去关事件对话"),
    dict(name="m236c_no_profession_guard", card="236", claimed=None,
         edits=[("brain/agentfarm/longrun.py",
                 '            if menu == "LevelUpMenu":\n                pending = ui.get("professionsToChoose")\n',
                 '            if False and menu == "LevelUpMenu":  # noqa\n                pending = ui.get("professionsToChoose")\n')],
         note="去掉收尾路径的职业选择守卫 ⇒ 会关掉 LevelUpMenu"),
    dict(name="m236d_wait_only_dismiss", card="236", claimed=None,
         edits=[("brain/agentfarm/longrun.py",
                 '            if menu in MODAL_WAIT_ONLY:\n                obs, gone, waited = self._wait_modal_gone(menu, obs)\n                self._journal("modal_dismissed", kind="cleanup_wait"',
                 '            if False and menu in MODAL_WAIT_ONLY:  # noqa\n                obs, gone, waited = self._wait_modal_gone(menu, obs)\n                self._journal("modal_dismissed", kind="cleanup_wait"')],
         note="存档菜单也 dismiss（会打断保存链）"),
    dict(name="m237a_no_demand_clamp", card="237", claimed=None,
         edits=[("brain/agentfarm/longrun.py",
                 "        demand = max(0, min(int(HARVEST_DEMAND_CAP), int(demand)))\n",
                 "        demand = max(0, int(demand))\n")],
         note="去掉需求上界钳制（demand 可无限大）"),
]


def _copy_base(base: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for d in COPY_DIRS:
        src = base / d
        if src.is_dir():
            shutil.copytree(src, dest / d,
                            ignore=shutil.ignore_patterns("__pycache__", "bin", "obj", "*.pyc"))
    for f in COPY_FILES:
        src = base / f
        if src.is_file():
            (dest / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / f)


def _apply(mut: Path, edits: list[tuple[str, str, str]]) -> None:
    for rel, old, new in edits:
        p = mut / rel
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"锚点 {rel} 命中 {n} 次（要求恰好 1 次）：{old!r}")
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _count_kills(tree: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    p = subprocess.run([PY, str(PROBE), "--tree", str(tree), "--only", "C"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(REPO), env=env, timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    kills = sum(1 for ln in out.splitlines() if ln.startswith("  FAIL  "))
    return kills, out


def run_case(base: Path, case: dict, root: Path) -> tuple[str, int, int]:
    name = case["name"]
    mut = root / name
    if mut.exists():
        shutil.rmtree(mut, ignore_errors=True)
    try:
        _copy_base(base, mut)
        _apply(mut, case["edits"])
    except SystemExit as exc:
        print(f"[ANCHOR] {name}: {exc}")
        return ("ANCHOR", -1, case.get("claimed") or -1)
    kills, out = _count_kills(mut)
    status = "KILLED" if kills > 0 else "MISSED"
    claimed = case.get("claimed")
    kc = f"{claimed}" if claimed is not None else "无自报"
    print(f"[{status}] {name}（card {case['card']}）实测杀 {kills} / 自报 {kc} :: {case['note']}")
    (HERE / f"_t239_mut_{name}.txt").write_text(out, encoding="utf-8", newline="\n")
    return (status, kills, claimed if claimed is not None else -1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(REPO))
    ap.add_argument("--only", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if args.list:
        for c in CASES:
            print(f"{c['name']}\tcard={c['card']}\tclaimed={c.get('claimed')}\t{c['note']}")
        return 0
    if args.check_anchors:
        bad = 0
        for c in CASES:
            for rel, old, _new in c["edits"]:
                try:
                    n = (base / rel).read_text(encoding="utf-8").count(old)
                except OSError:
                    n = 0
                flag = "OK" if n == 1 else f"BAD({n})"
                if n != 1:
                    bad += 1
                print(f"[{flag}] {c['name']} :: {rel} :: {old.strip()[:60]}")
        print(f"\n锚点：{len(CASES)} 条变异，坏 {bad} 处")
        return 1 if bad else 0
    chosen = [c for c in CASES if args.all or not args.only or c["name"] == args.only]
    if args.only and not chosen:
        print("没有匹配的变异名"); return 1
    root = Path(tempfile.gettempdir()) / "_t239_mut"
    root.mkdir(parents=True, exist_ok=True)
    print(f"base={base}\ntmp={root}")
    try:
        ctrl_kills, ctrl_out = _count_kills(base)
        print(f"[CONTROL] 基线杀 {ctrl_kills}（必须 0）")
        (HERE / "_t239_mut_control.txt").write_text(ctrl_out, encoding="utf-8", newline="\n")
        results = []
        for c in chosen:
            results.append(run_case(base, c, root))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 2
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
    missed = [n for n, st, _k, _c in [(c["name"], *r) for c, r in zip(chosen, results)] if st != "KILLED"]
    print(f"\n合计：{len(chosen)} 条，杀 {sum(1 for _n, st, _k, _c in [(c['name'], *r) for c, r in zip(chosen, results)] if st == 'KILLED')}，未杀/异常 {len(missed)}")
    for m in missed:
        print("  未杀/异常：", m)
    return 0 if not missed and ctrl_kills == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
