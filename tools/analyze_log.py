#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMAPI 日志分析器 —— 自动发现星露谷 Mod 的问题。

======================================================================
来源与适配说明（新项目 agentfarm）
======================================================================
本文件复制自旧项目（只读引用，未修改原文件）：
    C:\\Users\\admin\\WorkBuddy\\2026-10-04-20-36-38\\stardew-auto-farm\\tools\\scripts\\analyze_log.py
审计 docs/_legacy-audit.md §4.4 评定其为"高价值，建议复用"（刷屏风暴检测 /
错误归类 / 已知故障签名匹配 / 任务健康统计）。

本副本做的**最小适配**（不改分析逻辑，只做路径参数化与说明）：
  1. 加本段来源说明。
  2. 日志路径**完全参数化**，优先级：
     CLI 位置参数 / `--log` > 环境变量 `STARDEW_SMAPI_LOG`
     > `%APPDATA%\\StardewValley\\ErrorLogs\\SMAPI-latest.txt`
     **不硬编码任何盘符或游戏安装目录**（旧项目 ai_planner.py:52 硬编码
     `D:\\...\\Mods` 是审计点名的缺陷，本工具不再重复该错误）。
  3. Mod 名列表可配置：`--mods A,B` 或环境变量 `STARDEW_MODS`；
     默认在旧项目 5 个之外补上 AutoFarmMiner（审计 §4.4 指出旧 build.ps1
     的 $Mods 漏了它）。
  4. 修正位置参数解析：旧实现 `find_log_path(argv)` 内部又做 `argv[1:]`，
     而调用方传入的已是 `sys.argv[1:]`，等于跳过了一个参数。
======================================================================

用法:
    python analyze_log.py                # 分析最新日志
    python analyze_log.py <日志路径>      # 分析指定日志
    python analyze_log.py --log <路径>    # 同上（显式）
    python analyze_log.py --json         # 输出 JSON(给自动化用)
    python analyze_log.py --since 30     # 只看最近 30 分钟(默认全部)
    python analyze_log.py --mods AutoFarmWorker,AutoFarmMiner

环境变量:
    STARDEW_SMAPI_LOG   默认日志路径
    STARDEW_MODS        逗号分隔的 Mod 名列表

它能发现什么:
  1. ERROR / WARN 归类统计
  2. 【刷屏风暴】同一模式短时间内高频重复 —— 这是最隐蔽也最致命的
     症状(例如"每帧 warp 一次"会把玩家锁死在两张地图之间)
  3. 已知故障签名匹配(带修复建议)
  4. 各 Mod 的活跃度
  5. 任务健康度(放弃任务 / 寻路失败 / 跨地点失败 / 超时)
  6. Mod 崩溃与未处理异常

退出码: 0 = 健康, 1 = 发现问题(方便自动化判断)
"""

import os
import re
import sys
import json
import collections
from datetime import datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

# 默认认识旧项目的 5 个 Mod；已补上旧 build.ps1 遗漏的 AutoFarmMiner。
DEFAULT_MODS = [
    "AutoFarmPlanner",
    "AutoFarmWorker",
    "AutoFarmTrader",
    "AutoFarmFishing",
    "AutoFarmRancher",
    "AutoFarmMiner",
]


def _env_mods():
    """从 STARDEW_MODS 读 Mod 列表（逗号分隔）；未设置则用默认表。"""
    raw = os.environ.get("STARDEW_MODS", "").strip()
    if not raw:
        return list(DEFAULT_MODS)
    out = [m.strip() for m in raw.split(",") if m.strip()]
    return out or list(DEFAULT_MODS)


MODS = _env_mods()


def _default_logs():
    """默认日志候选位置。全部由环境变量推导，不含硬编码盘符。"""
    cands = []
    env_log = os.environ.get("STARDEW_SMAPI_LOG", "").strip()
    if env_log:
        cands.append(Path(env_log))
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        base = Path(appdata) / "StardewValley" / "ErrorLogs"
        cands.append(base / "SMAPI-latest.txt")
        cands.append(base / "SMAPI-crash.txt")
    return cands


# 默认日志位置
DEFAULT_LOGS = _default_logs()


def _force_utf8_output():
    """让 print 在 stdout 被重定向/管道捕获时也能输出中文。

    Windows 上 Python 默认按控制台代码页（常为 cp1252/cp936）编码 stdout，
    一旦被管道捕获就会因中文字符抛 UnicodeEncodeError。**只读的编码设置**，
    不改变分析逻辑；失败静默忽略（旧环境/无 stdout 时不应因此崩溃）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_force_utf8_output()

