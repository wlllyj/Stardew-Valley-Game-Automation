r"""task-200：为 0.7.37 批次构造**冻结快照树**（pre/post），供探针用 `T200_ROOT` 切换。

为什么必须用快照：在制工作树会移动（task-185 的教训），验收对象必须是不可变的树。

用法（在仓库根、pwsh）：
  & $py scratch\_t200_trees.py --card 198          # 找最近的 task-198 提交 ⇒ 建 _t200_pre198 / _t200_post198
  & $py scratch\_t200_trees.py --rev <sha> --name _t200_base
  & $py scratch\_t200_trees.py --markers            # 只报当前工作树的 marker 状态

纪律：只写 `scratch/`；`git archive`/`tar` 一律用**相对路径**（tar.exe 打不开含中文的绝对路径）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
SCRATCH = WS / "scratch"

# 每张卡在树里的"特性指纹"（文件, 子串）。pre 树应全为 False，post 树应全为 True。
MARKERS: dict[str, list[tuple[str, str]]] = {
    "198": [("brain/agentfarm/farmwork.py", "no_slot"),
            ("brain/agentfarm/farmwork.py", "slot_relief"),
            ("brain/agentfarm/longrun.py", "inventory_blocked")],
    "199": [("mod/AgentFarm.Bridge/FarmScan.cs", "readyTiles"),
            ("mod/AgentFarm.Bridge/Contracts.cs", "readyTiles"),
            ("brain/agentfarm/farmwork.py", "ready_far_blocked")],
    "195": [("mod/AgentFarm.Bridge/ClumpRules.cs", "Target"),
            ("mod/AgentFarm.Bridge/Skills.cs", "Affected")],
    "196": [("brain/agentfarm/farmwork.py", "collateral_loot")],
    "197": [("tests/test_longrun.py", 'encoding="utf-8"')],
}
CARD_ORDER = ["198", "199", "195", "196", "197"]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=WS, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def card_commit(card: str) -> str:
    r = git("log", "-1", "--format=%H", "--grep", f"task-{card}", "HEAD")
    sha = (r.stdout or "").strip()
    if not sha:
        raise SystemExit(f"找不到含 'task-{card}' 的提交（可能还没交付）")
    return sha


def markers_in(root: Path) -> dict[str, dict[str, bool]]:
    out: dict[str, dict[str, bool]] = {}
    for card, pairs in MARKERS.items():
        res = {}
        for rel, needle in pairs:
            p = root / rel
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                res[f"{rel}::{needle}"] = False
                continue
            res[f"{rel}::{needle}"] = needle in txt
        out[card] = res
    return out


def build(rev: str, name: str) -> Path:
    dest = SCRATCH / name
    tarp = SCRATCH / f"{name}.tar"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    r = git("archive", "--format=tar", "-o", str(tarp.relative_to(WS)), rev)
    if r.returncode != 0:
        raise SystemExit(f"git archive 失败：{(r.stderr or '').strip()[:300]}")
    # tar.exe 对含中文的绝对路径不可靠 ⇒ 用相对路径 + cwd
    r2 = subprocess.run(["tar", "-xf", str(tarp.relative_to(WS)), "-C", str(dest.relative_to(WS))],
                        cwd=WS, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r2.returncode != 0:
        raise SystemExit(f"tar 解包失败：{(r2.stderr or '').strip()[:300]}")
    tarp.unlink(missing_ok=True)
    n = sum(1 for _ in dest.rglob("*") if _.is_file())
    print(f"[OK] {name} ← {rev[:12]}（{n} 文件）")
    return dest


def report_markers(root: Path, tag: str) -> None:
    print(f"\n-- {tag}（{root.name}）marker 指纹 --")
    m = markers_in(root)
    for card in CARD_ORDER:
        hits = m[card]
        got = sum(1 for v in hits.values() if v)
        print(f"  task-{card}: {got}/{len(hits)} 命中")
        for k, v in hits.items():
            if not v:
                print(f"     缺: {k}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", help="卡号（198/199/195/196/197）⇒ 建 pre/post 两棵树")
    ap.add_argument("--rev", help="直接给提交")
    ap.add_argument("--name", help="树名（配合 --rev）")
    ap.add_argument("--markers", action="store_true", help="只报当前工作树 marker")
    a = ap.parse_args()
    SCRATCH.mkdir(exist_ok=True)
    if a.markers:
        report_markers(WS, "工作树")
        return 0
    if a.card:
        for c in a.card.split(","):
            c = c.strip()
            sha = card_commit(c)
            pre = build(f"{sha}^", f"_t200_pre{c}")
            post = build(sha, f"_t200_post{c}")
            print(f"  提交 {c} = {sha[:12]}")
            report_markers(pre, f"pre{c}")
            report_markers(post, f"post{c}")
        return 0
    if a.rev and a.name:
        report_markers(build(a.rev, a.name), a.name)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
