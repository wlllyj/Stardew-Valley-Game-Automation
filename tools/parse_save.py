"""解析星露谷存档,输出农场关键状态。
存档是 XML 格式,主文件不含扩展名。

======================================================================
来源与适配说明（新项目 agentfarm）
======================================================================
本文件复制自旧项目（只读引用，未修改原文件）：
    C:\\Users\\admin\\WorkBuddy\\2026-10-04-20-36-38\\stardew-auto-farm\\tools\\scripts\\parse_save.py

本副本做的**最小适配**：
  1. 加本段来源说明。
  2. 存档目录**完全参数化**：CLI `--saves <目录>` > 环境变量
     `STARDEW_SAVES_DIR` > `%APPDATA%\\StardewValley\\Saves`。
     **不硬编码盘符或用户目录**。
  3. 修掉旧实现的崩溃点：`os.environ["USERPROFILE"]` 在变量缺失时抛
     `KeyError`；改为 `os.path.expanduser("~")` 兜底。
  4. 去掉未使用的 `import xml.etree.ElementTree`，改为 `--json` 可选输出。
     注意：审计 §4.4 明确指出旧版本脚本的**覆盖范围"未确认"** —— 这是
     已知局限，不等于已验证。本副本只做路径适配，**没有**扩大解析覆盖度。
======================================================================

用法:
    python parse_save.py                            # 分析默认存档目录下所有存档
    python parse_save.py --saves <目录>              # 指定存档根目录
    python parse_save.py --save <存档主文件>          # 只分析单个存档主文件
    python parse_save.py --json                     # 输出 JSON

环境变量:
    STARDEW_SAVES_DIR   存档根目录
"""
import json
import os
import re
import sys

# 存档根目录：环境变量优先，否则用当前用户 Roaming 下的默认位置。
SAVES_DIR = (os.environ.get("STARDEW_SAVES_DIR", "").strip()
             or os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                             "StardewValley", "Saves"))


def _force_utf8_output():
    """让 print 在 stdout 被重定向/管道捕获时也能输出中文。

    Windows 上 Python 默认按控制台代码页（常为 cp1252/cp936）编码 stdout，
    一旦被管道捕获就会因中文字符抛 UnicodeEncodeError。**只读的编码设置**，
    不改变程序逻辑；失败静默忽略（旧环境/无 stdout 时不应因此崩溃）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_output()


def find_saves(saves_dir=None):
    """列出存档根目录下的所有存档。saves_dir 省略时用 SAVES_DIR。"""
    root = saves_dir or SAVES_DIR
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        main = os.path.join(d, name)
        info = os.path.join(d, "SaveGameInfo")
        if os.path.isfile(main):
            out.append({"folder": name, "main": main, "info": info, "dir": d})
    return out


def text(root, tag, default="-"):
    el = root.find(f".//{tag}")
    return el.text if el is not None and el.text is not None else default


def analyze(path):
    """流式读取,避免 3MB XML 全量解析的内存问题。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    result = {}

    # 用正则精准抓取顶层关键字段(比 ElementTree 快且容错)
    patterns = {
        "player_name": r"<player><name>([^<]*)</name>",
        "farm_name":   r"<farmName>([^<]*)</farmName>",
        "money":       r"<money>(\d+)</money>",
        "year":        r"<year>(\d+)</year>",
        "season":      r"<currentSeason>([^<]*)</currentSeason>",
        "day":         r"<dayOfMonth>(\d+)</dayOfMonth>",
        "which_farm":  r"<whichFarm>(\d+)</whichFarm>",
        "game_version": r"<gameVersion>([^<]*)</gameVersion>",
        "farming_lv":  r"<farmingLevel>(\d+)</farmingLevel>",
        "stamina":     r"<stamina>(\d+)</stamina>",
        "max_stamina": r"<maxStamina>(\d+)</maxStamina>",
    }
    for k, pat in patterns.items():
        m = re.search(pat, content)
        result[k] = m.group(1) if m else "-"

    # 技能等级(在多处出现,取第一个 farming 块)
    sk = re.search(r"<farmingLevel>(\d+)</farmingLevel>", content)
    result["farming_lv"] = sk.group(1) if sk else "-"

    # 邮件标记(判断是否解锁温室/沙漠)
    mails = re.findall(r"<string>(ccPantry|ccBoilerRoom|ccCraftsRoom|ccFishTank|ccVault|ccBulletin|busFixed|ccBusFixed|hasGreenhouse)</string>", content)
    result["mail_flags"] = sorted(set(mails))

    # 统计建筑
    result["buildings"] = len(re.findall(r"<Building>", content))

    # 统计箱子
    result["chests"] = len(re.findall(r"<items><Item xsi:type=\"Object\">", content))

    # 农作物数量(粗略)
    result["crop_count"] = len(re.findall(r"<crop ", content))

    return result


