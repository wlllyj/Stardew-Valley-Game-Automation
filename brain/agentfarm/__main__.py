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
from typing import Any, Callable

from .bridge import (
    BASELINE_GAME_VERSION,
    BASELINE_SMAPI_VERSION,
    MOD_VERSION_EXPECTED,
    SCHEMA_WORLD,
    BridgeClient,
    BridgeError,
    BridgeInfo,
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
from .watchdog import assess, format_findings, verdict, write_stop_report
# 规划层（P3 ⑤）：模块导入本身**不发任何请求**，LLM 调用藏在 planner.default_llm_chat 里延迟导入。
from .planner import (
    BOUNDARY_NEW_DAY,
    BOUNDARY_RECOVERY,
    BOUNDARY_TASK_CHANGE,
    Brief,
    BoundaryPlanner,
    PlannerState,
    farm_areas,
)

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
    if info.mod_version != MOD_VERSION_EXPECTED:
        print(f"{WARN} Mod 版本 {info.mod_version} ≠ 期望 {MOD_VERSION_EXPECTED}"
              f"（Mods\\ 里已经是新版，但游戏进程加载的还是旧 dll —— 需重启游戏）")
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
        print(f"{WARN} observe 返回 schema={obs.get('schema')!r}，期望 {SCHEMA_WORLD!r}")
        print(f"      → 游戏里装的 Mod 还是升级前的版本（dll 被游戏锁住，必须重启游戏才能换）。"
              f"新字段（如 location.furniture[]）不可用，其余功能正常。")
        warnings += 1
    else:
        print(f"{OK} /v1/observe 成功（schema={obs.get('schema')}，鉴权链路正常）")
    print(f"      {fmt_observe_line(obs)}")

    live = obs.get("liveness") or {}
    game = obs.get("game") or {}
    # ⚠️ `windowActive` / `pauseWhenOutOfFocus` / `oofFixCount` 只在 **/v1/health** 的 game 段里，
    #    observe 的 game 段是 shouldTimePass/paused，**没有**它们。
    #    早期版本这里读的是 `obs["game"]["windowActive"]`（永远是 None），于是不管真实焦点如何
    #    都会打印"窗口在前台却没推进" —— 诊断信息一旦撒谎，比没有诊断更糟。
    #
    #    v0.5.0 起的真机制（IL 实证，docs\_il-oof-pause.md）：`Game1._update` IL_0444–IL_0480 在
    #    "窗口不活跃 且 pauseWhenOutOfFocus==true" 时直接 ret，跳过 UpdateGameClock 与
    #    UpdateLocations（含 PathFindController）—— 这才是"时钟不走 + 角色不动"的唯一门。
    #    Mod 每帧把该选项扳回 false，所以**失焦不再是合理原因**。
    hgame = health.get("game") or {}
    active = hgame.get("windowActive")
    oof = hgame.get("pauseWhenOutOfFocus")
    oof_fixes = hgame.get("oofFixCount")
    if obs.get("hasSaveLoaded") and not live.get("worldAdvancing"):
        if oof is True:
            print(f"{WARN} 世界没在推进，而 `pauseWhenOutOfFocus` **此刻就是 true** —— 这就是那道门"
                  f"（Game1._update IL_0444-IL_0480）：时钟与角色更新整段被跳过。")
            print(f"      v0.5.0 应每帧把它扳回关闭；当前 oofFixCount={oof_fixes}。"
                  f"若游戏里装的还是 0.4.0，重启游戏装新版即可。")
        elif oof is None:
            print(f"{WARN} 世界没在推进，且 health 里**没有** `pauseWhenOutOfFocus` 字段"
                  f"（Mod < 0.5.0，字段是 0.5.0 新增的）。")
            if active is False:
                print(f"      窗口不在前台 —— 这正是 0.4.0 及更早版本的已知行为（失焦即冻结，"
                      f"因为 GameLaunched 里那次赋值被读档换掉的 Options 实例冲掉了）。装 0.5.0 即可。")
            else:
                print(f"      窗口在前台却也停着，需要人工排查"
                      f"（secondsSinceClockMoved={live.get('secondsSinceClockMoved')}）")
        elif active is False:
            print(f"{WARN} 世界没在推进（窗口不在前台），但 `pauseWhenOutOfFocus=false`、"
                  f"oofFixCount={oof_fixes} —— v0.5.0 起**失焦不该再让世界停摆**，这是新问题，需要人工排查"
                  f"（secondsSinceClockMoved={live.get('secondsSinceClockMoved')}，"
                  f"shouldTimePass={game.get('shouldTimePass')}，paused={game.get('paused')}）")
        elif active is True:
            print(f"{WARN} 世界没在推进，窗口**确实**在前台、`pauseWhenOutOfFocus=false` —— 需要人工排查"
                  f"（secondsSinceClockMoved={live.get('secondsSinceClockMoved')}，"
                  f"shouldTimePass={game.get('shouldTimePass')}，paused={game.get('paused')}）")
        else:
            print(f"{WARN} 世界没在推进，且**拿不到 windowActive**（Mod 太旧或字段改名），无法区分原因"
                  f"（secondsSinceClockMoved={live.get('secondsSinceClockMoved')}）")
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

    【历史与现状，别记错】2026-10-11 上午实测：失焦时角色不被 `PathFindController`
    驱动，move_to 10/10 失败；当时**误以为**"世界时间照常流逝、只是角色不动"。
    当晚的 A/B 与 IL 定因把两条都推翻了：失焦时**时钟与角色一起停**，同一个门
    （`Game1._update` IL_0444–IL_0480 的提前返回，由 `pauseWhenOutOfFocus` 控制）。
    Mod v0.5.0 起每帧把它扳成 false，**焦点已不再是移动的前提**。
    所以本命令现在是**可选兜底**（也是为了让真机记录与历史可比），不再是必需步骤。
    """
    hwnd = find_game_window()
    if hwnd is None:
        print(f"{FAIL} 找不到《星露谷》窗口（游戏没启动？）")
        return 1
    print(f"      游戏窗口 hwnd={hwnd}，当前前台 hwnd={foreground_window()}")
    ok = ensure_game_foreground()
    print(f"{OK if ok else FAIL} {'游戏已在前台' if ok else '抢焦点失败'}")
    return 0 if ok else 1


def cmd_triage(args: argparse.Namespace) -> int:
    """无人值守体检：一次取 health + observe，按 watchdog 的判据给结论。

    退出码就是结论：**0=ok / 1=warn / 2=stop**，这样外部脚本能直接拿它当门禁。
    stop 时会顺手把事故报告写到 `logs/stops/`（人不在时唯一的"喊人"方式）。
    """
    client = BridgeClient(timeout=10.0)
    try:
        h = client.health()
        obs = client.observe("summary", timeout=10.0)
    except BridgeError as exc:
        print(f"{FAIL} 连不上或快照取不到：{exc}")
        return 2
    findings = assess(h, obs, mod_version_expected=MOD_VERSION_EXPECTED)
    print(format_findings(findings))
    v = verdict(findings)
    if v == "stop":
        path = write_stop_report(findings, health=h, observe=obs, note="agentfarm triage")
        print(f"🔴 判定 stop：无人值守必须停下（脑自己修不了）。事故报告：{path}")
        return 2
    if v == "warn":
        print("⚠️ 判定 warn：可以继续，但上面的条目应先处理。")
        return 1
    print("✅ 判定 ok：世界在推进、失焦暂停已关闭、没有挡路弹窗。")
    return 0


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
    if args.allow_bed:
        print(f"{WARN} --allow-bed：已显式解禁床格，走到床上会触发睡觉弹窗（随后请用 dismiss_modal 收尾）")
    try:
        res = client.move_to(args.x, args.y, timeout_ms=args.timeout_ms, based_on_seq=seq,
                             allow_bed=args.allow_bed)
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


def print_hops(payload: dict[str, Any], prefix: str = "  ") -> None:
    """打印 move_to_location 回执里的 path / hops（成功与失败回执都带）。"""
    path = payload.get("path") or []
    hops = payload.get("hops") or []
    if path:
        print(f"{prefix}path：{' → '.join(str(p) for p in path)}")
    for i, h in enumerate(hops, 1):
        print(
            f"{prefix}hop{i}：{h.get('from')} → {h.get('to')} "
            f"result={h.get('result')} arrivedAt={h.get('arrivedAt')} "
            f"source={h.get('sourceTile')} landing={h.get('landingTile')} "
            f"used={h.get('usedTile')} {h.get('ms')}ms"
        )
        if h.get("detail"):
            print(f"{prefix}        detail：{h.get('detail')}")


def cmd_goto(args: argparse.Namespace) -> int:
    """跨地点移动（move_to_location）：走到另一个地点，可选再走到该地点的某一格。

    【为什么脑不自己规划路线】路线一律由 Mod 侧按**游戏真值的 warp 图** BFS 得出
    （架构 §5.2.1 禁止硬编码地名/坐标）。脑只声明"我要去哪个地点"。
    """
    if not args.no_focus:
        # v0.5.0 起失焦不再冻结世界（每帧强制 pauseWhenOutOfFocus=false），这里只作兜底。
        if not ensure_game_foreground(verbose=False):
            print(f"{WARN} 未能把游戏拉到前台（不影响世界推进，仅少一层兜底）")

    client = BridgeClient()
    try:
        obs = client.observe("summary", timeout=8.0)
    except BridgeError as exc:
        print(f"{FAIL} 取快照失败：{exc}")
        if getattr(exc, "status", "") in ("no_save", "unreachable_bridge"):
            print(f"     提示：若停在标题界面，先跑 `agentfarm load` 读档")
        return 1
    if not obs.get("hasSaveLoaded"):
        print(f"{FAIL} 尚未加载存档，无法移动；若停在标题界面请先跑 `agentfarm load`")
        return 1

    print(f"移动前：{fmt_observe_line(obs)}")
    tile = tuple(args.tile) if args.tile else None
    if args.allow_bed:
        print(f"{WARN} --allow-bed：落地格若为床会触发睡觉弹窗（随后请用 dismiss_modal 收尾）")

    try:
        res = client.move_to_location(
            args.location,
            tile=tile,
            timeout_ms=args.timeout_ms,
            based_on_seq=obs.get("worldSeq"),
            allow_bed=args.allow_bed,
        )
    except BridgeError as exc:
        payload = getattr(exc, "payload", None) or {}
        print(f"{FAIL} move_to_location 失败（status={getattr(exc, 'status', '?')}）：{exc}")
        print_hops(payload)
        return 1

    print(f"{OK} move_to_location status={res.get('status')} 耗时 {res.get('elapsedMs')}ms "
          f"reachedLocation={res.get('reachedLocation')}")
    print_hops(res)

    try:
        after = client.observe("summary", timeout=8.0)
        print(f"移动后：{fmt_observe_line(after)}")
        loc = (after.get("player") or {}).get("location") or (after.get("location") or {}).get("name")
        if loc and loc == args.location:
            print(f"{OK} 地点已到达 {args.location}")
        else:
            print(f"{WARN} 观测地点 {loc!r} 与目标 {args.location!r} 不一致（以观测为准）")
        if tile:
            got = (after.get("player") or {}).get("tile")
            if got and list(got) == list(tile):
                print(f"{OK} 已在目标格 {tuple(tile)}")
            else:
                print(f"{WARN} 未在目标格：期望 {tuple(tile)}，实际 {got}")
    except BridgeError as exc:
        print(f"{WARN} 移动后取快照失败：{exc}")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    """从标题界面读档（load_save）。

    【为什么这是自主性的前提】换 Mod dll 必须重启游戏，重启后停在标题界面；标题界面上
    唯一的正常入口是"点 Continue" —— 那属于伪造输入（硬纪律①禁止）。无人值守长跑也必须
    能从崩溃/重启里自己爬起来。Mod 侧调用的是游戏自己的 `SaveGame.Load(存档名)`。
    """
    client = BridgeClient()

    # health 在标题界面也能答（不依赖存档），先拿它判断"现在到底在不在存档里"。
    try:
        h = client.health()
    except BridgeError as exc:
        print(f"{FAIL} 连不上桥：{exc}")
        return 1
    rt = h.get("runtime") or {}
    in_save = bool(rt.get("hasSaveLoaded"))
    print(f"Mod {h.get('modVersion')} | hasSaveLoaded={in_save} onTitleScreen={rt.get('onTitleScreen')}")

    if in_save and not args.force:
        print(f"{WARN} 当前已经在存档里，拒绝读档：读档会丢掉当天进度（游戏只在睡觉时落盘）。")
        print(f"      确实要丢弃当前进度重新读档，请加 --force。")
        return 1

    try:
        res = client.load_save(args.save, force=args.force, timeout_ms=args.timeout_ms)
    except BridgeError as exc:
        print(f"{FAIL} load_save 失败（status={getattr(exc, 'status', '?')}）：{exc}")
        return 1

    print(f"{OK} 已进入存档 {res.get('save')}：地点 {res.get('reachedLocation')} "
          f"格 {res.get('tile')}（{res.get('elapsedMs')}ms）")
    try:
        print(f"读档后：{fmt_observe_line(client.observe('summary', timeout=8.0))}")
    except BridgeError as exc:
        print(f"{WARN} 读档后取快照失败：{exc}")
        return 1
    return 0


def _taskkill(pid: int) -> bool:
    """强杀进程（仅 Windows；别的平台返回 False）。**兜底用**，正常路径不该走到。"""
    if os.name != "nt":
        return False
    return os.system(f'taskkill /PID {int(pid)} /F >NUL 2>&1') == 0


def _bridge_responds(client: BridgeClient, timeout: float = 2.0) -> bool:
    """桥还答话吗（`health()`）——`pid` 不可用时的**独立判活证据**。只读，不驱动游戏。"""
    try:
        client.health(timeout=timeout)
        return True
    except BridgeError:
        return False


def await_game_exit(
    info: BridgeInfo,
    seconds: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    bridge_responds: Callable[[], bool] | None = None,
    kill: Callable[[int], bool] = _taskkill,
    out: Callable[[str], None] = print,
) -> int:
    """等游戏进程真的消失（最多 `seconds` 秒），超时则强杀。返回 CLI 退出码。

    `quit_game` 的回执本身可能收不到（Mod 正在退出），所以判活必须**三态**——**`None` 不是 `False`**：
      * `True`  ⇒ 确实还活着 → 继续等；
      * `False` ⇒ 确实不在了 → 报"已退出"并返回 0；
      * `None`  ⇒ **不知道**（`bridge.json` 缺 `pid`，或平台不支持）= 既不是"活着"，也**不是"已退出"**：
        绝不走"已退出"分支。此时改用 `bridge_responds()`（HTTP `health()`）取独立证据——桥还在应答
        ⇒ 进程显然还活着，继续等；桥不应答 ⇒ 也**只是"没有证据"**，照样把时间等完。
    超时后：`pid` 是正整数 → 强杀并返回 0；**`pid` 未知 → 老实报"存活未知、无法强杀"并返回 1**
    （本模块的原则是"只报告事实，不美化失败"：没能确认进程消失就不能报成功）。

    【为什么需要这个函数】旧写法 `if pid_alive(info.pid) is not True:` 把 `None` 一并当成"已退出"，
    于是 `bridge.json` 缺 `pid` 时会**立刻** `return 0`，跳过整个强杀兜底 —— 无人值守时游戏可能还挂着，
    部署脚本却以为它已经关了。拆成纯函数也是为了能用**行为**断言测它（是否强杀/返回码），
    而不是只断言日志文本。
    """
    pid = info.pid
    ticks = max(0, int(seconds))
    noted_unknown = False
    for _ in range(ticks):
        alive = pid_alive(pid)
        if alive is False:
            out(f"{OK} 游戏进程（pid {pid}）已退出")
            return 0
        if alive is None and not noted_unknown:
            noted_unknown = True                      # 只解释一次，避免刷屏
            if bridge_responds is not None and bridge_responds():
                out(f"{WARN} 无法按 pid 判活（bridge.json 里可用的 pid = {pid!r}），但桥仍在应答 "
                    f"⇒ 进程显然还活着，继续等待")
            else:
                out(f"{WARN} 无法按 pid 判活（bridge.json 里可用的 pid = {pid!r}），桥也没应答："
                    f"存活未知，**不等于**已退出，继续等满 {ticks}s")
        sleep(1)
    if pid is None:
        out(f"{WARN} 等了 {ticks}s 仍无法判定游戏进程是否退出（bridge.json 缺 pid，无法强杀）："
            f"请手动确认进程是否还在")
        return 1
    out(f"{WARN} 等了 {ticks}s 进程仍在（pid {pid}），强杀")
    kill(int(pid))
    return 0


def cmd_shutdown(args: argparse.Namespace) -> int:
    """让游戏**自己退出**（quit_game）。

    【为什么这是一条正经技能】换 Mod dll 必须重启游戏；而无人值守时没人去点"退出"。
    与 `load`（自己读档）配对，才构成"发现问题 → 自己关 → 换 dll → 自己开 → 自己读档"的闭环：
    见 `tools\\deploy-mod.py`。
    """
    client = BridgeClient()
    try:
        res = client.quit_game()
    except BridgeError as exc:
        print(f"{FAIL} quit_game 失败（status={getattr(exc, 'status', '?')}）：{exc}")
        return 1

    print(f"{OK} {res.get('status')}：{res.get('reason')}")
    if args.force_after and not args.no_force:
        # 兜底：等进程真的消失，超时就强杀（先备份存档是调用方的责任）。
        # 三态判活见 await_game_exit —— pid 未知时**绝不**当成"已退出"。
        info = load_bridge_info()
        return await_game_exit(
            info,
            int(args.force_after),
            bridge_responds=lambda: _bridge_responds(client),
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """无人值守**监督循环**：每 N 秒 health+observe 体检，stop 级发现就落事故报告（并可按需关游戏）。

    【为什么这是一条正经命令（旧账条目 00888）】`watchdog` 早就写好且有 20 个单测，
    但一直只有 `triage` 手动跑一次 —— 也就是"人得想起来去看"。P3 要连续 3 个游戏日无人介入，
    必须有个"一直在看"的循环；本命令就是它，逻辑在 `brain\\agentfarm\\runner.py`（有 7 个单测）。
    """
    from .runner import SupervisedRunner, load_last_stop_report

    if args.last_stop:
        rep = load_last_stop_report()
        if rep is None:
            print(f"{WARN} 还没有任何事故报告（logs\\stops\\ 为空）")
            return 0
        print(json.dumps(rep, ensure_ascii=False, indent=2)[:4000])
        return 0

    runner = SupervisedRunner(
        interval=args.interval,
        duration_seconds=None if args.minutes <= 0 else args.minutes * 60.0,
        max_samples=args.max_samples,
        on_stop=args.on_stop,
    )
    return runner.run()


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


def cmd_plan(args: argparse.Namespace) -> int:
    """规划层（P3 ⑤）自检：一份 full 快照 → 情境简报 → 边界决策 → **只打印任务意图**。

    【本命令刻意做什么、不做什么】
    * 只输出"任务意图"（task / area_hint / reason / expected_evidence）；
      **坐标与动作序列由技能层按当下 observe 计算**，这里一行都不算。
    * 默认**不碰大模型**（`--boundary-llm` 关着）。用户 m01184 明确要求：
      大模型开始介入前先告知、等确认。所以真机默认是纯代码策略，
      连"边界"也只跑 `deterministic_plan()`。
    * `--boundary` 用来人为站到某个边界上（否则单次调用永远是"首次决策 = 非边界"），
      这样即使不开 LLM 也能看清边界状态机是怎么判的。
    """
    try:
        obs = BridgeClient().observe("full", timeout=10.0)
    except BridgeError as exc:
        print(f"{FAIL} 取不到 full 快照（游戏没开？）：{exc}")
        return 1

    areas, area_lines = farm_areas(obs)
    brief = Brief.from_observe(obs, consecutive_failures=max(0, int(args.failures)),
                               areas=areas, area_lines=area_lines)
    state = PlannerState(last_seen_failures=max(0, int(args.failures)))
    if args.boundary == BOUNDARY_NEW_DAY:
        state.day_key = (-1, "forced-by-cli", -1)      # 与当前 day_key 必然不等 ⇒ 跨日边界
    elif args.boundary == BOUNDARY_RECOVERY:
        state.last_seen_failures = max(0, int(args.failures)) - 1   # 计数"上升" ⇒ 恢复边界
    elif args.boundary == BOUNDARY_TASK_CHANGE:
        state.last_task_kind = "__forced__"            # 与代码策略给出的阶段不同 ⇒ 换任务边界
    else:
        state.day_key = brief.day_key                  # 自动：首次决策（非边界）

    planner = BoundaryPlanner(llm_enabled=bool(args.boundary_llm))
    decision = planner.decide(state, brief)

    if args.json:
        print(json.dumps(decision.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"地点={brief.location} 农场={brief.is_farm} 粒度={'逐格' if brief.tiles_present else '整场计数'}")
        print(f"边界={decision.boundary or '（无：常规区间）'}  来源={decision.source}  真的调了 LLM={decision.llm_called}")
        if decision.fallback_reason:
            print(f"{WARN} 降级原因：{decision.fallback_reason}")
        for index, intent in enumerate(decision.intents, 1):
            print(f"  {index}. {intent.to_line()}")
        print("（以上只有任务意图；坐标与动作序列由技能层按当下 observe 计算）")
    if not args.boundary_llm:
        print("提示：大模型边界决策**默认关闭**。要真调 LLM 请显式加 --boundary-llm"
              "（用户 m01184 要求：大模型介入前先告知）。")
    return 0 if decision.intents else 1


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
    m.add_argument("--allow-bed", action="store_true", dest="allow_bed",
                   help="显式允许走到床格（默认禁止：踩床会触发睡觉弹窗）。仅用于复现睡觉弹窗来验证 dismiss_modal")
    m.set_defaults(func=cmd_move)

    g = sub.add_parser("goto", help="跨地点移动：走到另一个地点（可选再走到该地点的某格）")
    g.add_argument("location", help="目标地点名（如 Farm；大小写不敏感，必须是游戏真值里真实存在的地点）")
    g.add_argument("--tile", nargs=2, type=int, metavar=("X", "Y"), default=None,
                   help="到达该地点后再走到的格；省略则只要求跨到该地点")
    g.add_argument("--timeout-ms", type=int, default=30000, dest="timeout_ms",
                   help="整体预算（跨地点要多跳，默认 30000）")
    g.add_argument("--no-focus", action="store_true", dest="no_focus",
                   help="不要把游戏拉到前台（用于验证失焦行为）")
    g.add_argument("--allow-bed", action="store_true", dest="allow_bed",
                   help="落地格允许是床（默认禁止：踩床会触发睡觉弹窗）")
    g.set_defaults(func=cmd_goto)

    ld = sub.add_parser("load", help="从标题界面读档（换 Mod 重启后自己回到存档；无人值守必需）")
    ld.add_argument("--save", default=None, help="存档文件夹名；省略=自动挑最近写过的那个")
    ld.add_argument("--force", action="store_true",
                    help="已经在存档里时也强行读档（会丢掉当天进度，破坏性）")
    ld.add_argument("--timeout-ms", type=int, default=60000, dest="timeout_ms")
    ld.set_defaults(func=cmd_load)

    sd = sub.add_parser("shutdown", help="让游戏自己退出（quit_game）——与 load 配对构成无人值守重启闭环")
    sd.add_argument("--force-after", type=int, default=0, dest="force_after",
                    help="等多少秒后仍没退出就强杀（0=不等待也不强杀）")
    sd.add_argument("--no-force", action="store_true", dest="no_force",
                    help="只发退出请求，绝不强杀")
    sd.set_defaults(func=cmd_shutdown)

    sub.add_parser("focus", help="把《星露谷》窗口拉到前台（v0.5.0 起只是可选兜底）").set_defaults(func=cmd_focus)

    r = sub.add_parser(
        "run",
        help="无人值守监督循环：每 N 秒体检，stop 就落 logs\\stops\\ 事故报告（默认不动游戏）",
    )
    r.add_argument("--interval", type=float, default=15.0, help="采样间隔秒（默认 15）")
    r.add_argument("--minutes", type=float, default=60.0, help="跑多少分钟（<=0 表示不限时；默认 60）")
    r.add_argument("--max-samples", type=int, default=None, dest="max_samples",
                   help="最多采样几次（自检用；默认不限）")
    r.add_argument("--on-stop", choices=("report", "quit", "nothing"), default="report",
                   dest="on_stop", help="停机动作：report=只落报告（默认）/ quit=再让游戏自己退出 / nothing")
    r.add_argument("--last-stop", action="store_true", dest="last_stop",
                   help="不跑循环，只打印最近一次事故报告")
    r.set_defaults(func=cmd_run)

    sub.add_parser(
        "triage",
        help="无人值守体检：世界在推进吗／失焦暂停关着吗／有没有挡路弹窗（退出码 0=ok 1=warn 2=stop）",
    ).set_defaults(func=cmd_triage)

    w = sub.add_parser("watch", help="持续打印世界摘要")
    w.add_argument("--interval", type=float, default=2.0)
    w.set_defaults(func=cmd_watch)

    sub.add_parser("llm-check", help="检查大模型密钥与连通性（不打印密钥）").set_defaults(func=cmd_llm_check)

    a = sub.add_parser("ask", help="临时问慢脑一句（人工验证提示词）")
    a.add_argument("question")
    a.add_argument("--max-tokens", type=int, default=16384, dest="max_tokens",
                   help="给慢脑的 token 上限（默认 16384；与 llm.DEFAULT_MAX_TOKENS 同口径）")
    a.add_argument("--reasoning", action="store_true", help="同时打印思考过程")
    a.set_defaults(func=cmd_ask)

    pl = sub.add_parser(
        "plan",
        help="规划层（P3 ⑤）：打印当前该做的任务意图（默认纯代码策略，不碰大模型）",
    )
    pl.add_argument("--boundary-llm", action="store_true", dest="boundary_llm",
                    help="**默认关闭**：允许在边界上调用真实大模型（用户要求先告知再启用）")
    pl.add_argument("--boundary", choices=(BOUNDARY_NEW_DAY, BOUNDARY_RECOVERY, BOUNDARY_TASK_CHANGE),
                    default=None, help="人为站到某个边界上，用来观察边界状态机（默认：首次决策）")
    pl.add_argument("--failures", type=int, default=0,
                    help="假装技能层已经连续失败 N 次（配合 --boundary recovery 看异常恢复）")
    pl.add_argument("--json", action="store_true", help="打印完整 JSON（含来源/降级原因/拒收问题）")
    pl.set_defaults(func=cmd_plan)
    return p


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
