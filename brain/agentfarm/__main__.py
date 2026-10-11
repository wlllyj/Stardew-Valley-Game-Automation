"""脑的命令行入口（P2 里程碑 A）。

用法（在 brain 目录下）：
    python -m agentfarm doctor          # 医生检查：能不能连上、看到什么、版本对不对
    python -m agentfarm observe         # 打印一行世界摘要
    python -m agentfarm observe --full  # 打印完整快照 JSON
    python -m agentfarm health          # 只探活
    python -m agentfarm noop            # 发一个不碰游戏的动作，验证 exec 链路
    python -m agentfarm move 64 15      # 让角色走到农场出口（真实移动，可被打断）
    python -m agentfarm watch           # 每 2 秒打印一行世界摘要（真机测试时用眼睛看）

设计原则：**只报告事实，不美化失败**。任何一步失败都要能让用户一眼看出卡在哪一环。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from .bridge import (
    BASELINE_GAME_VERSION,
    BASELINE_SMAPI_VERSION,
    SCHEMA_WORLD,
    BridgeClient,
    BridgeError,
    default_bridge_json_path,
    load_bridge_info,
    pid_alive,
)
from .llm import (
    ENV_API_KEY,
    LlmError,
    chat,
    default_model,
    list_models,
    load_api_key,
    secrets_dir,
)
from .winfocus import ensure_game_foreground, find_game_window, foreground_window

SEASON_ZH = {"spring": "春", "summer": "夏", "fall": "秋", "winter": "冬"}

OK = "[OK]  "
FAIL = "[FAIL]"
WARN = "[警告]"


def force_utf8_console() -> None:
    """把 stdout/stderr 钉成 UTF-8。

    本机实测：Python 在管道/重定向场景下默认用系统 locale 编码（实测为 cp1252），
    一打印中文就抛 UnicodeEncodeError 直接崩掉。这是环境级陷阱，必须在入口处修掉，
    而不是要求用户记得设 PYTHONIOENCODING（详见 docs/00-开发日志.md 条目 008）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # 非标准流（例如已被替换）时静默跳过
            pass


def fmt_time(time_of_day: Any) -> str:
    """1230 -> 12:30"""
    try:
        t = int(time_of_day)
    except (TypeError, ValueError):
        return "??:??"
    return f"{t // 100:02d}:{t % 100:02d}"


def fmt_clock(clock: dict[str, Any] | None) -> str:
    if not clock:
        return "无时间信息"
    season = SEASON_ZH.get(str(clock.get("season")), str(clock.get("season")))
    return (
        f"第{clock.get('year')}年 {season}{clock.get('day')}日 "
        f"{fmt_time(clock.get('timeOfDay'))} {clock.get('weather', '')}"
    )


def fmt_observe_line(obs: dict[str, Any]) -> str:
    """一行世界摘要——真机测试时靠它一眼看出世界在不在动。"""
    if not obs.get("hasSaveLoaded"):
        return f"{fmt_clock(None)} | 尚未加载存档（标题界面）"
    player = obs.get("player") or {}
    loc = obs.get("location") or {}
    farm = obs.get("farm") or {}
    live = obs.get("liveness") or {}
    tile = player.get("tile") or ["?", "?"]

    parts = [
        fmt_clock(obs.get("clock")),
        f"{player.get('location')}({tile[0]},{tile[1]})",
        f"体力{player.get('stamina'):.0f}/{player.get('maxStamina'):.0f}"
        if isinstance(player.get("stamina"), (int, float))
        else "体力?",
        f"血{player.get('health')}",
        f"钱{player.get('money')}g",
    ]
    if loc.get("isFarm") or farm.get("loaded"):
        parts.append(
            "农场[草{weeds}/石{stones}/枝{twigs}/树{trees} 耕地{hoeDirt} 作物{crops}]".format(
                weeds=farm.get("weeds"), stones=farm.get("stones"), twigs=farm.get("twigs"),
                trees=farm.get("trees"), hoeDirt=farm.get("hoeDirt"), crops=farm.get("crops"),
            )
        )
    advancing = "世界推进中" if live.get("worldAdvancing") else "**世界未推进**"
    parts.append(f"| seq={obs.get('worldSeq')} {advancing}({live.get('secondsSinceClockMoved')}s)")
    return "  ".join(parts)


