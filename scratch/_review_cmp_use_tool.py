# -*- coding: utf-8 -*-
"""deputy-lead 独立对账：把 mod/AgentFarm.Bridge/UseToolSkill.cs 的 HEAD 版本与在制版本
按**函数**切开逐行比对，回答验收条款①「非近战起手路径与 HEAD 逐字未变」。

只读仓库（git show / 读文件），不写任何仓库文件；输出全部 print 到 stdout。
用法：python scratch\\_review_cmp_use_tool.py
"""
from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REL = "mod/AgentFarm.Bridge/UseToolSkill.cs"

SIGS = [
    "private void Swing()",
    "private bool BeginUse(Farmer p)",
    "private bool Done()",
    "private static bool ClassifyTile(Point p)",
]


def head_bytes() -> bytes:
    cp = subprocess.run(["git", "show", f"HEAD:{REL}"], cwd=str(REPO),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cp.returncode != 0:
        raise SystemExit(f"git show 失败：{cp.stderr.decode('utf-8', 'replace')}")
    return cp.stdout


def extract(text: str, sig: str) -> tuple[int, int, str] | None:
    """按 '签名 + 花括号配对' 切出函数，返回 (起始行号1基, 结束行号, 源码)。"""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if sig in ln:
            depth = 0
            started = False
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    return i + 1, j + 1, "\n".join(lines[i:j + 1])
            return i + 1, len(lines), "\n".join(lines[i:])
    return None


def main() -> int:
    hb = head_bytes().decode("utf-8-sig")
    wb = (REPO / REL).read_text(encoding="utf-8-sig")
    print(f"HEAD 行数={len(hb.splitlines())}  在制行数={len(wb.splitlines())}")

    for sig in SIGS:
        h = extract(hb, sig)
        w = extract(wb, sig)
        print("\n" + "=" * 78)
        print(f"函数：{sig}")
        if h is None and w is None:
            print("  两边都没有")
            continue
        if h is None:
            print(f"  仅**在制**有（新增函数）：在制 {w[0]}-{w[1]} 行，{w[1]-w[0]+1} 行")
            continue
        if w is None:
            print(f"  ⚠️ 仅 HEAD 有（被删？）：HEAD {h[0]}-{h[1]} 行")
            continue
        print(f"  HEAD {h[0]}-{h[1]} 行（{h[1]-h[0]+1} 行） | 在制 {w[0]}-{w[1]} 行（{w[1]-w[0]+1} 行）")
        if h[2] == w[2]:
            print("  ✅ **逐字完全相同**")
            continue
        print("  差异（- HEAD / + 在制）：")
        for line in difflib.unified_diff(h[2].splitlines(), w[2].splitlines(),
                                         "HEAD", "worktree", lineterm="", n=1):
            print("    " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
