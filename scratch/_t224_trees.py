"""task-224 B 段：按卡建 pre/post 冻结树（只写 scratch/）。

用法：
    python scratch/_t224_trees.py 218 219 220 228
每张卡建 `scratch/_t224_pre<card>`（`<commit>^`）与 `scratch/_t224_post<card>`（`<commit>`），
并从真仓库拷夹具（`logs/*.jsonl`、`logs/*.json`、`scratch/_ledger_*.jsonl`、`scratch/_t5x_vacuum*.jsonl`），
否则 analyzer 相关用例在无 gitignore 目录的树里会 FileNotFoundError。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = REPO / "scratch"

CA = {
    "218": "b679f4e",
    "219": "fc147a7",
    "220": "19b2827",
    "222": "7f030c2",
    "228": "3dc4b1e",
    "230": "1e96509",
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def fixtures(dst: Path) -> int:
    n = 0
    for sub, pats in (("logs", ("*.jsonl", "*.json")), ("scratch", ("_ledger_*.jsonl", "_t5x_vacuum*.jsonl"))):
        src = REPO / sub
        if not src.is_dir():
            continue
        for pat in pats:
            for p in src.glob(pat):
                (dst / sub).mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst / sub / p.name)
                n += 1
    return n


def build(rev: str, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEMP")) as td:
        tar = Path(td) / "t.tar"
        subprocess.run(["git", "archive", "--format=tar", "-o", str(tar), rev],
                       cwd=REPO, check=True)
        with tarfile.open(tar) as tf:
            tf.extractall(dst)
    fixt = fixtures(dst)
    print(f"  {dst.name}: {sum(1 for _ in dst.rglob('*'))} 项（夹具 {fixt}）")


def main(argv: list[str]) -> int:
    cards = argv or ["218", "219", "220", "228"]
    for card in cards:
        commit = CA[card]
        parent = git("rev-parse", f"{commit}^")
        print(f"[card {card}] {commit}（父 {parent[:8]}）")
        build(parent, SCRATCH / f"_t224_pre{card}")
        build(commit, SCRATCH / f"_t224_post{card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