# 时间戳: [22:10:22 TRACE game]
TS_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\s+(TRACE|DEBUG|INFO|WARN|ERROR|ALERT)\s+([^\]]+)\]\s?(.*)$")

# 把"会变化的数字"归一化,好把同类行聚成一个模式
NORM_RULES = [
    (re.compile(r"\{X:\s*-?\d+\s*Y:\s*-?\d+\}"), "{TILE}"),
    (re.compile(r"@\s*-?\d+,\s*-?\d+"), "@{XY}"),
    (re.compile(r"\b\d{4,}\b"), "{N}"),           # 大数字
    (re.compile(r"\b\d+\.\d+\b"), "{F}"),          # 小数
    (re.compile(r"\b\d+\b"), "{n}"),               # 普通数字
    (re.compile(r"\(\d+,\d+\)"), "({XY})"),
]

# ----------------------------------------------------------------------
# 已知故障签名: (匹配模式, 标题, 诊断, 建议)
# 顺序有意义 —— 先匹配更具体的
# ----------------------------------------------------------------------
KNOWN_ISSUES = [
    (
        re.compile(r"doesn'?t seem to be valid JSON|Can'?t parse JSON", re.I),
        "JSON 数据文件加载失败",
        "数据文件要么语法错误,要么结构与 C# 类型不匹配。"
        "常见陷阱: JSON 里是字符串(\"1.6\")但 C# 声明成 int;或字段名大小写/下划线不一致。",
        "用 tools/scripts/check_data_json.py 校验;确认 C# 侧有 [JsonProperty(\"snake_case\")]。",
    ),
    (
        re.compile(r"KeyNotFoundException", re.I),
        "字典键不存在",
        "多半在用 Game1.getFarm() 之类按名字取地点的旧写法 —— 存档未加载时会抛。",
        "改成遍历 Game1.locations 找目标类型。",
    ),
    (
        re.compile(r"NullReferenceException", re.I),
        "空引用异常",
        "某个对象还没初始化就被访问(常见:作物为 null、地点未加载、玩家不在世界内)。",
        "加判空;并在 Context.IsWorldReady / IsPlayerFree 为 false 时直接返回。",
    ),
    (
        re.compile(r"IndexOutOfRange|ArgumentOutOfRange", re.I),
        "数组越界",
        "坐标或索引超出了地图/列表范围。",
        "访问 terrainFeatures / Objects 前先判断坐标是否在地图内。",
    ),
    (
        re.compile(r"Mod failed handling that command", re.I),
        "控制台命令执行失败",
        "命令处理函数里抛了异常。",
        "看该命令对应的异常堆栈,通常同上几种原因。",
    ),
    (
        re.compile(r"(走不到|放弃任务)", re.I),
        "任务被放弃(走不到目的地)",
        "寻路失败次数过多。可能是目标格被围住、跨地图、或寻路逻辑有问题。",
        "看 afw dbg;若大量出现且伴随 Warping 刷屏,说明跨地点逻辑有问题。",
    ),
    (
        re.compile(r"Warping to", re.I),
        "地图传送",
        "正常的地图切换。但若短时间高频出现,说明跨地点逻辑陷入循环 —— "
        "会抢占 controller 让玩家失去控制,并让角色在两图间闪现。",
        "确认 CrossLocationMode 与挂起(_awaitingLocationChange)逻辑正常;必要时设 never。",
    ),
    (
        re.compile(r"寻路失败|PathFind", re.I),
        "寻路失败",
        "PathFindController 无法到达目标。",
        "目标格可能不可达;检查布局是否留了通道(BedGutter)。",
    ),
    (
        re.compile(r"跨地点", re.I),
        "跨地点移动",
        "从一个地点去另一个地点的过程记录。",
        "若频繁伴随等待超时,检查出口扫描是否找得到门。",
    ),
]

