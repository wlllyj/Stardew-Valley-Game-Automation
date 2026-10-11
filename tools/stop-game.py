"""不需要真机验证时，把游戏关掉 —— 免得游戏里的时间白走、机器白占。

用法（仓库根目录）：
    python tools\\stop-game.py                # 优雅退出，默认最多等 45s
    python tools\\stop-game.py --wait 90
    python tools\\stop-game.py --force        # 等不到才硬关（硬关前先备份存档）

为什么默认不用 taskkill：`quit_game` 技能就是置 `Game1.quit = true`，让**游戏自己**走它的退出路径，
存档不会被写坏。硬关只在"游戏卡死不退"时兜底，且先备份存档（与 tools\\deploy-mod.py 同一纪律）。

两个必须知道的事实：
  * **没睡觉就退出 = 当天的进度不保留**（星露谷只在睡觉时存档）。真实机上要接着今天的活干，
    就先让 brain 睡一觉（跨日存档），再来关游戏。
  * `quit_game` 的**回执常常收不到**（连接会被重置）—— 回执不算证据，以"进程是否真的消失"为准。

返回码：0 = 游戏已不在跑（关掉了 / 本来就没开）；1 = 还活着且没允许硬关（或硬关失败）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

GAME_EXE = "StardewModdingAPI.exe"


def game_pids() -> list[int]:
    """当前在跑的 `StardewModdingAPI.exe` 进程号（tasklist 解析，不依赖 psutil）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=20,
        ).stdout
    except Exception:
        return []

    pids: list[int] = []
    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower().startswith("stardewmoddingapi"):
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def wait_no_process(seconds: float) -> bool:
    end = time.time() + seconds
    while True:
        if not game_pids():
            return True
        if time.time() >= end:
            return False
        time.sleep(1.0)


def backup_save() -> bool:
    cmd = REPO / "tools" / "backup-save.cmd"
    if not cmd.exists():
        print(f"[WARN] 找不到 {cmd}，跳过存档备份")
        return False
    print(f"    备份存档：{cmd.name}")
    try:
        r = subprocess.run(["cmd", "/c", str(cmd)], cwd=str(REPO),
                           capture_output=True, text=True, errors="replace", timeout=180)
        for line in (r.stdout or "").strip().splitlines()[-3:]:
            print(f"    {line}")
        return r.returncode == 0
    except Exception as exc:
        print(f"[WARN] 备份失败：{exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="不需要真机验证时关掉游戏（优雅退出优先）")
    ap.add_argument("--wait", type=float, default=45.0, help="等游戏自己退出的秒数（默认 45）")
    ap.add_argument("--force", action="store_true", help="等不到就 taskkill（硬关前先备份存档）")
    args = ap.parse_args(argv)

    pids = game_pids()
    if not pids:
        print("游戏本来就没在跑（没有 StardewModdingAPI.exe），无需关闭。")
        return 0
    print(f"[1] 游戏在跑：pids={pids}")

    graceful_sent = False
    try:
        client = BridgeClient(timeout=5.0)
        try:
            h = client.health(timeout=5.0)
            print(f"    桥就绪：modVersion={h.get('modVersion')} hasSaveLoaded={h.get('hasSaveLoaded')}")
        except BridgeError as exc:
            print(f"    桥读不到 health（{exc.status}）：可能刚启动或已经要退出，仍试 quit_game")
        print("[2] 请游戏自己退出（quit_game → Game1.quit=true）…")
        r = client.quit_game(timeout_ms=3000)
        print(f"    回执：{r.get('status')} — {r.get('reason', '')}")
        graceful_sent = True
    except BridgeError as exc:
        # 连接被重置正是"正在退出"的预期现象（docs 里写明了：回执不算证据）
        print(f"    连接中断（{exc.status}）：这正是退出的预期现象，继续等进程消失")
        graceful_sent = True
    except Exception as exc:
        print(f"[WARN] 发起退出时出问题：{type(exc).__name__}: {exc}")

    if wait_no_process(max(1.0, args.wait)):
        print(f"✅ 游戏已退出（原 pids={pids}）。下次要真机验证时再拉起：python tools\\deploy-mod.py --no-quit")
        return 0

    print(f"× 等了 {args.wait:.0f}s 还没退出：pids={game_pids()}")
    if not args.force:
        print("  要硬关：python tools\\stop-game.py --force（会先备份存档）")
        return 1

    print("[3] 硬关兜底：先备份存档")
    backup_save()
    try:
        subprocess.run(["taskkill", "/IM", GAME_EXE, "/F", "/T"],
                       capture_output=True, text=True, errors="replace", timeout=60)
    except Exception as exc:
        print(f"    taskkill 失败：{exc}")
    if wait_no_process(30.0):
        print(f"✅ 已硬关（原 pids={pids}）")
        return 0
    print(f"[STOP] 进程仍在：{game_pids()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
