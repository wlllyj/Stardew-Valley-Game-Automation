# -*- coding: utf-8 -*-
"""Restore the 63bb3e0 version of docs/_review-0.7.48.md verbatim as an appendix
(we overwrote it with the task-38 review; nothing must be destroyed)."""
import pathlib
import subprocess

repo = pathlib.Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
cur = repo / "docs" / "_review-0.7.48.md"

old = subprocess.run(
    ["git", "-C", str(repo), "show", "63bb3e0:docs/_review-0.7.48.md"],
    capture_output=True, check=True).stdout.decode("utf-8")

text = cur.read_text(encoding="utf-8")
marker = "## 附录B"
if marker in text:
    print("appendix already present; no-op")
else:
    text = text.rstrip() + "\n\n---\n\n" + (
        "## 附录B：上一版 `docs/_review-0.7.48.md`（commit `63bb3e0`）原文保留\n\n"
        "> 说明：本文件此前已由本会话较早的一轮写入并被提交（`63bb3e0 docs(review): 0.7.48 正式对抗验收（provenance+单测+P0 清单）`），\n"
        "> 覆盖 **另一批范围**（在 `e2b69d9` 之上追加的 P0-1..P0-7 代码批，commit `0f72f3c`..`bbb6a89`）。\n"
        "> 本卡（T5 · task-38 字段奇偶补齐）重写了正文；为不丢失既有验收记录，此处**逐字保留**该版原文（内容可能有更早的时点印记，勿当本卡结论）。\n\n"
        + old.rstrip() + "\n")
    cur.write_text(text, encoding="utf-8")
    print("appended", len(old), "chars from 63bb3e0")
print("new size", len(cur.read_text(encoding='utf-8')))
