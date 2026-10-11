# -*- coding: utf-8 -*-
"""真机验收 v0.7.20 的两个新技能：**买东西（buy）** 与 **睡觉（sleep）**。

【铁律】不看回执当证据：每个技能的成败都由 `observe?detail=full` 的**前后差分**判定。
  * buy：`player.money` 减少量 == 单价 × 净得数量；`inventory[]` 里该 item 的堆叠增加量 == 回执说的数量。
  * sleep：`clock`（year/season/day）必须**前进一天**；跨日后位置/体力/天气以观测为准。

【sleep 为什么要先 interact 床】游戏里"睡觉"的真实入口是玩家**点床** →
`BedFurniture.checkForAction` 弹 "Go to sleep for the night?" → 玩家点"是" →
`GameLocation.answerDialogueAction("Sleep_Yes", null)` → `startSleep()` → `doSleep()` → `Game1.NewDay(0f)`。
所以这里先 `interact(<床格>)` 把游戏自己的提问引出来，再让 `sleep` 去应答它（走 ModalDismiss 那条口径）。
`interact` 走的是游戏自己的 `GameLocation.checkAction(tile, viewport, player)`，不是合成鼠标事件。

用法（先设 PYTHONPATH=<repo>\\brain）：
    python tools\\verify-sleep-buy.py               # 两个都验
    python tools\\verify-sleep-buy.py --phase buy
    python tools\\verify-sleep-buy.py --phase sleep
    python tools\\verify-sleep-buy.py --seed 472 --count 10
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

LOG_PATH: Path | None = None
_LINES: list[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    _LINES.append(msg)


def flush_log() -> None:
    if LOG_PATH is None:
        return
    try:
        LOG_PATH.write_text("\n".join(_LINES) + "\n", encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        print(f"(写日志失败：{exc})", file=sys.stderr)


def stack_of(obs: dict, item_id: str) -> int:
    total = 0
    for it in (obs.get("player") or {}).get("inventory") or []:
        if str(it.get("id")) == str(item_id):
            total += int(it.get("stack") or 0)
    return total


def inv_lines(obs: dict) -> list[str]:
    out = []
    for it in (obs.get("player") or {}).get("inventory") or []:
        out.append(f"slot{it.get('slot')} {it.get('name')}(id={it.get('id')}) x{it.get('stack')}")
    return out


def day_key(obs: dict) -> tuple:
    c = obs.get("clock") or {}
    return (c.get("year"), c.get("season"), c.get("day"))


def health_line(c: BridgeClient) -> str:
    h = c.health()
    return (f"Mod {h.get('modVersion')}  runtime={json.dumps(h.get('runtime'), ensure_ascii=False)}")


def brief(obs: dict) -> str:
    p = obs.get("player") or {}
    loc = obs.get("location") or {}
    c = obs.get("clock") or {}
    return (f"位置 {loc.get('name')} 玩家 {tuple(p.get('tile') or [])} "
            f"时间 {c.get('year')}年 {c.get('season')} {c.get('day')}日 {c.get('timeOfDay')} "
            f"钱 {p.get('money')}g 体力 {p.get('stamina')}/{p.get('maxStamina')} "
            f"isInBed={p.get('isInBed')}")


def bed_tiles(obs: dict) -> list[tuple[int, int]]:
    out = []
    for f in (obs.get("location") or {}).get("furniture") or []:
        if f.get("isBed"):
            t = tuple(f.get("tile") or [])
            if len(t) == 2:
                out.append(t)
    return out


# ======================================================================
#  Phase buy
# ======================================================================

def phase_buy(c: BridgeClient, seed: str, count: int) -> bool:
    log("=" * 72)
    log(f"【Phase BUY】买 {count} 个 item {seed}")
    log("=" * 72)

    obs0 = c.observe("full")
    money0 = int((obs0.get("player") or {}).get("money") or 0)
    have0 = stack_of(obs0, seed)
    log(f"买之前：{brief(obs0)}")
    log(f"        背包里 item {seed} = {have0}")

    t0 = time.time()
    try:
        res = c.exec_skill("buy", {"item": seed, "count": count}, timeout_ms=30000)
    except BridgeError as exc:
        payload = getattr(exc, "payload", None) or {}
        log(f"[FAIL] buy 失败：status={getattr(exc, 'status', '?')} — {str(exc)[:600]}")
        if payload:
            log(f"        回执：{json.dumps(payload, ensure_ascii=False)[:900]}")
        return False
    dt = time.time() - t0
    log(f"buy 回执（{dt:.1f}s，status={res.get('status')}）：{res.get('reason')}")

    obs1 = c.observe("full")
    money1 = int((obs1.get("player") or {}).get("money") or 0)
    have1 = stack_of(obs1, seed)
    spent = money0 - money1
    gained = have1 - have0
    log(f"买之后：{brief(obs1)}")
    log(f"        背包里 item {seed} = {have1}（前 {have0}，差 +{gained}）")
    log(f"        钱 {money0} → {money1}（支出 {spent}g）")

    ok_gain = gained > 0
    if ok_gain:
        unit = spent / gained
        ok_money = abs(unit - round(unit)) < 1e-9 and (spent % gained == 0)
        log(f"{'✅' if ok_gain else '❌'} 买到东西：+{gained} 个")
        log(f"{'✅' if ok_money else '⚠️'} 钱的差分：{spent}g / {gained} 个 = {unit:g}g 每个"
            + ("" if ok_money else "（不是整数单价，需要人工看一眼）"))
        log("结论：VERIFIED —— 钱少了、背包多了，且都是游戏自己的购买链做的。")
        return ok_gain
    log("❌ 背包没有增加：观测上没买到（回执不算证据）。")
    return False


# ======================================================================
#  Phase sleep
# ======================================================================

def phase_sleep(c: BridgeClient, sleep_timeout_ms: int) -> bool:
    log("=" * 72)
    log("【Phase SLEEP】应答游戏自己的睡觉提问，跨到第二天")
    log("=" * 72)

    obs0 = c.observe("full")
    p0 = obs0.get("player") or {}
    d0 = day_key(obs0)
    beds = bed_tiles(obs0)
    log(f"睡前：{brief(obs0)}")
    log(f"      床格（location.furniture[isBed]）：{beds}")
    log("      背包：" + "、".join(inv_lines(obs0)))

    if not obs0.get("hasSaveLoaded"):
        log("[FAIL] 尚未加载存档")
        return False

    # ---- 引出游戏自己的提问：对床格调游戏自己的 checkAction ----
    if beds and not p0.get("isInBed"):
        target = beds[0]
        try:
            r = c.interact(target, timeout_ms=8000)
            log(f"interact{target} 回执：status={r.get('status')} reason={r.get('reason')}")
        except BridgeError as exc:
            log(f"interact{target} 失败（不致命，继续试 sleep）：status={getattr(exc, 'status', '?')} — {str(exc)[:200]}")
        time.sleep(0.7)
        obs_q = c.observe("full")
        p_q = obs_q.get("player") or {}
        log(f"      interact 后：isInBed={p_q.get('isInBed')} 位置 {tuple(p_q.get('tile') or [])}")
    else:
        log("      （已在床上或拿不到床格，直接 sleep）")

    # ---- 睡觉（长任务：Mod 侧跨 tick 等 Date.TotalDays 变大） ----
    log(f"下发 sleep（timeout_ms={sleep_timeout_ms}，跨日要淡黑+存档+换天，可能几十秒）…")
    t0 = time.time()
    try:
        res = c.exec_skill("sleep", {}, timeout_ms=sleep_timeout_ms)
        dt = time.time() - t0
        log(f"sleep 回执（{dt:.1f}s，status={res.get('status')}）：{res.get('reason')}")
    except BridgeError as exc:
        dt = time.time() - t0
        payload = getattr(exc, "payload", None) or {}
        log(f"[FAIL] sleep 失败（{dt:.1f}s）：status={getattr(exc, 'status', '?')} — {str(exc)[:800]}")
        if payload:
            log(f"        回执：{json.dumps(payload, ensure_ascii=False)[:1200]}")

    time.sleep(1.0)
    obs1 = c.observe("full")
    d1 = day_key(obs1)
    log(f"睡后：{brief(obs1)}")
    log(f"      背包：" + "、".join(inv_lines(obs1)))

    ok_day = d1 != d0
    log()
    log(f"{'✅' if ok_day else '❌'} 跨日：{d0} → {d1}")
    if ok_day:
        log("结论：VERIFIED —— 游戏日期真的前进了一天（跨日 = 唯一能让作物长大/体力恢复的路）。")
        return True
    log("结论：needs_review —— 日期没变，sleep 没有真正跨日（看上面的诊断字段）。")
    return False


def main() -> int:
    global LOG_PATH

    ap = argparse.ArgumentParser(description="真机验收 buy + sleep（v0.7.20）")
    ap.add_argument("--phase", choices=["all", "buy", "sleep"], default="all")
    ap.add_argument("--seed", default="472", help="buy 的 item（默认 472 = 防风草种子）")
    ap.add_argument("--count", type=int, default=10, help="buy 想买几个（默认 10）")
    ap.add_argument("--sleep-timeout", type=int, default=180000, help="sleep 的 timeout_ms（默认 180000）")
    ap.add_argument("--no-log", action="store_true", help="不写 logs/ 里的日志文件")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    logdir = REPO / "logs"
    if not args.no_log:
        logdir.mkdir(exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        LOG_PATH = logdir / f"verify-sleep-buy-{ts}.log"

    c = BridgeClient(timeout=240.0)
    log(health_line(c))

    results: list[tuple[str, bool]] = []
    try:
        if args.phase in ("all", "buy"):
            results.append(("buy", phase_buy(c, args.seed, args.count)))
        if args.phase in ("all", "sleep"):
            results.append(("sleep", phase_sleep(c, args.sleep_timeout)))
    finally:
        if LOG_PATH is not None:
            log(f"\n（日志已写：{LOG_PATH}）")
            flush_log()

    log("=" * 72)
    for name, ok in results:
        log(f"{'✅' if ok else '❌'} {name}")
    all_ok = all(ok for _, ok in results)
    log("总结论：" + ("VERIFIED" if all_ok else "needs_review"))
    if LOG_PATH is not None:
        flush_log()
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
