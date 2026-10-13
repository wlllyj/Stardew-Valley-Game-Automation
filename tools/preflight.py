#!/usr/bin/env python
"""起跑前检查（Lead 装机后自检 / machine-runner 跑 run 前自检）。

为什么需要它：run2 的教训是"起跑时的世界状态没记全"，事后对账时说不清"当时到底几格没浇、几颗种子"。
这个脚本把"能不能起跑"与"起跑时的基线"一次性打印出来，并把基线写盘，供跑完后做观测差分。

它只读：health + observe(full)。**不会**启动游戏、不会 load_save、不会 quit、不写世界。

用法：
    python tools\\preflight.py                     # 用 brain 里 MOD_VERSION_EXPECTED 作期望版本
    python tools\\preflight.py --expect 0.7.22
    python tools\\preflight.py --save-baseline logs\\run3-baseline.json
退出码：0 = 可以起跑；1 = 状态不满足（列出缺哪一条）；2 = 桥不可达/环境问题。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, MOD_VERSION_EXPECTED  # noqa: E402
from agentfarm.farmwork import FarmWorker, seed_items  # noqa: E402


def dig(obj, *path, default=None):
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description="起跑前检查 + 记录基线（只读）")
    ap.add_argument("--expect", default=MOD_VERSION_EXPECTED, help="期望的 Mod 版本（默认取 brain 常量）")
    ap.add_argument("--save-baseline", default=None, help="把基线写成 JSON 文件")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    # 中文输出在非 UTF-8 控制台（cp1252/cp936）会 UnicodeEncodeError 直接崩在第一个 print 上
    # （Lead 实测：未设 PYTHONUTF8 时 `preflight.py --expect 0.7.22` 抛 charmap 编码错误）。
    # 与 tools\run-longrun.py 同口径：自配 stdout 编码，别指望调用方记得设环境变量。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"仓库：{REPO}")
    print(f"期望 Mod 版本：{args.expect}")

    try:
        # 注意：BridgeClient() 构造函数本身就会读 %APPDATA%\StardewValley\AgentFarm\bridge.json，
        # 游戏没在跑时这一步就抛 BridgeError（bridge_file_missing）—— 也要算"桥不可达"。
        client = BridgeClient(timeout=args.timeout)
        health = client.health(timeout=args.timeout)
    except BridgeError as exc:
        print(f"❌ 桥不可达（status={exc.status}）：{exc}")
        print("   游戏没在跑？先 `python tools\\deploy-mod.py`（它会启动游戏并读档）。")
        return 2

    mod_version = health.get("modVersion", "?")
    say_mod = mod_version == args.expect
    print(f"{'✅' if say_mod else '❌'} 装机 Mod 版本 —— 实测={mod_version} / 期望={args.expect}")
    if not say_mod:
        print("   版本不一致：观测里可能缺字段（或多了未识别字段），不要起跑。")

    try:
        obs = client.observe("full", timeout=max(args.timeout, 20.0))
    except BridgeError as exc:
        print(f"❌ observe 失败（status={exc.status}）：{exc}")
        return 2

    has_save = bool(obs.get("hasSaveLoaded"))
    outdoor = bool(dig(obs, "location", "isOutdoorFarm", default=False))
    is_modal = bool(dig(obs, "ui", "isModal", default=False))
    menu = dig(obs, "ui", "activeMenu", default=None)
    advancing = dig(obs, "liveness", "worldAdvancing", default=None)

    checks = [
        (has_save, "已读档（hasSaveLoaded）", has_save),
        (outdoor, "在户外农场（location.isOutdoorFarm）", outdoor),
        (not is_modal, "无阻断模态（ui.isModal==false）", f"activeMenu={menu!r}"),
    ]
    for ok, label, detail in checks:
        print(f"{'✅' if ok else '❌'} {label} —— {detail}")
    if advancing is False:
        print("⚠️ liveness.worldAdvancing=false（时间没在走：可能在模态里，或游戏被暂停）—— 只提示，不判红")

    # 基线（跑完后做差分的起点）
    worker = FarmWorker(client, log=lambda *_a, **_k: None)
    try:
        seeds = seed_items(worker.player_of(obs))
    except Exception as exc:  # noqa: BLE001
        seeds = []
        print(f"⚠️ 种子清点失败：{type(exc).__name__}: {exc}")
    baseline = {
        "generatedAt": obs.get("generatedAt"),
        "recordedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "worldSeq": obs.get("worldSeq"),
        "modVersion": mod_version,
        "day": worker.day_key(obs),
        "timeOfDay": worker.time_of_day(obs),
        "location": worker.location_of(obs).get("name"),
        "playerTile": worker.player_tile(obs),
        "stamina": worker.stamina(obs),
        "money": worker.money(obs),
        "isInBed": worker.is_in_bed(obs),
        "seeds": [[i, n, s] for i, n, s in seeds],
        # task-12 要求基线必须能回答"会不会弹职业选择"与"浇水真值"两个问题
        "farmingLevel": (worker.player_of(obs) or {}).get("farmingLevel"),
        "crops": dig(obs, "farm", "crops"),
        "unwateredCrops": dig(obs, "farm", "unwateredCrops"),
        # farm.dryCrops 才是"今天没浇的格数"（farm.unwateredCrops 不是，见 docs/_analyze-farmcounts.md）；
        # complete==false 时 farm.* 计数不可用，scanSeq 用于判断这张扫描是不是新的。
        "dryCrops": dig(obs, "farm", "dryCrops"),
        "farmComplete": dig(obs, "farm", "complete", default=None),
        "farmScanSeq": dig(obs, "farm", "scanSeq", default=None),
        "waterLeft": worker.water_left(obs),
        "tillableCount": len(worker.tillable_of(obs)),
        "tileCount": len(worker.tiles_of(obs)),
        "tilesTruncated": bool(dig(obs, "location", "tilesTruncated", default=False)),
        "activeMenu": menu,
        "isModal": is_modal,
        "worldAdvancing": advancing,
    }
    print("\n基线：")
    print(json.dumps(baseline, ensure_ascii=False, indent=2, default=str))
    if args.save_baseline:
        out = Path(args.save_baseline)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n已写入基线文件：{out}")

    hard_fail = not (say_mod and has_save and outdoor and not is_modal)
    print("\n结论：" + ("❌ 状态不满足，不要起跑" if hard_fail else "✅ 可以起跑"))
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
