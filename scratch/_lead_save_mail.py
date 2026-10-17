"""Lead 只读探针：查存档 XML 的邮件/配方，判断熔炉（Furnace 114）蓝图是否还躺在邮件里。

背景：铜工具升级需要 5 条铜锭；铜锭要熔炉；全存档无熔炉、`craftingRecipes` 也没 Furnace。
SDV 里 Furnace 配方是 Clint 在**采矿 1 级后寄来的邮件**（读取邮件才学会）。
本存档 mining=1 级（xp 279）却无配方 ⇒ 检查 mailbox / mailReceived。
只读，不写任何东西。
"""
from __future__ import annotations

import os
import re

SAVE = os.path.expandvars(
    r"%APPDATA%\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035"
)


def block(s: str, tag: str) -> str | None:
    m = re.search(r"<" + tag + r">(.*?)</" + tag + r">", s, re.S)
    return m.group(1) if m else None


def strings(b: str) -> list[str]:
    return re.findall(r"<string>(.*?)</string>", b, re.S)


def main() -> int:
    if not os.path.exists(SAVE):
        print("save not found", SAVE)
        return 2
    s = open(SAVE, encoding="utf-8", errors="replace").read()
    print("save size", len(s), "path", SAVE)
    for tag in ("mailReceived", "mailbox", "craftingRecipes", "cookingRecipes"):
        b = block(s, tag)
        print(f"--- {tag} ---")
        if b is None:
            print("  <absent>")
            continue
        items = strings(b)
        print("  count", len(items))
        for it in items[:60]:
            print("   ", it)
    print("--- 关键字命中 ---")
    for kw in ("Furnace", "Clint", "furnace", "114"):
        print(f"  {kw!r}: {s.count(kw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