# 刷屏阈值: 同一模式在 N 秒窗口内出现 >= K 次
SPAM_WINDOW_SEC = 1.0
SPAM_THRESHOLD = 10

C_RESET = "\033[0m"
C_RED = "\033[91m"
C_YEL = "\033[93m"
C_GRN = "\033[92m"
C_CYA = "\033[96m"
C_GRY = "\033[90m"
C_BOLD = "\033[1m"


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def color(s: str, c: str) -> str:
    return f"{c}{s}{C_RESET}" if supports_color() else s


# ----------------------------------------------------------------------
# 解析
# ----------------------------------------------------------------------

def find_log_path(argv) -> Path:
    """按 `--log <路径>` > 位置参数 > 环境变量/默认候选 的顺序定位日志。

    argv 是**已经剥掉脚本名**的参数列表（即 sys.argv[1:]）。
    """
    # 1) 显式 --log <path>
    for i, a in enumerate(argv):
        if a == "--log" and i + 1 < len(argv):
            p = Path(argv[i + 1])
            if p.exists():
                return p
            sys.exit(f"找不到日志文件: {argv[i + 1]}")

    # 2) 位置参数（跳过所有 --xxx 及其取值）
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a.startswith("-"):
            if a in ("--since", "--log", "--mods"):
                skip_next = True
            continue
        p = Path(a)
        if p.exists():
            return p
        sys.exit(f"找不到日志文件: {a}")

    # 3) 环境变量 STARDEW_SMAPI_LOG / APPDATA 下的默认位置
    for p in DEFAULT_LOGS:
        if p.exists():
            return p
    sys.exit("找不到 SMAPI 日志。请用 --log <路径> 指定，"
             "或设置环境变量 STARDEW_SMAPI_LOG。")


def normalize(msg: str) -> str:
    """把会变化的数字归一化,便于把同类行聚成一个模式。"""
    s = msg
    for rx, rep in NORM_RULES:
        s = rx.sub(rep, s)
    return s.strip()