def cmd_doctor(args: argparse.Namespace) -> int:
    """医生检查：把"连不上"拆成可定位的若干步，逐条给结论。"""
    path = default_bridge_json_path()
    print(f"== AgentFarm 医生检查 ==")
    print(f"bridge.json 期望位置：{path}")
    failures = 0
    warnings = 0

    # 1) 发现文件
    try:
        info = load_bridge_info(path)
    except BridgeError as exc:
        print(f"{FAIL} 读取 bridge.json 失败：{exc}")
        print("      → 排查顺序：游戏是否用 SMAPI 启动 → Mod 是否在 Mods\\AgentFarm.Bridge\\ → 是否已加载存档")
        return 1
    print(f"{OK} 找到 bridge.json")
    print(f"      端口 {info.port} | pid {info.pid} | Mod {info.mod_version} | "
          f"游戏 {info.game_version} | SMAPI {info.smapi_version} | 启动于 {info.started_at}")

    # 文件存在 ≠ 游戏在跑：实测游戏退出后 bridge.json 可能残留（协议要求清理但没清）
    alive = pid_alive(info.pid)
    if alive is False:
        print(f"{WARN} bridge.json 里的 pid {info.pid} 已经不存在 —— 这是上一次运行留下的**陈旧文件**。")
        print(f"      游戏可能已经退出，或 Mod 的退出清理没生效。")
        print(f"      （脑不会因此误判：后面的 HTTP 探测仍会独立失败，报 'unreachable_bridge'）")
        warnings += 1

    # 2) 版本基线
    if info.game_version != BASELINE_GAME_VERSION:
        print(f"{WARN} 游戏版本 {info.game_version} ≠ 基线 {BASELINE_GAME_VERSION}（可能已更新，需重跑验收）")
        warnings += 1
    if info.smapi_version != BASELINE_SMAPI_VERSION:
        print(f"{WARN} SMAPI 版本 {info.smapi_version} ≠ 基线 {BASELINE_SMAPI_VERSION}")
        warnings += 1

    client = BridgeClient(info)

    # 3) 探活
    try:
        health = client.health(timeout=3.0)
    except BridgeError as exc:
        print(f"{FAIL} /v1/health 不可达：{exc}")
        return 1
    rt = health.get("runtime") or {}
    srv = health.get("server") or {}
    print(f"{OK} /v1/health 可达（已服务 {srv.get('requestsServed')} 个请求，"
          f"运行 {rt.get('uptimeSeconds')}s，worldSeq={rt.get('worldSeq')}）")
    if rt.get("onTitleScreen"):
        print(f"{WARN} 当前在标题界面：请先加载存档，否则拿不到世界快照")
        warnings += 1

    # 4) 快照 + 令牌鉴权（observe 必须带令牌，能成功说明令牌链路通）
    try:
        obs = client.observe("summary", timeout=8.0)
    except BridgeError as exc:
        print(f"{FAIL} /v1/observe 失败：{exc}")
        return 1
    if obs.get("schema") != SCHEMA_WORLD:
        print(f"{FAIL} observe schema 异常：{obs.get('schema')!r}")
        failures += 1
    else:
        print(f"{OK} /v1/observe 成功（schema={obs.get('schema')}，鉴权链路正常）")
    print(f"      {fmt_observe_line(obs)}")

    live = obs.get("liveness") or {}
    if obs.get("hasSaveLoaded") and not live.get("worldAdvancing"):
        print(f"{WARN} 世界似乎没有在推进（secondsSinceClockMoved={live.get('secondsSinceClockMoved')}）。"
              f"若游戏窗口失去焦点，检查是否启用了「失焦暂停」")
        warnings += 1

    # 5) exec 链路（noop 不碰游戏）
    try:
        res = client.noop()
        print(f"{OK} /v1/exec 链路正常（noop 返回 status={res.get('status')}，耗时 {res.get('elapsedMs')}ms）")
    except BridgeError as exc:
        print(f"{FAIL} /v1/exec 失败：{exc}")
        failures += 1

    print()
    if failures:
        print(f"结论：{failures} 项失败，{warnings} 项警告 —— 先修失败项。")
        return 1
    print(f"结论：链路全部打通{'（有 %d 项警告，见上）' % warnings if warnings else ''}。可以开始做动作测试。")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(BridgeClient().health(), ensure_ascii=False, indent=2))
        return 0
    except BridgeError as exc:
        print(f"{FAIL} {exc}")
        return 1


