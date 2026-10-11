"""一次性查看：把 plan-llm-manual 的日志切成 4 段打印（只读，不改任何东西）。"""
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")


def section(start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return f"（没找到 {start}）"
    j = text.find(end, i + 1)
    return text[i:] if j < 0 else text[i:j]


print(f"总长度 {len(text)} 字符")
print("=" * 30, "段 1 简报", "=" * 30)
print(section("── 1.", "── 2.")[:1600])
print("=" * 30, "段 2 提示词里的田区行", "=" * 30)
seg2 = section("── 2.", "── 3.")
print(f"（段 2 共 {len(seg2)} 字符）")
for line in seg2.splitlines():
    if "field_" in line or "田区" in line:
        print(line[:400])
print("=" * 30, "段 3 模型原文返回", "=" * 30)
print(section("── 3.", "── 4.")[:4000])
print("=" * 30, "段 4 决策结果", "=" * 30)
print(section("── 4.", "\n（以上")[:2500])
