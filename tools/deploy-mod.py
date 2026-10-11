# -*- coding: utf-8 -*-
"""无人值守部署闭环：**自己关游戏 → 换 Mod dll → 自己开游戏 → 自己读档 → 自检**。

【为什么需要它】换 Mod dll 时游戏进程会锁着 dll，所以以前每改一版都要**人**去做四件事：
关游戏、复制文件、开游戏、点 Continue。用户 2026-10-11 明确要求把这半边也自动化
（"如果能发现问题需要关闭的时候也能自己自主操作就更好了"）。
本工具把这条链路做成一件事，且每一步都留下可审计的输出。

【每一步用的机制（都不是伪造键鼠、也不是乱写游戏状态）】
1. **备份存档**：`tools\\backup-save.cmd`（快照到 `save-backups\\`）。
2. **关游戏**：优先让**游戏自己退出** —— `quit_game` 技能置 `Game1.quit = true`
   （等价于玩家点退出）。只有当它没生效（旧版 Mod 不认识这个技能 / 卡住）时，
   才退到 `taskkill /IM StardewModdingAPI.exe /F /T` 强杀；**强杀前一定已经备份过存档**。
   ⚠️ 游戏只在睡觉/翻页时落盘，所以"关掉"本身会丢当前这一天的进度 —— 这是已知代价，
      因此本工具**不**在无人值守长跑中途调用，只在你决定换版本时调用。
3. **换 dll**：复制 `mod\\AgentFarm.Bridge\\bin\\Release\\{AgentFarm.Bridge.dll,manifest.json}`，
   把旧文件备份成 `.bak-<时间戳>`（可回滚）。
4. **开游戏**：`subprocess.Popen(..., stdout/stderr/stdin=DEVNULL, DETACHED_PROCESS)` ——
   **绝不给游戏接管道**（实测：管道不关会让调用方一直等、而且包装进程被杀会连带杀掉游戏）。
5. **等桥起来**：轮询 `health()` 直到 `modVersion` == 装进去的版本。
   ⚠️ 每次轮询都要**新建 BridgeClient**：token 每次启动都变，必须重读 `bridge.json`。
6. **自己读档**：`load_save`（标题界面 → 存档）。

用法：
    set PYTHONPATH=D:\\...\\星露谷游戏自动化\\brain
    python tools\\deploy-mod.py                    # 完整闭环（关→换→开→读档）
    python tools\\deploy-mod.py --no-quit          # 游戏已经关了，只换 dll 并启动
    python tools\\deploy-mod.py --keep-running     # 只关+换，不自动开（人工来开）
    python tools\\deploy-mod.py --skip-backup      # 不备份存档（默认会备份）

退出码：0 成功；2 前置条件不满足；3 游戏不肯退出；4 安装失败；
        5 桥没起来 / 版本对不上；6 读档失败。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BUILD_DIR = REPO / "mod" / "AgentFarm.Bridge" / "bin" / "Release"
DEFAULT_GAME = Path(r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley")
GAME_EXE = "StardewModdingAPI.exe"


def game_dir() -> Path:
    return Path(os.environ.get("STARDEW_GAME_PATH") or DEFAULT_GAME)


def mod_dir() -> Path:
    return game_dir() / "Mods" / "AgentFarm.Bridge"


def read_manifest_version(path: Path) -> str | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("Version")
    except Exception:
        return None


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
    while time.time() < end:
        if not game_pids():
            return True
        time.sleep(1.0)
    return not game_pids()


def backup_save() -> bool:
    cmd = REPO / "tools" / "backup-save.cmd"
    if not cmd.exists():
        print(f"[WARN] 找不到 {cmd}，跳过存档备份")
        return False
    print(f"[1] 备份存档：{cmd.name}")
    try:
        r = subprocess.run(["cmd", "/c", str(cmd)], cwd=str(REPO),
                           capture_output=True, text=True, errors="replace", timeout=180)
        tail = (r.stdout or "").strip().splitlines()[-3:]
        for line in tail:
            print(f"    {line}")
        return r.returncode == 0
    except Exception as exc:
        print(f"[WARN] 备份存档失败：{exc}（继续，但请知情）")
        return False


def quit_game(exit_timeout: float) -> int:
    """返回 0=已退出；3=退不掉。"""
    pids = game_pids()
    if not pids:
        print("[2] 游戏没在运行（跳过退出步骤）")
        return 0

    graceful = None
    try:
        client = BridgeClient(timeout=6.0)
        graceful = client.quit_game()
        print(f"[2] 请游戏自己退出（quit_game）：{graceful.get('status')} — {graceful.get('reason')}")
    except BridgeError as exc:
        print(f"[2] 无法通过桥请求退出（{getattr(exc, 'status', '?')}）：{exc}")
        print("    → 将直接走强杀兜底（存档已备份）")

    if wait_no_process(exit_timeout):
        print(f"[2] 游戏已退出（等待 {exit_timeout:.0f}s 内）")
        return 0

    # 兜底：强杀。只在"游戏自己不肯退"时走这一步，且此前已备份存档。
    print(f"[2] {exit_timeout:.0f}s 内没退出（pids={game_pids()}）→ 强杀兜底：taskkill /F /T")
    try:
        subprocess.run(["taskkill", "/IM", GAME_EXE, "/F", "/T"],
                       capture_output=True, text=True, errors="replace", timeout=60)
    except Exception as exc:
        print(f"    taskkill 失败：{exc}")
    if wait_no_process(15):
        print("[2] 强杀后进程已消失")
        return 0

    print(f"[STOP] 游戏进程仍在：{game_pids()}；dll 很可能被锁，拒绝覆盖")
    return 3


def install() -> tuple[str | None, str | None]:
    """复制 dll + manifest（旧文件留 .bak）。返回 (旧版本, 新版本)。"""
    src_dll, src_man = BUILD_DIR / "AgentFarm.Bridge.dll", BUILD_DIR / "manifest.json"
    if not src_dll.exists() or not src_man.exists():
        print(f"[STOP] 编译产物不存在：{src_dll} / {src_man}（先 dotnet build）")
        return None, None

    dst = mod_dir()
    dst.mkdir(parents=True, exist_ok=True)
    old_ver = read_manifest_version(dst / "manifest.json")
    new_ver = read_manifest_version(src_man)

    ts = time.strftime("%Y%m%d-%H%M%S")
    print(f"[3] 安装到 {dst}（旧版本 {old_ver} → 新版本 {new_ver}）")
    for name, src in (("AgentFarm.Bridge.dll", src_dll), ("manifest.json", src_man)):
        target = dst / name
        if target.exists():
            shutil.copy2(target, dst / f"{name}.bak-{ts}")
        shutil.copy2(src, target)
        print(f"    {name}  {target.stat().st_size} bytes")
    return old_ver, new_ver


def launch() -> int:
    exe = game_dir() / GAME_EXE
    if not exe.exists():
        print(f"[STOP] 找不到 {exe}")
        return 4
    flags = 0
    if os.name == "nt":
        # 【实测教训 2026-10-11】目标必须带一个**自己的控制台**：
        #   * `DETACHED_PROCESS`(0x8) 试过 —— 进程起了但**SMAPI 起不来**：
        #     150 秒内桥端口一直不通，游戏进程随即消失，`SMAPI-latest.txt` 里连启动横幅都没有。
        #     推断是没有控制台时 `Console.*`（标题/编码）抛异常，SMAPI 在进入游戏前就挂了。
        #   * `CREATE_NEW_CONSOLE`(0x10) 实测可行：3 秒内健康检查就回了 modVersion。
        # 同时给 CREATE_NEW_PROCESS_GROUP 让它与调用方脱钩。
        # ⚠️ 三个 std 句柄一律指向 DEVNULL：**绝不给游戏接管道**（管道不关会让调用方一直等）。
        flags = 0x00000010 | 0x00000200
    subprocess.Popen([str(exe)], cwd=str(game_dir()),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    print(f"[4] 已启动 {exe.name}（flags=0x{flags:X}）")
    return 0


def wait_bridge(expected_version: str | None, boot_timeout: float) -> dict | None:
    print(f"[5] 等桥起来（期望 modVersion={expected_version}，最多 {boot_timeout:.0f}s）")
    end = time.time() + boot_timeout
    last = ""
    while time.time() < end:
        try:
            # ⚠️ 每次都要新建：token 每次启动都变，必须重读 bridge.json
            client = BridgeClient(timeout=4.0)
            h = client.health()
            ver = h.get("modVersion")
            if ver == expected_version:
                print(f"[5] 桥已就绪：modVersion={ver} port={h.get('server', {}).get('port')}")
                return h
            last = f"modVersion={ver}（期望 {expected_version}）"
        except BridgeError as exc:
            last = getattr(exc, "status", str(exc))
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(2.0)
    print(f"[STOP] 桥没起来或版本对不上：最后一次 {last}")
    return None


def load_save(save: str | None) -> bool:
    print("[6] 让游戏自己读档（load_save）")
    try:
        res = BridgeClient(timeout=90.0).load_save(save, timeout_ms=90000)
        print(f"[6] {res.get('status')}：{res.get('reason')}")
        return True
    except BridgeError as exc:
        print(f"[STOP] 读档失败（status={getattr(exc, 'status', '?')}）：{exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="无人值守部署：关游戏 → 换 Mod dll → 开游戏 → 读档")
    ap.add_argument("--no-quit", action="store_true", dest="no_quit",
                    help="假设游戏已经关闭（跳过退出步骤）")
    ap.add_argument("--keep-running", action="store_true", dest="keep_running",
                    help="换完 dll 不自动启动游戏")
    ap.add_argument("--skip-load", action="store_true", dest="skip_load",
                    help="启动后不自动读档（留在标题界面）")
    ap.add_argument("--skip-backup", action="store_true", dest="skip_backup",
                    help="不备份存档（默认会备份；强杀前的保险）")
    ap.add_argument("--save", default=None, help="要读的存档文件夹名（默认自动挑最近的）")
    ap.add_argument("--exit-timeout", type=float, default=45.0, dest="exit_timeout",
                    help="等游戏自己退出的秒数，超时才强杀（默认 45）")
    ap.add_argument("--boot-timeout", type=float, default=150.0, dest="boot_timeout",
                    help="等桥起来的秒数（默认 150）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("== 无人值守部署 ==")
    print(f"仓库 {REPO}")
    print(f"游戏 {game_dir()}")
    installed_now = read_manifest_version(mod_dir() / "manifest.json")
    print(f"装机版本 {installed_now}；待装版本 {read_manifest_version(BUILD_DIR / 'manifest.json')}")

    if not args.skip_backup:
        backup_save()

    if not args.no_quit:
        rc = quit_game(args.exit_timeout)
        if rc != 0:
            return rc
    else:
        print("[2] --no-quit：跳过退出步骤")
        if game_pids():
            print(f"[STOP] 但游戏仍在运行（pids={game_pids()}）：dll 会被锁，拒绝覆盖")
            return 2

    old_ver, new_ver = install()
    if new_ver is None:
        return 4

    if args.keep_running:
        print("[4] --keep-running：不自动启动游戏")
        return 0

    rc = launch()
    if rc != 0:
        return rc

    h = wait_bridge(new_ver, args.boot_timeout)
    if h is None:
        return 5
    print(f"    运行态：{json.dumps(h.get('runtime'), ensure_ascii=False)}")

    if args.skip_load:
        print("[6] --skip-load：留在标题界面")
        return 0

    if not load_save(args.save):
        return 6

    print(f"[OK] 部署闭环完成：{old_ver} → {new_ver}，已自动读档")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