def cmd_observe(args: argparse.Namespace) -> int:
    try:
        obs = BridgeClient().observe("full" if args.full else "summary", timeout=10.0)
    except BridgeError as exc:
        print(f"{FAIL} {exc}")
        return 1
    if args.json:
        print(json.dumps(obs, ensure_ascii=False, indent=2))
    else:
        print(fmt_observe_line(obs))
    return 0


def cmd_noop(args: argparse.Namespace) -> int:
    try:
        print(json.dumps(BridgeClient().noop(), ensure_ascii=False, indent=2))
        return 0
    except BridgeError as exc:
        print(f"{FAIL} {exc}")
        return 1


def cmd_focus(args: argparse.Namespace) -> int:
    """把游戏窗口拉到前台。

    为什么需要：实测（2026-10-11）游戏**失焦时角色不会被控制器驱动** ——
    世界时间照常流逝，但 move_to 10/10 失败、角色一动不动；回到前台后 5/5 成功。
    所以任何"会移动角色"的操作之前都必须确保游戏在前台。
    """
    hwnd = find_game_window()
    if hwnd is None:
        print(f"{FAIL} 找不到《星露谷》窗口（游戏没启动？）")
        return 1
    print(f"      游戏窗口 hwnd={hwnd}，当前前台 hwnd={foreground_window()}")
    ok = ensure_game_foreground()
    print(f"{OK if ok else FAIL} {'游戏已在前台' if ok else '抢焦点失败'}")
    return 0 if ok else 1


def cmd_move(args: argparse.Namespace) -> int:
    # 实测教训：失焦时控制器不驱动角色 —— 移动前先把游戏拉到前台
    if not args.no_focus:
        if not ensure_game_foreground(verbose=False):
            print(f"{WARN} 未能把游戏拉到前台；失焦时角色可能不会移动（实测会卡死检测失败）")

    client = BridgeClient()
    try:
        obs = client.observe("summary", timeout=8.0)
    except BridgeError as exc:
        print(f"{FAIL} 取快照失败：{exc}")
        return 1
    if not obs.get("hasSaveLoaded"):
        print(f"{FAIL} 尚未加载存档，无法移动")
        return 1
    print(f"移动前：{fmt_observe_line(obs)}")
    seq = obs.get("worldSeq")
    try:
        res = client.move_to(args.x, args.y, timeout_ms=args.timeout_ms, based_on_seq=seq)
    except BridgeError as exc:
        print(f"{FAIL} move_to 失败：{exc}")
        return 1
    print(f"{OK} move_to 返回 status={res.get('status')} 耗时 {res.get('elapsedMs')}ms "
          f"worldSeq {res.get('worldSeqBefore')}→{res.get('worldSeqAfter')}")
    try:
        after = client.observe("summary", timeout=8.0)
        print(f"移动后：{fmt_observe_line(after)}")
        tile = (after.get("player") or {}).get("tile")
        if tile and list(tile) == [args.x, args.y]:
            print(f"{OK} 到达目标 ({args.x},{args.y})")
        else:
            print(f"{WARN} 未在目标格：期望 ({args.x},{args.y})，实际 {tile}")
    except BridgeError as exc:
        print(f"{WARN} 移动后取快照失败：{exc}")
    return 0


