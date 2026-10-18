#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""【0.7.46 / task-31 预热】冻结树提取 + provenance 对照（独立实现）。

用途：给任意 commit 建一份"与 git archive 等价"的临时树，并做两件事：
  1) 全量：`git ls-tree -r` 的 tracked 文件数 vs 解压文件数；逐 blob sha1 对照
     （CRLF 归一：.ps1/.bat/.cmd，以及含 \r\n 的文本，按 LF 计算）；
  2) 关键清单：8 个关键文件逐个 `git hash-object`（按归一后的内容）vs
     `git rev-parse <commit>:<path>`；另自动列出 `tests/_mutate_*.py`。

用法（所有 Python 命令必须 PYTHONUTF8=1）：
  python scratch/_t0746_prep_prov.py --commit HEAD
  python scratch/_t0746_prep_prov.py --commit 2feb1f8 --dest %TEMP%\t0746_prep_x --keep

判据：tracked==解压、逐 blob 不符 0、关键 8/8 相等 ⇒ rc=0；否则 rc=1。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

KEY_FILES = [
    "brain/agentfarm/longrun.py",
    "brain/agentfarm/farmwork.py",
    "brain/agentfarm/bridge.py",
    "tests/test_longrun.py",
    "mod/AgentFarm.Bridge/manifest.json",
    "tests/_mutate_t15_justified.py",
    "tests/_mutate_t16_inventory.py",
    "tests/_mutate_t22_malformed.py",
]


def git(*args: str, data: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", *args], cwd=str(REPO), input=data, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{proc.stderr.decode('utf-8', 'replace')[:400]}")
    return proc.stdout


def norm(data: bytes) -> bytes:
    """文本按 LF 归一后再算 sha1；二进制保持原样。"""
    if b"\x00" in data[:4096]:
        return data
    return data.replace(b"\r\n", b"\n")


def blob_sha(data: bytes) -> str:
    body = norm(data)
    h = hashlib.sha1()
    h.update(f"blob {len(body)}\0".encode())
    h.update(body)
    return h.hexdigest()


def parse_ls_tree(commit: str) -> dict[str, str]:
    out = git("ls-tree", "-r", "-z", commit)
    items = [x for x in out.split(b"\0") if x]
    table: dict[str, str] = {}
    for it in items:
        meta, _, path = it.partition(b"\t")
        mode, typ, sha = meta.split(b" ")
        if typ != b"blob":
            continue
        table[path.decode("utf-8", "replace")] = sha.decode()
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--dest", default="")
    ap.add_argument("--keep", action="store_true", help="保留解压目录（默认临时目录会被删）")
    args = ap.parse_args()

    commit = git("rev-parse", args.commit).decode().strip()
    short = commit[:8]
    tracked = parse_ls_tree(commit)

    tmp_ctx = None
    if args.dest:
        dest = Path(args.dest).expanduser()
        if dest.exists():
            raise SystemExit(f"目标已存在：{dest}")
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix=f"t0746_prep_{short}-")
        dest = Path(tmp_ctx.name) / "tree"
    dest.mkdir(parents=True, exist_ok=False)

    tar_bytes = git("archive", "--format=tar", commit)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        tar.extractall(dest, filter="data")

    files = sorted(p for p in dest.rglob("*") if p.is_file())
    print(f"== 0.7.46 预热 provenance == commit={commit} dest={dest}")
    print(f"tracked(blob)={len(tracked)}  extracted={len(files)}")

    missing, mismatch = [], []
    for rel, want in tracked.items():
        p = dest / rel
        if not p.is_file():
            missing.append(rel)
            continue
        got = blob_sha(p.read_bytes())
        if got != want:
            mismatch.append((rel, want, got))
    print(f"missing={len(missing)} mismatch={len(mismatch)}")
    for rel in missing[:10]:
        print(f"  MISS {rel}")
    for rel, want, got in mismatch[:10]:
        print(f"  DIFF {rel} want={want[:12]} got={got[:12]}")

    print("\n== 关键文件（8）")
    key_ok = 0
    for rel in KEY_FILES:
        p = dest / rel
        if not p.is_file():
            print(f"  MISS {rel}")
            continue
        want = git("rev-parse", f"{commit}:{rel}").decode().strip()
        got = blob_sha(p.read_bytes())
        ok = want == got
        key_ok += int(ok)
        print(f"  {'OK ' if ok else 'BAD'} {rel} want={want[:12]} got={got[:12]}")
    print(f"关键 8：{key_ok}/8")

    muts = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("tests/_mutate_*.py"))
    print(f"\n== 变异脚本（自动列出）：{len(muts)}")
    for m in muts:
        print("  ", m)

    rc = 0 if (not missing and not mismatch and key_ok == len(KEY_FILES)) else 1
    print(f"\n判定：{'PASS' if rc == 0 else 'FAIL'}（tracked==extracted、逐 blob 不符 0、关键 8/8）")
    if args.keep and not args.dest:
        print(f"（--keep 但未给 --dest，临时目录仍会删除）")
    if tmp_ctx is not None:
        if args.keep:
            tmp_ctx.cleanup = lambda: None  # type: ignore[method-assign]
            print(f"临时目录保留：{dest}")
        else:
            tmp_ctx.cleanup()
    return rc


if __name__ == "__main__":
    sys.exit(main())