def parse_log(path: Path, since_minutes=None):
    """返回 (entries, raw_lines)"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        sys.exit(f"读日志失败: {e}")

    entries = []
    cutoff = None
    if since_minutes:
        cutoff = datetime.now() - timedelta(minutes=since_minutes)

    for line in text.splitlines():
        m = TS_RE.match(line)
        if not m:
            continue
        hh, mm, ss, level, source, msg = m.groups()
        t = datetime.now().replace(hour=int(hh), minute=int(mm), second=int(ss), microsecond=0)
        if cutoff and t < cutoff:
            continue
        entries.append({
            "time": t,
            "hms": f"{hh}:{mm}:{ss}",
            "level": level,
            "source": source.strip(),
            "msg": msg,
            "norm": normalize(msg),
            "raw": line,
        })
    return entries, text


# ----------------------------------------------------------------------
# 分析
# ----------------------------------------------------------------------

def analyze(entries):
    r = {
        "total": len(entries),
        "span": None,
        "by_level": collections.Counter(),
        "errors": [],
        "warns": [],
        "mod_activity": collections.Counter(),
        "task_health": collections.Counter(),
        "spam": [],
        "known": [],
    }

    if not entries:
        return r

    r["span"] = (entries[0]["hms"], entries[-1]["hms"])

    for e in entries:
        r["by_level"][e["level"]] += 1
        if e["level"] == "ERROR":
            r["errors"].append(e)
        elif e["level"] in ("WARN", "ALERT"):
            r["warns"].append(e)

        # 我们 Mod 的活跃度
        for mod in MODS:
            if e["source"] == mod or mod in e["source"]:
                r["mod_activity"][mod] += 1
                break

        # 任务健康
        for key, pat in [
            ("放弃任务", r"放弃任务|走不到"),
            ("寻路失败", r"寻路失败"),
            ("跨地点失败", r"跨地点(等待超时|失败|传送)"),
            ("任务超时", r"超时"),
            ("地图切换", r"Warping to"),
        ]:
            if re.search(pat, e["msg"]):
                r["task_health"][key] += 1

    # ---- 刷屏检测: 同一(来源+模式)在时间窗内高频出现 ----
    buckets = collections.defaultdict(list)
    for e in entries:
        key = (e["source"], e["norm"])
        buckets[key].append(e["time"])

    for (source, norm), times in buckets.items():
        if len(times) < SPAM_THRESHOLD:
            continue
        times.sort()
        # 滑动窗口找最大密度
        best_n, best_start = 0, None
        j = 0
        for i in range(len(times)):
            while j < len(times) and (times[j] - times[i]).total_seconds() <= SPAM_WINDOW_SEC:
                j += 1
            n = j - i
            if n > best_n:
                best_n, best_start = n, times[i]
        if best_n >= SPAM_THRESHOLD:
            r["spam"].append({
                "source": source,
                "pattern": norm,
                "count": best_n,
                "window": SPAM_WINDOW_SEC,
                "at": best_start.strftime("%H:%M:%S"),
                "total": len(times),
            })

    r["spam"].sort(key=lambda x: -x["count"])

    # ---- 已知故障签名 ----
    seen = set()
    for e in entries:
        for rx, title, diag, fix in KNOWN_ISSUES:
            if rx.search(e["msg"]):
                k = (title, e["source"])
                if k in seen:
                    break
                seen.add(k)
                hits = [x for x in entries
                        if x["source"] == e["source"] and rx.search(x["msg"])]
                r["known"].append({
                    "title": title,
                    "source": e["source"],
                    "diag": diag,
                    "fix": fix,
                    "count": len(hits),
                    "first": hits[0]["hms"],
                    "last": hits[-1]["hms"],
                    "sample": hits[0]["msg"][:160],
                })
                break

    return r


def health_grade(r) -> tuple:
    """返回 (等级, 说明)"""
    score = 100
    score -= len(r["errors"]) * 12
    score -= len(r["warns"]) * 3
    score -= len(r["spam"]) * 20
    score = max(0, min(100, score))

    if score >= 90:
        g = "A"
    elif score >= 75:
        g = "B"
    elif score >= 55:
        g = "C"
    elif score >= 35:
        g = "D"
    else:
        g = "F"
    return g, score


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------

def print_report(path: Path, r):
    g, score = health_grade(r)

    print()
    print(color("=" * 62, C_CYA))
    print(color("  SMAPI 日志分析报告", C_BOLD + C_CYA))
    print(color("=" * 62, C_CYA))
    print(f"  日志: {path}")
    if r["span"]:
        print(f"  时间跨度: {r['span'][0]} ~ {r['span'][1]}   共 {r['total']} 条")
    gc = C_GRN if g in ("A", "B") else (C_YEL if g in ("C",) else C_RED)
    print(f"  健康度: {color(g, gc + C_BOLD)}  ({score}/100)")

    ok = True

    # ---- 刷屏(最优先,最隐蔽) ----
    if r["spam"]:
        ok = False
        print()
        print(color("  ── 刷屏风暴(最危险) ──", C_RED + C_BOLD))
        for s in r["spam"][:8]:
            print(f"  {color('!!', C_RED)} [{s['source']}] 同一模式在 {s['window']}s 内出现 "
                  f"{color(str(s['count']), C_RED + C_BOLD)} 次 (首现 {s['at']}, 累计 {s['total']} 条)")
            print(f"     模式: {s['pattern'][:110]}")
        print(color("     → 高频重复通常意味着逻辑陷入循环:会抢占角色控制器,"
                    "让玩家按不动键、角色在地图间闪现。", C_GRY))

    # ---- 错误 ----
    if r["errors"]:
        ok = False
        print()
        print(color("  ── 错误 ──", C_RED + C_BOLD))
        grouped = collections.Counter()
        first_last = {}
        for e in r["errors"]:
            k = (e["source"], e["norm"])
            grouped[k] += 1
            if k not in first_last:
                first_last[k] = [e["hms"], e["hms"]]
            else:
                first_last[k][1] = e["hms"]
        for (src, pat), n in grouped.most_common(10):
            fl = first_last[(src, pat)]
            print(f"  {color('×' + str(n), C_RED)} [{src}] {pat[:105]}")
            print(f"      {fl[0]} ~ {fl[1]}")

    # ---- 警告 ----
    if r["warns"]:
        print()
        print(color("  ── 警告 ──", C_YEL + C_BOLD))
        grouped = collections.Counter()
        for e in r["warns"]:
            grouped[(e["source"], e["norm"])] += 1
        for (src, pat), n in grouped.most_common(8):
            print(f"  ×{n} [{src}] {pat[:105]}")

    # ---- 已知故障诊断 ----
    if r["known"]:
        print()
        print(color("  ── 已知故障诊断 ──", C_YEL + C_BOLD))
        for k in r["known"]:
            print(f"  ▸ {color(k['title'], C_BOLD)}  [{k['source']}] ×{k['count']} ({k['first']}~{k['last']})")
            print(f"      诊断: {k['diag']}")
            print(f"      建议: {color(k['fix'], C_GRN)}")
            print(f"      样例: {k['sample']}")
            print()

    # ---- Mod 活跃度 ----
    if r["mod_activity"]:
        print(color("  ── Mod 活跃度 ──", C_CYA))
        for mod, n in r["mod_activity"].most_common():
            bar = "█" * min(30, max(1, n // 5))
            print(f"  {mod:<18} {n:>5}  {color(bar, C_GRY)}")

    # ---- 任务健康 ----
    if r["task_health"]:
        print()
        print(color("  ── 任务健康 ──", C_CYA))
        for k in ["地图切换", "放弃任务", "寻路失败", "跨地点失败", "任务超时"]:
            if k in r["task_health"]:
                n = r["task_health"][k]
                mark = ""
                if k == "放弃任务" and n > 20:
                    mark = color("  ← 偏多,检查可达性", C_YEL)
                if k == "地图切换" and n > 200:
                    mark = color("  ← 异常高频,疑似循环", C_RED)
                print(f"  {k:<10} {n:>5}{mark}")

    print()
    if ok and not r["warns"]:
        print(color("  ✓ 未发现问题。", C_GRN + C_BOLD))
    elif ok:
        print(color("  ! 只有警告,可继续观察。", C_YEL))
    else:
        print(color("  ✗ 发现问题,见上文。", C_RED + C_BOLD))
    print()


def main():
    global MODS

    args = sys.argv[1:]
    as_json = "--json" in args
    since = None
    for i, a in enumerate(args):
        if a == "--since" and i + 1 < len(args):
            try:
                since = float(args[i + 1])
            except ValueError:
                pass
        # --mods A,B,C 覆盖 Mod 活跃度统计口径
        elif a == "--mods" and i + 1 < len(args):
            picked = [m.strip() for m in args[i + 1].split(",") if m.strip()]
            if picked:
                MODS = picked

    path = find_log_path(args)
    entries, _ = parse_log(path, since)
    r = analyze(entries)

    if as_json:
        g, score = health_grade(r)
        out = {
            "log": str(path),
            "health": g,
            "score": score,
            "total_lines": r["total"],
            "span": r["span"],
            "by_level": dict(r["by_level"]),
            "errors": len(r["errors"]),
            "warns": len(r["warns"]),
            "spam": r["spam"],
            "known_issues": r["known"],
            "mod_activity": dict(r["mod_activity"]),
            "task_health": dict(r["task_health"]),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print_report(path, r)

    g, _ = health_grade(r)
    return 1 if (r["errors"] or r["spam"]) else 0


if __name__ == "__main__":
    sys.exit(main())
