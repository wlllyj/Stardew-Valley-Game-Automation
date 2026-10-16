# -*- coding: utf-8 -*-
"""run B 起跑前三步（只读 + 一次字节拷贝）：
1) 汇报 A 的起止外部快照（不重复追加 end 行）
2) 原样拷贝 logs\\longrun-runA-0732-lessons.json → logs\\longrun-runB-0732-lessons.json（记两侧 size/mtime/SHA256）
3) 核对五个源文件 SHA256 与 A 的 sidecar 是否逐字一致（任一不同 ⇒ 退出码 3，停手）
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SNAP_A = os.path.join(ROOT, "scratch", "runA-0732-external-snapshots.jsonl")
SIDE_A = os.path.join(ROOT, "logs", "longrun-runA-0732.version.json")
LESSONS_A = os.path.join(ROOT, "logs", "longrun-runA-0732-lessons.json")
LESSONS_B = os.path.join(ROOT, "logs", "longrun-runB-0732-lessons.json")


def sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest().upper()


def stat_line(p: str) -> str:
    st = os.stat(p)
    return f"{st.st_size} B / mtime {time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(st.st_mtime))} / SHA256 {sha256(p)}"


print("=== 1) A 的起止外部快照（不重复追加）===")
with open(SNAP_A, encoding="utf-8") as fh:
    for i, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        print(f"  行{i}: tag={o.get('tag')} at={o.get('at')} save_main={o.get('save_main')} / {o.get('save_main_mtime')} "
              f"pid={o.get('pid')} pid_alive={o.get('pid_alive')} mod_version_matches={o.get('mod_version_matches')}")

print("\n=== 2) 拷贝教训库（原样字节拷贝）===")
if os.path.exists(LESSONS_B):
    print(f"⚠ 目标已存在，先停手报告：{LESSONS_B}（{stat_line(LESSONS_B)}）")
    sys.exit(4)
print(f"源   {LESSONS_A}\n     {stat_line(LESSONS_A)}")
copied_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
shutil.copyfile(LESSONS_A, LESSONS_B)  # copyfile = 纯字节，不复制元数据
print(f"目标 {LESSONS_B}\n     {stat_line(LESSONS_B)}")
a_sha, b_sha = sha256(LESSONS_A), sha256(LESSONS_B)
print(f"两侧 SHA256 一致 = {a_sha == b_sha}；拷贝时刻 = {copied_at}")
print(f"可直接粘进 docs\\_runB-0732-evidence.md §1：拷贝时刻 {copied_at}；run A 库 size/mtime/SHA256 = "
      f"{os.path.getsize(LESSONS_A)} B / {time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(os.stat(LESSONS_A).st_mtime))} / {a_sha}；"
      f"run B 库 = {os.path.getsize(LESSONS_B)} B / {time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(os.stat(LESSONS_B).st_mtime))} / {b_sha}")

print("\n=== 3) 五文件 SHA256 vs A 的 sidecar ===")
with open(SIDE_A, encoding="utf-8") as fh:
    side = json.load(fh)
print(f"  sidecar head = {side.get('head')}；pid = {side.get('pid')}；argv = {side.get('argv')}")
bad = []
for rel, rec in (side.get("files") or {}).items():
    p = os.path.join(ROOT, rel.replace("/", os.sep))
    now = sha256(p) if os.path.exists(p) else "<缺失>"
    ok = (now == rec.get("sha256"))
    print(f"  {'✅' if ok else '❌'} {rel}\n       sidecar {rec.get('sha256')} @ {rec.get('mtime')}\n       现盘   {now}")
    if not ok:
        bad.append(rel)
if bad:
    print(f"\n❌ 有 {len(bad)} 个文件与 sidecar 不一致 ⇒ 停手报 Lead：{bad}")
    sys.exit(3)
print("\n✅ 五个源文件与 A 起跑时逐字一致（argv 只差 --journal）⇒ 可以起 run B")
