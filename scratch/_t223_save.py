"""只读：从存档 XML 里取 Furnace 授予相关的关键事实（不改存档）。

用法：
  python scratch\\_t223_save.py            # 默认找最新的存档目录
输出：
  - 存档路径 / 玩家名 / 日期
  - Farmer.stats 里 CopperFound/IronFound/... 与 mining 相关
  - Farmer.craftingRecipes 键列表（是否含 Furnace）
  - Farmer.mailReceived / mailbox / mailForTomorrow（是否含 copperFound）
  - 背包里铜矿/铜锭数量
"""
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAVES = os.path.expanduser(r"~\AppData\Roaming\StardewValley\Saves")


def newest_save():
    dirs = [d for d in glob.glob(os.path.join(SAVES, "*")) if os.path.isdir(d)]
    files = []
    for d in dirs:
        base = os.path.join(d, os.path.basename(d))
        if os.path.isfile(base):
            files.append(base)
    if not files:
        # 有时主文件名不同（含扩展名或无者），退化为找最大文件
        for d in dirs:
            for p in glob.glob(os.path.join(d, "*")):
                if os.path.isfile(p) and not p.endswith((".xml", ".bak", ".json")):
                    files.append(p)
    return max(files, key=os.path.getmtime)


def main():
    path = newest_save()
    print("存档:", path)
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    print("大小:", len(text))

    def find_block(tag):
        m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
        return m.group(1) if m else None

    stats = find_block("stats") or ""
    for key in ("CopperFound", "IronFound", "GoldFound", "IridiumFound",
                "DaysPlayed", "Seedsof", "StepsTaken"):
        m = re.search(r"<%s>([^<]*)</%s>" % (key, key), stats)
        if m:
            print("stats.%s = %s" % (key, m.group(1)))
    for m in re.finditer(r"<([A-Za-z]+)>(\d+)</\1>", stats):
        if m.group(1).startswith(("Copper", "Iron", "Gold", "Iridium", "Stone", "Ore")):
            print("stats", m.group(1), "=", m.group(2))

    # 技能
    exp = find_block("experiencePoints")
    lv = find_block("Level")
    print("experiencePoints:", (exp or "")[:200])
    print("Level:", (lv or "")[:200])

    # craftingRecipes 键
    cr = find_block("craftingRecipes") or ""
    keys = re.findall(r"<key>(?:<string>)?([^<]+)", cr)
    print("craftingRecipes 数:", len(keys))
    print("含 Furnace:", any("Furnace" in k for k in keys), keys[:60])

    ck = find_block("cookingRecipes") or ""
    ckeys = re.findall(r"<key>(?:<string>)?([^<]+)", ck)
    print("cookingRecipes 数:", len(ckeys), ckeys[:20])

    for tag in ("mailReceived", "mailbox", "mailForTomorrow"):
        blk = find_block(tag) or ""
        items = re.findall(r"<string>([^<]*)</string>", blk)
        if not items:
            items = re.findall(r"<[A-Za-z]+>([^<]*)</[A-Za-z]+>", blk)
        print(tag, "数:", len(items), "含 copperFound:", any("copperFound" == i or "copperFound" in i for i in items))
        print("  ", items[:30])

    # 背包铜矿/铜锭
    items = find_block("items") or ""
    n_ore = text.count("<int>378</int>")
    n_bar = text.count("<int>334</int>")
    print("保存文本里 (O)378/334 出现次数:", n_ore, n_bar)
    for m in re.finditer(r"<Item xsi:type=\"(?:O|Object)\">(.*?)</Item>", text, re.S):
        seg = m.group(1)
        if "<int>378</int>" in seg or "(O)378" in seg:
            print("铜矿段:", seg[:300].replace("\n", " "))
        if "<int>334</int>" in seg or "(O)334" in seg:
            print("铜锭段:", seg[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
