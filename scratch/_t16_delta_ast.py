# -*- coding: utf-8 -*-
r"""【T16 / deputy-lead】自验 `git diff 51ef0a7 daceb48` 的 delta 是否**纯注释/测试/scratch/docs**。

判据（不采信任何自述，逐文件机械比）：
1. 改动文件清单 + 每文件增删行；
2. `.py` 文件：用 `ast` 解析两版、**剔除 docstring 表达式**后 `ast.dump` 比对
   ⇒ 相等 ⇒ 语义/结构等价（注释天然不进 AST）；不等 ⇒ 报首个差异节点；
3. `.py` 文件再做一层粗判：剔除「本行 lstrip 后以 `#` 开头」的行后逐行比对；
4. 非 `.py`（.md/.txt/.json）判为文档/数据，另列其内容性质。

用法：$env:PYTHONUTF8='1'; & <DSH python> scratch\_t16_delta_ast.py [refA] [refB]
"""
from __future__ import annotations

import ast
import subprocess
import sys

REPO = r"D:\OpenCode Workspace\星露谷游戏自动化"
A = sys.argv[1] if len(sys.argv) > 1 else "51ef0a7"
B = sys.argv[2] if len(sys.argv) > 2 else "daceb48"


def sh(args: list[str]) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8").stdout


def blob(ref: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO,
                          capture_output=True, text=True, encoding="utf-8").stdout


def strip_docstrings(tree: ast.AST) -> ast.AST:
    """把模块/类/函数首个 Expr(Constant str) 当 docstring 剔除。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                v = body[0].value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    node.body = body[1:]
    return tree


def main() -> int:
    print(f"=== 自验 {A} -> {B} ===")
    stat = sh(["git", "diff", "--stat", A, B])
    print(stat.rstrip())
    names = [l for l in sh(["git", "diff", "--name-only", A, B]).splitlines() if l.strip()]
    print(f"改动文件数 = {len(names)}")

    fail = 0
    for p in names:
        sa = sh(["git", "diff", "--shortstat", A, B, "--", p]).strip()
        if not p.endswith(".py"):
            print(f"[非PY] {p}  ({sa})  -> 文档/数据类")
            continue
        ta, tb = blob(A, p), blob(B, p)
        # (2) AST 比对
        try:
            da = ast.dump(strip_docstrings(ast.parse(ta)))
            db = ast.dump(strip_docstrings(ast.parse(tb)))
            ast_eq = (da == db)
            note = "AST(去docstring) 相同 ⇒ 语义等价"
            if not ast_eq:
                # 找首个差异行号（用注释剔除法交叉定位）
                la = [i for i, l in enumerate(ta.splitlines(), 1)
                      if not l.lstrip().startswith("#")]
                note = "AST(去docstring) **不同**"
                fail += 1
                print(f"[PY] {p}  ({sa})  -> {note}  非注释行 {len(la)}")
                continue
        except SyntaxError as e:
            note = f"AST 解析失败 {e}"
            fail += 1
            print(f"[PY] {p}  ({sa})  -> {note}")
            continue
        # (3) 注释剔除后逐行比
        na = [l for l in ta.splitlines() if not l.lstrip().startswith("#")]
        nb = [l for l in tb.splitlines() if not l.lstrip().startswith("#")]
        same = (na == nb)
        if not same:
            fail += 1
            note += "；**但剔注释后逐行不同** ⇒ 存在非注释改动"
        else:
            note += "；剔注释后逐行相同 ⇒ 纯注释"
        print(f"[PY] {p}  ({sa})  -> {note}")
    print(f"=== 结论：{'发现非注释改动 %d 处' % fail if fail else '零非注释改动（逐文件 AST+剔注释双判）'} ===")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
