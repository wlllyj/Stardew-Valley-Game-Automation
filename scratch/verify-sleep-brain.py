r"""真机验收：**脑侧**（`brain\agentfarm\farmwork.py` 的 `FarmWorker.sleep()`）能不能真的睡过去。

为什么单独有这个脚本：条目 036 已用 4 个探针把"睡觉提问怎么弹 / 为什么 180s 不落地"定案
（触发格 `(bed.X+bedTileOffset, bed.Y+1)`、隐藏前置 `Farmer.hasMoved`、应答后必须关提问框），
但那都是**手工拼的步骤**。0.7.23 的 task-33 把这些搬进 Mod + 脑侧之后，必须验证**脑侧真实调用路径**
也能跨日——判据一律是**观测差分**（回执只作诊断）：

  1. `clock.day` **恰好 +1 天**（`season/year` 正确处理跨季/跨年）；
  2. 存档 `...\Saves\Wahaha_450799035\{Wahaha_450799035, SaveGameInfo}` 的 **size 或 mtime 前进**；
  3. `observe` 里 `clock.timeOfDay` 回到清晨（约 06:00）且 `player.stamina` 被恢复。

用法（**真机单写者 = Lead / machine-runner，跑前确认 preflight 通过**）：

  # 先在农场，让脚本自己走回家睡（最接近 run3 的场景，会同时练门格寻路）
  & $py scratch\verify-sleep-brain.py --from-farm

  # 连跑两次（跨两日）
  & $py scratch\verify-sleep-brain.py --times 2

  # 已经在家、只想验床那一段
  & $py scratch\verify-sleep-brain.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
SEASONS = ["spring", "summer", "fall", "winter"]


def save_sig() -> tuple[int, float]:
    """（size 之和, 最新 mtime）——两个文件一起看，任一变都算前进。"""
    total, newest = 0, 0.0
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        p = SAVE_DIR / name
        try:
            st = p.stat()
        except OSError:
            continue
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return total, newest


def fmt_sig(sig: tuple[int, float]) -> str:
    return f"{sig[0]} B / mtime {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sig[1]))}"


def day_key(obs: dict) -> tuple:
    c = obs.get("clock") or {}
    return (c.get("year"), c.get("season"), c.get("day"))


def ordinal(key: tuple) -> int | None:
    """把 (year, season, day) 折成绝对日序，用来断言"恰好 +1 天"。"""
    try:
        y, season, d = key
        return ((int(y) - 1) * 4 + SEASONS.index(str(season))) * 28 + int(d)
    except (TypeError, ValueError):
        return None


def brief(obs: dict) -> str:
    c = obs.get("clock") or {}
    p = obs.get("player") or {}
    return (
        f"day={list(day_key(obs))} tod={c.get('timeOfDay')} loc={p.get('location')} tile={p.get('tile')} "
        f"stam={p.get('stamina')}/{p.get('maxStamina')} money={p.get('money')} isInBed={p.get('isInBed')}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--times", type=int, default=1, help="连续跨日次数（默认 1）")
    ap.add_argument("--from-farm", action="store_true", help="先走去 Farm，再让脑侧走回家睡")
    ap.add_argument("--home", default="FarmHouse")
    ap.add_argument("--farm", default="Farm")
    ap.add_argument("--sleep-timeout", type=int, default=180000)
    ap.add_argument("--wait", type=float, default=120.0, help="每次发完 sleep 后轮询跨日的秒数")
    args = ap.parse_args()

    client = BridgeClient(timeout=15.0)
    worker = FarmWorker(client)
    failures: list[str] = []

    print("== 脑侧睡眠真机验收（判据 = 观测差分，不看回执）==")
    print("health：", {k: (client.health() or {}).get(k) for k in ("modVersion", "schema", "port")})

    for i in range(1, args.times + 1):
        print(f"\n---------------- 第 {i}/{args.times} 次 ----------------")
        obs = client.observe("full")
        k0 = day_key(obs)
        sig0 = save_sig()
        print("睡前：", brief(obs))
        print("存档（前）：", fmt_sig(sig0))

        if args.from_farm:
            print(f"[1] 先走去 {args.farm}（练一次门格寻路：{args.home} → {args.farm}）")
            mv = worker.ensure_location(args.farm)
            print(f"    ensure_location ok={mv.ok} code={mv.code} reason={str(mv.reason)[:200]}")
            obs = client.observe("full")
            print("    现在：", brief(obs))
            if not (obs.get("location") or {}).get("isOutdoorFarm"):
                print("    ⚠ 没到户外农场，仍继续（sleep 会自己走回家）")

        print(f"[2] worker.sleep(home={args.home!r}, timeout_ms={args.sleep_timeout}) —— 脑侧真实路径")
        t0 = time.time()
        r = worker.sleep(home=args.home, timeout_ms=args.sleep_timeout)
        print(f"    耗时 {time.time() - t0:.1f}s  ok={r.ok} code={r.code}")
        print(f"    reason: {str(r.reason)[:500]}")
        if getattr(r, "receipt", ""):
            print(f"    回执:   {str(r.receipt)[:300]}")
        if getattr(r, "before", None) is not None:
            print(f"    before: {r.before}")
        if getattr(r, "after", None) is not None:
            print(f"    after:  {r.after}")

        print(f"[3] 轮询观测最多 {args.wait:.0f}s（跨日会渐黑 + 写存档）")
        moved = False
        last = None
        deadline = time.time() + args.wait
        while time.time() < deadline:
            try:
                obs = client.observe("full")
            except BridgeError as exc:
                print(f"    observe 中断（渐黑/重载？）：{exc.status}")
                time.sleep(3.0)
                continue
            line = brief(obs)
            if line != last:
                print(f"    t+{time.time() - t0:5.1f}s  {line}")
                last = line
            if day_key(obs) != k0:
                moved = True
                break
            time.sleep(2.0)

        sig1 = save_sig()
        k1 = day_key(obs)
        o0, o1 = ordinal(k0), ordinal(k1)
        exact = (o0 is not None and o1 is not None and o1 - o0 == 1)
        save_ok = sig1[1] > sig0[1] or sig1[0] != sig0[0]

        print("[4] 判定")
        print(f"    day 变化：{list(k0)} → {list(k1)}  恰好 +1 天：{'✅' if exact else '❌'}")
        print(f"    存档前进：{fmt_sig(sig1)}  {'✅' if save_ok else '❌'}")
        if not moved:
            failures.append(f"第 {i} 次：日期没变（观测 {list(k1)}）")
        if not exact:
            failures.append(f"第 {i} 次：day 不是恰好 +1（{list(k0)} → {list(k1)}）")
        if not save_ok:
            failures.append(f"第 {i} 次：存档 size/mtime 没前进")
        if not r.ok:
            # 回执 ok 不是判据，但"回执失败而日期前进"要作为诊断记下来（条目 036 的口径）
            print(f"    ⚠ 回执 ok=False（code={r.code}）—— 按口径不作为判据，但需记录：{str(r.reason)[:200]}")

        print(f"    本次结论：{'VERIFIED ✅' if (moved and exact and save_ok) else 'needs_review ❌'}")

    print("\n== 总结 ==")
    if failures:
        print("❌ 未通过：")
        for f in failures:
            print("   -", f)
        return 1
    print(f"✅ VERIFIED —— 脑侧 sleep() 连续 {args.times} 次真跨日（day 恰好 +1 + 存档前进）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