SEASON_CN = {"spring": "春", "summer": "夏", "fall": "秋", "winter": "冬"}
FARM_TYPE = {
    "0": "标准农场", "1": "河畔农场", "2": "森林农场", "3": "山顶农场",
    "4": "荒野农场", "5": "四角农场", "6": "海滩农场",
}


def print_one(folder, main_path, info_path, r):
    """把单个存档的分析结果打成人读报告。"""
    print(f"\n存档文件夹: {folder}")
    print(f"  主文件: {os.path.getsize(main_path):,} 字节")
    if info_path and os.path.isfile(info_path):
        print(f"  信息文件: {os.path.getsize(info_path):,} 字节")

    print("\n  --- 农场状态 ---")
    print(f"  玩家:       {r['player_name']}")
    print(f"  农场名:     {r['farm_name']}")
    print(f"  农场类型:   {FARM_TYPE.get(r['which_farm'], '未知(' + r['which_farm'] + ')')}")
    season = SEASON_CN.get(r["season"], r["season"])
    print(f"  游戏进度:   第 {r['year']} 年 {season} 季 第 {r['day']} 日")
    print(f"  金钱:       {int(r['money']):,} g" if r["money"].isdigit() else f"  金钱:       {r['money']}")
    print(f"  游戏版本:   {r['game_version']}")
    print(f"  耕种等级:   {r['farming_lv']}")
    print(f"  体力:       {r['stamina']} / {r['max_stamina']}")

    print("\n  --- 农场设施 ---")
    print(f"  建筑数量:   {r['buildings']}")
    print(f"  箱子数量:   {r['chests']}")

    print("\n  --- 关键解锁 ---")
    if r["mail_flags"]:
        for f in r["mail_flags"]:
            print(f"  ✓ {f}")
    else:
        print("  (尚未解锁温室/社区中心相关)")

    has_gh = "hasGreenhouse" in r["mail_flags"] or "ccPantry" in r["mail_flags"]
    has_desert = "busFixed" in r["mail_flags"] or "ccBusFixed" in r["mail_flags"]
    print(f"\n  温室: {'已解锁 ✓' if has_gh else '未解锁 ✗'}")
    print(f"  沙漠: {'已解锁 ✓' if has_desert else '未解锁 ✗'}")


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    saves_dir = None
    single = None
    for i, a in enumerate(args):
        if a == "--saves" and i + 1 < len(args):
            saves_dir = args[i + 1]
        elif a == "--save" and i + 1 < len(args):
            single = args[i + 1]
        elif a == "--saves-dir" and i + 1 < len(args):
            saves_dir = args[i + 1]

    # --save <主文件>：只分析单个存档
    if single:
        if not os.path.isfile(single):
            sys.exit(f"找不到存档主文件: {single}")
        r = analyze(single)
        if as_json:
            print(json.dumps({"save": single, "result": r}, ensure_ascii=False, indent=2))
        else:
            print("=" * 70)
            print_one(os.path.basename(os.path.dirname(single)), single, None, r)
        return 0

    saves = find_saves(saves_dir)
    if not saves:
        root = saves_dir or SAVES_DIR
        msg = f"未找到任何存档（查找目录: {root}）。"
        if as_json:
            print(json.dumps({"saves_dir": root, "saves": []}, ensure_ascii=False, indent=2))
        else:
            print(msg)
            print("可用 --saves <目录> 或环境变量 STARDEW_SAVES_DIR 指定存档根目录。")
        return 0

    results = []
    for s in saves:
        r = analyze(s["main"])
        results.append({"folder": s["folder"], "main": s["main"], "result": r})

    if as_json:
        print(json.dumps({"saves_dir": saves_dir or SAVES_DIR, "saves": results},
                         ensure_ascii=False, indent=2))
        return 0

    print("=" * 70)
    print(f"找到 {len(saves)} 个存档")
    print("=" * 70)
    for s, item in zip(saves, results):
        print_one(s["folder"], s["main"], s["info"], item["result"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