def cmd_llm_check(args: argparse.Namespace) -> int:
    """大模型检查：密钥从哪来、模型名是否真实存在、一次最小调用的耗时与用量。

    注意：**绝不打印密钥本身**，只报告来源与长度。
    """
    print("== 大模型（慢脑）检查 ==")
    source = "环境变量 " + ENV_API_KEY if (os.environ.get(ENV_API_KEY) or "").strip() else \
             f"文件 {secrets_dir() / 'deepseek.key'}"
    try:
        key = load_api_key()
    except LlmError as exc:
        print(f"{FAIL} {exc}")
        return 1
    print(f"{OK} 密钥来源：{source}（长度 {len(key)}，前缀 {key[:6]}…，内容不打印）")
    print(f"      模型：{default_model()}")

    try:
        models = list_models()
        print(f"{OK} 端点可用模型：{', '.join(models)}")
        if default_model() not in models:
            print(f"{WARN} 默认模型 {default_model()} 不在模型列表里，调用可能失败")
    except LlmError as exc:
        print(f"{FAIL} 查询模型列表失败：{exc}")
        return 1

    try:
        res = chat([{"role": "user", "content": "只回复两个字：就绪"}], max_tokens=512)
    except LlmError as exc:
        print(f"{FAIL} 调用失败：{exc}")
        return 1
    print(f"{OK} 调用成功：{res.elapsed_ms}ms，{res.usage}，finish={res.finish_reason}，"
          f"尝试 {res.attempts} 次")
    print(f"      回答：{res.content.strip()[:80]!r}")
    if res.reasoning:
        print(f"      （推理模型，另有 {len(res.reasoning)} 字思考过程，默认不打印）")
    print()
    print("结论：慢脑可用。注意 deepseek-flash 是推理模型，max_tokens 给小了会出现空回答。")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """临时问一句，用于人工验证提示词与模型行为。"""
    try:
        res = chat([{"role": "user", "content": args.question}],
                   max_tokens=args.max_tokens, temperature=None)
    except LlmError as exc:
        print(f"{FAIL} {exc}")
        return 1
    if args.reasoning and res.reasoning:
        print("--- 思考过程 ---")
        print(res.reasoning)
        print("--- 回答 ---")
    print(res.content)
    print(f"\n[{res.model} {res.elapsed_ms}ms {res.usage}]", file=sys.stderr)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """真机测试时的"眼睛"：每 N 秒打一行，什么时候世界不动了一眼就能看出来。"""
    client = BridgeClient()
    print(f"每 {args.interval}s 打印一次世界摘要，Ctrl+C 退出")
    last_seq = None
    try:
        while True:
            try:
                obs = client.observe("summary", timeout=8.0)
                seq = obs.get("worldSeq")
                marker = "" if last_seq is None else ("" if seq != last_seq else "  <-- seq 未变")
                print(f"{time.strftime('%H:%M:%S')}  {fmt_observe_line(obs)}{marker}")
                last_seq = seq
            except BridgeError as exc:
                print(f"{time.strftime('%H:%M:%S')}  {FAIL} {exc}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已退出 watch")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentfarm", description="星露谷自动化 · 脑（P2 里程碑 A）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="医生检查：连通性 / 版本 / 快照 / exec 链路").set_defaults(func=cmd_doctor)
    sub.add_parser("health", help="只探活").set_defaults(func=cmd_health)

    o = sub.add_parser("observe", help="打印世界快照")
    o.add_argument("--full", action="store_true", help="取 full 明细")
    o.add_argument("--json", action="store_true", help="打印完整 JSON")
    o.set_defaults(func=cmd_observe)

    sub.add_parser("noop", help="发一个不碰游戏的动作，验证 exec 链路").set_defaults(func=cmd_noop)

    m = sub.add_parser("move", help="让角色走到指定格（真实移动）")
    m.add_argument("x", type=int)
    m.add_argument("y", type=int)
    m.add_argument("--timeout-ms", type=int, default=8000, dest="timeout_ms")
    m.add_argument("--no-focus", action="store_true", dest="no_focus",
                   help="不要把游戏拉到前台（用于验证失焦行为）")
    m.set_defaults(func=cmd_move)

    sub.add_parser("focus", help="把《星露谷》窗口拉到前台").set_defaults(func=cmd_focus)

    w = sub.add_parser("watch", help="持续打印世界摘要")
    w.add_argument("--interval", type=float, default=2.0)
    w.set_defaults(func=cmd_watch)

    sub.add_parser("llm-check", help="检查大模型密钥与连通性（不打印密钥）").set_defaults(func=cmd_llm_check)

    a = sub.add_parser("ask", help="临时问慢脑一句（人工验证提示词）")
    a.add_argument("question")
    a.add_argument("--max-tokens", type=int, default=8192, dest="max_tokens")
    a.add_argument("--reasoning", action="store_true", help="同时打印思考过程")
    a.set_defaults(func=cmd_ask)
    return p


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
