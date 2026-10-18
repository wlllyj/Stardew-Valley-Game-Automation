# -*- coding: utf-8 -*-
"""P3 第⑥步：长跑控制器 CLI —— 连续 N 个游戏日自主干农活。

【它和另外两个脚本的分工】
    tools\\run-plot.py     单块地的一次性验收（5x5 清障→开垦→播种→浇水），跑完就停；
    tools\\run-watchdog.py P2 的无人值守体检（只看健康，不动手）；
    tools\\run-longrun.py 本脚本：把上面两件事合起来**连续跑好几天**，每天自己决定该干什么。

【判据铁律】
一天算不算数，只看观测差分（`observe?detail=full`）：必须是我们**主动睡**过去的、当天没有硬失败、
睡前所有作物都浇过水。回执只是声明，一概不作证据。

【LLM 的位置】
默认**开启**（用户 2026-10-11 拍板："大模型改成长跑默认开启"）。它只在"边界"上被问一次
（新的一天 / 连续失败上升 / 代码策略换阶段）—— 它只说方向（哪片地、干什么），坐标永远由代码落；
非边界 0 次调用。想回到纯确定性策略就加 `--no-boundary-llm`。
用户 m01184 要求"大模型开始介入的时候告诉我一下"：长跑一开始会**显式播报**开/关状态。

用法：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\run-longrun.py --days 3 --size 5
    python tools\\run-longrun.py --days 1 --size 3 --max-minutes 25      # 先小跑一次看看
    python tools\\run-longrun.py --days 3 --no-boundary-llm              # 纯代码策略（不打网络）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.longrun import DEFAULT_LLM_MAX_TOKENS, LongRun  # noqa: E402

ZONE_PREFERS = ("most_tillable", "nearest", "empty")

#: 【task-35 / 0.7.47 快修】背包升级对话购买**默认关闭**的显式开启环境变量。
#: 为什么默认关闭：task-34 真机只读探针（commit 4524665）证明 `talk` 原语可用，但**背包升级
#: 对话没取到**——进 SeedShop 触发过场事件 3102768，相邻 talk 只拿到 "Sigh..."（非提问、无选项），
#: Town 事件 15389722 还 5 进 4 卡死。0.7.46 的 task-25 路径每天 gate 满足就会 goto SeedShop，
#: 会污染 smoke-0746 / A9 的五日连续证据，还有过场/卡死风险 ⇒ 入口未取证前一律默认关闭。
BACKPACK_UPGRADE_ENV = "AGENTFARM_ENABLE_BACKPACK_UPGRADE"
BACKPACK_ENV_TRUTHY = ("1", "true", "yes", "on")


def backpack_upgrade_enabled_from_env(env: dict[str, str] | None = None) -> bool:
    """读 `AGENTFARM_ENABLE_BACKPACK_UPGRADE`（1/true/yes/on 才算开）；未设置 ⇒ False（默认关）。"""
    values = os.environ if env is None else env
    raw = values.get(BACKPACK_UPGRADE_ENV, "")
    return str(raw).strip().lower() in BACKPACK_ENV_TRUTHY


def build_parser() -> argparse.ArgumentParser:
    """长跑 CLI 参数解析器（单独成函数是为了单测能直接验证参数透传）。"""
    ap = argparse.ArgumentParser(description="P3 长跑：连续几个游戏日自主清障/开垦/播种/浇水")
    ap.add_argument("--days", type=int, default=3, help="要求尾部连续这么多天都 VERIFIED（默认 3）")
    ap.add_argument("--size", type=int, default=5, help="作业区边长（默认 5 → 每片 25 格）")
    ap.add_argument("--zone-split", type=int, default=2, dest="zone_split",
                    help="把农场切成 N×N 个具名田区（默认 2）")
    ap.add_argument("--zone-prefer", default="most_tillable", choices=ZONE_PREFERS, dest="zone_prefer",
                    help="田区偏好：可锄最多 / 最近 / 空的优先（默认 most_tillable）")
    ap.add_argument("--boundary-llm", action="store_true", default=True, dest="boundary_llm",
                    help="边界决策交给大模型（**默认就是开的**；留着这个开关是为了显式表达意图）")
    ap.add_argument("--no-boundary-llm", action="store_false", dest="boundary_llm",
                    help="关掉大模型：全程走确定性策略（不碰网络，便于对比/排查）")
    ap.add_argument("--max-minutes", type=float, default=60.0, dest="max_minutes",
                    help="整个长跑的真实时间预算（默认 60 分钟）")
    ap.add_argument("--max-plots", type=int, default=10, dest="max_plots",
                    help="一天最多**新开**几片地（task-32 起是软配额：配额到顶但区内还有活时会继续干，"
                         "只是不再换新片；默认 10）")
    ap.add_argument("--max-days", type=int, default=None, dest="max_days",
                    help="最多试几个日报告（默认 = max(要求天数×2, 要求天数+2)；睡失败会重试同一天、"
                         "每次都算一个日报告 ⇒ 想留重试余量就显式调大，例如 --days 3 --max-days 9）")
    ap.add_argument("--min-stamina", type=float, default=12.0, dest="min_stamina",
                    help="体力低于这个值就收工睡觉（默认 12）")
    ap.add_argument("--sleep-at", type=int, default=2200, dest="sleep_at",
                    help="到几点就该睡了（默认 2200，游戏内时间）")
    ap.add_argument("--seed", default=None, help="固定用哪种种子（默认自动挑背包里最多的）")
    ap.add_argument("--buy-item", default="472", dest="buy_item", help="补种子的 ItemId（默认 472 防风草）")
    ap.add_argument("--seed-price", type=int, default=20, dest="seed_price",
                    help="补种子时用来判断钱够不够的单价（默认 20g）")
    ap.add_argument("--buy-count", type=int, default=10, dest="buy_count", help="每次补几个（默认 10）")
    ap.add_argument("--no-buy", action="store_true", dest="no_buy", help="禁止买种子（只用背包里的）")
    ap.add_argument("--enable-backpack-upgrade", action="store_true",
                    default=backpack_upgrade_enabled_from_env(),
                    dest="enable_backpack_upgrade",
                    help=("显式开启 Pierre 背包升级对话购买（默认关闭）。task-34 真机探针证明 talk 可用，"
                          "但背包升级对话没取到（进 SeedShop 触发过场事件 3102768）⇒ 默认关闭，避免每天"
                          "进店/过场卡死污染冒烟与 A9 证据；也可用环境变量 "
                          f"{BACKPACK_UPGRADE_ENV}=1 开启"))
    ap.add_argument("--journal", default=None, help="JSONL 账本路径（默认 logs\\longrun-<时间戳>.jsonl）")
    ap.add_argument("--report-dir", default="logs", dest="report_dir",
                    help="watchdog 判 STOP 时事故报告落哪个目录（默认 logs）")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_LLM_MAX_TOKENS, dest="max_tokens",
                    help=f"给慢脑的 token 上限（默认 {DEFAULT_LLM_MAX_TOKENS}：8192 在 run2 "
                         f"真机上仍被推理吃光过）")
    ap.add_argument("--timeout", type=float, default=180.0, help="桥的 HTTP 超时（默认 180s）")
    return ap


def main() -> int:
    args = build_parser().parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    stamp = time.strftime("%Y%m%d-%H%M%S")
    journal = Path(args.journal) if args.journal else Path("logs") / f"longrun-{stamp}.jsonl"

    if args.enable_backpack_upgrade:
        print("★ 背包升级对话购买已显式开启（--enable-backpack-upgrade / "
              f"{BACKPACK_UPGRADE_ENV}=1）：gate 满足时会 goto SeedShop → talk Pierre；"
              "task-34 探针表明背包升级入口未取证，注意过场事件 3102768 的风险。")
    else:
        print("i 背包升级对话购买默认关闭（task-34：背包升级入口未取证）⇒ 不发 goto/talk，"
              "只在 day_end 留 skip=disabled 痕迹；要启用加 --enable-backpack-upgrade。")

    if args.boundary_llm:
        print("★ 边界决策的大模型已开启（默认）：只在跨日/连续失败/换阶段时问一次，"
              "它只给方向（具名田区+任务），坐标由代码落；非边界不问。想关掉用 --no-boundary-llm。")
    else:
        print("i 边界决策的大模型已关闭（--no-boundary-llm）：全程确定性策略，不发网络请求。")

    print(f"[run] 目标：尾部连续 {args.days} 天 VERIFIED；作业区 {args.size}×{args.size}；"
          f"田区偏好 {args.zone_prefer}；LLM {'开' if args.boundary_llm else '关'}；"
          f"token 上限 {args.max_tokens}；账本 {journal}")

    run = LongRun(
        client_factory=lambda: BridgeClient(timeout=args.timeout),
        target_days=args.days,
        plot_size=args.size,
        zone_split=args.zone_split,
        zone_prefer=args.zone_prefer,
        llm_enabled=args.boundary_llm,
        llm_max_tokens=args.max_tokens,
        seed=args.seed,
        buy_item=args.buy_item,
        seed_price=args.seed_price,
        buy_count=args.buy_count,
        allow_buy=not args.no_buy,
        backpack_upgrade_enabled=args.enable_backpack_upgrade,
        min_stamina=args.min_stamina,
        sleep_at=args.sleep_at,
        max_minutes=args.max_minutes,
        max_days=args.max_days,
        max_plots_per_day=args.max_plots,
        report_dir=args.report_dir,
        journal_path=journal,
    )
    try:
        code = run.run()
    except BridgeError as exc:
        print(f"× 桥出错：{exc}")
        return 2
    except KeyboardInterrupt:  # pragma: no cover - 人工打断
        print("\n× 人工打断（Ctrl+C）：账本已经写到磁盘，可据此复盘")
        return 130

    print()
    for d in run.days:
        print(f"  {d.day_text}  {d.ended_by:<11} 阶段 {d.stages_seen or '无'} "
              f"做成 {d.ok_steps} 跳过 {d.skipped_steps} 失败 {d.failed_steps} "
              f"→ {'VERIFIED' if d.verified else 'needs_review'}")
        for note in d.notes[:6]:
            print(f"      · {note}")
    print(f"[run] 账本：{journal}")
    print(json.dumps({"code": code, "verified_streak": run.summary.get("verified_streak"),
                      "target_days": run.summary.get("target_days"),
                      "actions": run.summary.get("actions"),
                      "minutes": run.summary.get("minutes")}, ensure_ascii=False))
    verdict = "VERIFIED" if code == 0 else ("起不来" if code == 2 else "needs_review")
    print(f"终态：{verdict}（判据：observe?detail=full 的 tiles[]/clock 差分；回执一律不作证据）")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
