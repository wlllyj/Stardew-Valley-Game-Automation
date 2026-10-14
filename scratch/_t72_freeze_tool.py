# -*- coding: utf-8 -*-
"""task-72 取证：把「已提交 HEAD 的 verify-run3.py」与「Lead 在制的 task-71 版本」各冻一份。

用法：python scratch\\_t72_freeze_tool.py
只读 git/工作树，只写 scratch\\_t72_tool_*.py 两个冻结副本（不改 tools\\）。
"""
import hashlib
import subprocess
import sys

HEAD_OUT = "scratch/_t72_tool_head.py"
WIP_OUT = "scratch/_t72_tool_wip.py"
TOOL = "tools/verify-run3.py"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    p = subprocess.run(["git", "show", f"HEAD:{TOOL}"], capture_output=True)
    if p.returncode != 0:
        print("git show 失败：" + p.stderr.decode("utf-8", "replace"))
        return 1
    head = p.stdout
    with open(HEAD_OUT, "wb") as fh:
        fh.write(head)
    with open(TOOL, "rb") as fh:
        wip = fh.read()
    with open(WIP_OUT, "wb") as fh:
        fh.write(wip)
    head_sha, wip_sha = sha(head), sha(wip)
    print(f"HEAD 已提交版 : {HEAD_OUT}  {len(head):6d} B  {len(head.splitlines()):4d} 行  sha256={head_sha}")
    print(f"工作树(在制)  : {WIP_OUT}  {len(wip):6d} B  {len(wip.splitlines()):4d} 行  sha256={wip_sha}")
    print("两侧" + ("相同（task-71 未改工作树）" if head_sha == wip_sha else "不同 ⇒ task-71 正在改工作树，未提交"))
    st = subprocess.run(["git", "status", "--short", "--", TOOL], capture_output=True)
    print("git status --short -- tools/verify-run3.py : " + repr(st.stdout.decode("utf-8", "replace")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
