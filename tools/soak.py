# -*- coding: utf-8 -*-
"""无人值守浸泡测试（soak）：长时间连续采样桥接与世界，最后给一份判据清单。

【为什么需要它】
项目目标是"无人值守"，而这个性质**没法靠一次点检证明**——必须在真实运行中
连续观察几十分钟：连接会不会断、Mod 会不会漏 tick、世界时钟会不会停、
`oofFixCount` 会不会继续涨（说明 `Game1.options` 又被整体换掉）、
有没有弹窗把世界卡住、exec 链路会不会中途失灵。

【它同时是"补时间之谜"的取证工具】
IL 结论说游戏里**没有** catch-up 机制，但 v0.5.0 验收时实测到
`650 → 700`（≤2 秒 +50 分钟）。本脚本按固定间隔采样 `clock.timeOfDay`，
把任何 **单次采样间隔内 ≥ 20 分钟** 的跳跃单独打出来并计入 `tod_jumps`——
这样"是不是每次都跳、跳多少、间隔多久"就有数据可查，而不是靠回忆。

【用法】（**不需要**设 PYTHONPATH：脚本自己把仓库的 `brain/` 插进 sys.path）
    python tools\\soak.py                      # 默认 20 分钟，3 秒一采样
    python tools\\soak.py --minutes 40         # 长跑
    python tools\\soak.py --interval 2 --move-every 120

【纪律】本脚本**不抢焦点、不碰键鼠**：移动靠 `move_to`（游戏自己的寻路），
且只在已知空地板格之间来回走，**绝不**把床格当选点（那会弹睡觉确认框）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

# 已知空地板格（FarmHouse 真机验过：(7,9) ok / (8,9) ok / (6,8) ok）。
# 刻意不放任何被床覆盖的格（x=9..11, y=8..11 都在床的包围盒里）。
SAFE_TILES = [(7, 9), (8, 9), (6, 8)]


def to_minutes(tod: int | None) -> int | None:
    """`630` -> `390`（当天 0 点起的分钟数），用于跨小时比较。"""
    if not isinstance(tod, int):
        return None
    return (tod // 100) * 60 + (tod % 100)


def stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    # 控制台默认可能是 cp1252/cp936，中文输出会 UnicodeEncodeError 直接崩——
    # 本项目**所有** tools 都自带这一步，不要求用户记得设 PYTHONIOENCODING
    # （见 docs/00-开发日志.md 条目 008）。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="无人值守浸泡测试")
    ap.add_argument("--minutes", type=float, default=20.0, help="总时长（分钟）")
    ap.add_argument("--interval", type=float, default=3.0, help="采样间隔（秒）")
    ap.add_argument("--move-every", type=float, default=90.0,
                    help="每隔多少秒发一次 move_to（0 = 不移动）")
    ap.add_argument("--out", default=None, help="日志文件路径（默认 logs\\soak-<时间戳>.log）")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else (
        _REPO / "logs" / f"soak-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logf = out_path.open("w", encoding="utf-8")

    def emit(line: str) -> None:
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    client = BridgeClient(timeout=8.0)
    emit(f"# soak 开始 {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}")
    emit(f"# 目标 URL {client.info.base_url}  时长 {args.minutes} 分钟  采样 {args.interval}s  "
         f"移动间隔 {args.move_every}s")
    emit(f"# 日志 {out_path}")

    stats: dict[str, object] = {
        "samples": 0, "errors": 0, "conn_errors": 0,
        "tod_jumps": [], "tod_stalls": [], "oof_fix_growth": [],
        "modal_seen": 0, "moves": 0, "moves_ok": 0,
        "seq_first": None, "seq_last": None,
    }

    t_end = time.time() + args.minutes * 60
    next_move = time.time() + args.move_every if args.move_every > 0 else None
    move_idx = 0
    prev_tod_min: int | None = None
    prev_tod_at: float | None = None
    prev_sample_at: float | None = None
    prev_oof_fix: int | None = None
    last_seq: int | None = None
    seq_stuck_since: float | None = None

    try:
        while time.time() < t_end:
            t0 = time.time()
            try:
                h = client.health()
                o = client.observe("summary")
            except BridgeError as ex:
                stats["errors"] = int(stats["errors"]) + 1
                if ex.status in ("connection_broken", "not_running", "stale"):
                    stats["conn_errors"] = int(stats["conn_errors"]) + 1
                emit(f"{stamp()}  ❌ 采样失败 status={ex.status} {ex}")
                time.sleep(args.interval)
                continue
            except OSError as ex:
                stats["errors"] = int(stats["errors"]) + 1
                stats["conn_errors"] = int(stats["conn_errors"]) + 1
                emit(f"{stamp()}  ❌ 连接层异常 {type(ex).__name__}: {ex}")
                time.sleep(args.interval)
                continue

            stats["samples"] = int(stats["samples"]) + 1
            hg = h.get("game") or {}
            hr = h.get("runtime") or {}
            clock = o.get("clock") or {}
            loc = o.get("location") or {}
            player = o.get("player") or {}
            ui = o.get("ui") or {}
            live = o.get("liveness") or {}

            # 注意字段位置：`secondsSinceClockMoved` 在 **liveness** 下，不在 clock 下
            # （真机对照 brain/agentfarm/__main__.py:112-113 的打印即可确认）。
            tod = clock.get("timeOfDay")
            tod_min = to_minutes(tod)
            seq = hr.get("worldSeq")
            stall = live.get("secondsSinceClockMoved")
            advancing = live.get("worldAdvancing")
            if stats["seq_first"] is None:
                stats["seq_first"] = seq
            stats["seq_last"] = seq

            # 采样器**自己**的节奏也要留证据：否则"时钟跳了一大步"可能只是脚本睡过头，
            # 而不是游戏真的跳了。dt 明显超过 interval 时单独标出来。
            dt = (t0 - prev_sample_at) if prev_sample_at is not None else None
            prev_sample_at = t0

            flags = []
            if dt is not None and dt > args.interval * 1.75:
                flags.append(f"⏱采样器被拖慢 dt={dt:.1f}s")
            # --- 判据 1：游戏窗口不活跃时，世界也必须推进（v0.5.0 的整条命门） ---
            if hg.get("windowActive") is False and hg.get("pauseWhenOutOfFocus") is True:
                flags.append("🔴oof=true(失焦暂停又回来了)")
            # --- 判据 2：oofFixCount 只增不减是正常的（被改回就扳），但要记录增长时刻 ---
            of = hg.get("oofFixCount")
            if isinstance(of, int):
                if prev_oof_fix is not None and of > prev_oof_fix:
                    stats["oof_fix_growth"].append((stamp(), prev_oof_fix, of))  # type: ignore[union-attr]
                    flags.append(f"⚠️oofFixCount {prev_oof_fix}→{of}(options 被换掉过)")
                prev_oof_fix = of
            # --- 判据 3：时钟单步跳跃（补时间之谜取证） ---
            if tod_min is not None and prev_tod_min is not None:
                d = tod_min - prev_tod_min
                if d >= 20:
                    stats["tod_jumps"].append((stamp(), prev_tod_min, tod_min, d))  # type: ignore[union-attr]
                    flags.append(f"🔎时钟单步 +{d}min")
                elif d == 0 and isinstance(stall, (int, float)) and stall > 60:
                    stats["tod_stalls"].append((stamp(), stall))  # type: ignore[union-attr]
                    flags.append(f"🔴时钟停滞 {stall:.0f}s")
            if tod_min is not None:
                prev_tod_min, prev_tod_at = tod_min, t0
            # --- 判据 4：worldSeq 长期不动（= Mod 侧真的卡了） ---
            if seq == last_seq:
                if seq_stuck_since is None:
                    seq_stuck_since = t0
                elif t0 - seq_stuck_since > 30:
                    flags.append(f"🔴worldSeq 已经 {t0 - seq_stuck_since:.0f}s 没动")
            else:
                seq_stuck_since = None
            last_seq = seq
            # --- 判据 5：模态挡路（无人值守的经典死法） ---
            modal = ui.get("isModal") or ui.get("activeMenu") not in (None, "")
            if modal:
                stats["modal_seen"] = int(stats["modal_seen"]) + 1
                flags.append(f"⚠️模态 {ui.get('activeMenu')!r}")

            ptile = player.get("tile") or player.get("tilePoint")
            emit(f"{stamp()}  samples={stats['samples']:4d} "
                 f"loc={loc.get('name'):<12} tile={ptile} tod={tod} stall={stall} adv={advancing} "
                 f"seq={seq} ticks={hr.get('ticks')} active={hg.get('windowActive')} "
                 f"oof={hg.get('pauseWhenOutOfFocus')} oofFix={of} "
                 f"req={h.get('server', {}).get('requestsServed')}"
                 + ("   " + " ".join(flags) if flags else ""))

            # --- 周期性移动：验证 exec 链路在长时间运行后仍然可用 ---
            if next_move is not None and time.time() >= next_move:
                x, y = SAFE_TILES[move_idx % len(SAFE_TILES)]
                move_idx += 1
                stats["moves"] = int(stats["moves"]) + 1
                try:
                    r = client.move_to(x, y, timeout_ms=8000)
                    ok = bool(r.get("ok"))
                    if ok:
                        stats["moves_ok"] = int(stats["moves_ok"]) + 1
                    emit(f"{stamp()}  🚶 move_to({x},{y}) -> ok={ok} status={r.get('status')} "
                         f"{r.get('elapsedMs')}ms reason={r.get('reason') or '-'}")
                except BridgeError as ex:
                    stats["errors"] = int(stats["errors"]) + 1
                    emit(f"{stamp()}  🚶 move_to({x},{y}) 抛 BridgeError status={ex.status} {ex}")
                next_move = time.time() + args.move_every

            time.sleep(max(0.0, args.interval - (time.time() - t0)))
    except KeyboardInterrupt:
        emit(f"{stamp()}  (被 Ctrl+C 打断，输出已落盘)")
    finally:
        emit("")
        emit("========== soak 汇总 ==========")
        emit(f"采样 {stats['samples']} 次；采样失败 {stats['errors']} 次（其中连接层 {stats['conn_errors']}）")
        emit(f"worldSeq {stats['seq_first']} → {stats['seq_last']}")
        emit(f"移动 {stats['moves']} 次，成功 {stats['moves_ok']}")
        emit(f"见到模态 {stats['modal_seen']} 次")
        jumps = stats["tod_jumps"]
        emit(f"时钟单步跳跃(≥20min) {len(jumps)} 次：{jumps}")
        emits = stats["tod_stalls"]
        emit(f"时钟停滞(>60s 且同刻度) {len(emits)} 次：{emits}")
        emit(f"oofFixCount 增长 {len(stats['oof_fix_growth'])} 次：{stats['oof_fix_growth']}")
        emit(f"日志：{out_path}")
        logf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
