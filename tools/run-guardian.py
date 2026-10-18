#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""长跑看护守护：脑进程消失后自动把游戏**优雅**退出（防「无人看护 1h43m」重演）。

## 为什么需要它（2026-10-18 A8 事故）

A8 是**脱离式**长跑：前任 Lead 会话 15:08 上下文硬顶死亡、看护子代理 15:09 一起失败，但脑进程
继续跑到 15:20:38 自己以 max-days 收尾。此后**没有人执行 `tools/stop-game.py`**，游戏无人看护
又跑了 1h43m（15:20→17:03，SMAPI 再落盘 7 次），证据链被污染、终态存档不可复核。
本脚本补的就是这一环：**脑一死，看护者自己把游戏关掉**。

## 判据（只看三样东西，不碰生产代码、不写任务板）

1. `logs/<tag>.pid` 里的脑进程是否还活着（`tasklist`/`OpenProcess` 实测，不信自述）；
2. `logs/<tag>.jsonl` 是否出现 `finish` 事件，或**超过 `--stall-seconds` 秒没有新行**；
3. `%APPDATA%\\StardewValley\\AgentFarm\\bridge.json` 是否存在/是否新鲜/health 是否可达。

| 状态 | 动作 |
|---|---|
| 脑**死** 且（`finish` 出现 或 账本超时无新行） | **执行 `tools/stop-game.py` 优雅退出** → 复核进程 0 / bridge.json / 17890 → 写日志 |
| 脑**活** 但桥失联 | **只告警，不退出**（不越权：脑还在跑，游戏必须开着） |
| PID 文件缺失 / 解析失败 | 告警并**不触发**（安全闸：不能证明脑死就不动手） |
| 脑死但账本仍在更新 | 继续观察，等 `finish` 或超时（避免打断收尾写账本） |

## 安全闸

- **只对显式 `--tag` 的 run 生效**（无默认 tag；路径全部由 tag 派生）；
- 触发的必要条件里必须有「PID 文件存在 + 进程实测已死」——`PID 文件缺失` 一律不触发；
- `--dry-run` 可离线演练（打印将要执行的命令，不执行 stop、不退出游戏）；
- 只调用 `tools/stop-game.py`（优雅退出；**绝不 taskkill**），stop 后如实复核，不静默。

## 用法

```
# 真机（脱离式起跑，返回后看护进程继续跑；与 agent 回合边界无关）
python tools\\run-guardian.py --tag longrun-runA9-0744 --detach

# 前台看护（调试用；Ctrl+C 退出）
python tools\\run-guardian.py --tag longrun-runA9-0744

# 离线演练（不触发真 stop；--once 只评估一拍）
python tools\\run-guardian.py --tag t9 --journal scratch\\fixture.jsonl --pid-file scratch\\fixture.pid --dry-run --once

# 只评估一拍不循环（夹具/自测用）
python tools\\run-guardian.py --tag t9 --pid-file ... --journal ... --once
```

日志：`logs/<tag>-guardian.log`（逐条带时间/判据/stop rc/复核读数）；状态快照：
`logs/<tag>-guardian-state.json`（每拍覆盖）；脱离式起跑的 console：
`logs/<tag>-guardian.console.log`、guardian 自身 pid：`logs/<tag>-guardian.pid`。

退出码：0 = 已收尾/无需动作（含 --once/--dry-run 正常结束）；2 = 已触发 stop 但游戏仍未退出
（需要人工介入，日志里写清）；3 = 参数/环境错误。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - 老 Python/被重定向的流
        pass

ROOT = Path(__file__).resolve().parents[1]
GAME_EXE = "StardewModdingAPI.exe"
HOST = "127.0.0.1"
BRIDGE_PORT_DEFAULT = 17890
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_STOP_SCRIPT_DEFAULT = "tools/stop-game.py"
_ECHO = True  # 日志是否同时回显到 stdout（脱离式起跑时 console 里能看到过程；--no-echo 关闭）


# ------------------------------------------------------------------ 基础探测

def _alive(pid: int | None) -> bool | None:
    """Windows 下实测 PID 是否活着；None = 探测失败（安全闸：不据此触发）。"""
    if not pid:
        return False
    if sys.platform != "win32":  # pragma: no cover - 本项目只跑 Windows
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    except Exception:  # noqa: BLE001
        return None


def game_pids() -> list[int]:
    """当前在跑的 `StardewModdingAPI.exe` 进程号（与 tools/stop-game.py 同口径）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=20,
        ).stdout
    except Exception:  # noqa: BLE001
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


def port_listening(port: int) -> bool | None:
    """17890 是否仍有 LISTENING（TIME_WAIT 不算；探测失败返回 None）。"""
    import re
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             errors="replace", timeout=20).stdout
    except Exception:  # noqa: BLE001
        return None
    pat = re.compile(rf":{port}\s")
    for line in out.splitlines():
        if "LISTENING" in line.upper() and pat.search(line):
            return True
    return False


def read_pid_file(path: Path) -> dict:
    rec: dict = {"path": str(path), "exists": path.exists(), "raw": "", "pid": None, "parse_ok": False}
    if not rec["exists"]:
        return rec
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        return rec
    rec["raw"] = raw
    if raw.isdigit():
        rec["pid"] = int(raw)
        rec["parse_ok"] = True
    return rec


def read_journal(path: Path) -> dict:
    """账本只读快照：行数 / 末事件 / finish 是否存在 / mtime / 无新行秒数。"""
    rec: dict = {"path": str(path), "exists": path.exists(), "lines": 0, "finish": False,
                 "last_event": None, "last_t": None, "size": 0, "mtime": None,
                 "mtime_epoch": None, "stall_seconds": None}
    if not rec["exists"]:
        return rec
    try:
        st = path.stat()
        rec["size"] = st.st_size
        rec["mtime_epoch"] = st.st_mtime
        rec["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        rec["stall_seconds"] = round(time.time() - st.st_mtime, 1)
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec["lines"] += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = row.get("event")
                rec["last_event"] = ev
                rec["last_t"] = row.get("t")
                if ev == "finish":
                    rec["finish"] = True
    except OSError as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def read_bridge(path: Path, stale_seconds: float, health: bool, port: int) -> dict:
    rec: dict = {"path": str(path), "exists": path.exists(), "pid": None, "modVersion": None,
                 "port": None, "mtime": None, "age_seconds": None, "stale": False,
                 "health_ok": None, "error": None}
    if not rec["exists"]:
        return rec
    try:
        st = path.stat()
        rec["mtime"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        rec["age_seconds"] = round(time.time() - st.st_mtime, 1)
        rec["stale"] = st.st_mtime < time.time() - stale_seconds
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        rec["pid"] = data.get("pid")
        rec["modVersion"] = data.get("modVersion")
        rec["port"] = data.get("port")
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
    if health:
        rec["health_ok"] = _health_ok(rec.get("port") or port)
    return rec


def _health_ok(port: int) -> bool | None:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{HOST}:{port}/v1/health", timeout=3) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ 判据

def evaluate(cfg: argparse.Namespace) -> dict:
    pid = read_pid_file(Path(cfg.pid_file))
    alive = _alive(pid["pid"]) if pid["parse_ok"] else None
    journal = read_journal(Path(cfg.journal))
    bridge = read_bridge(Path(cfg.bridge_json), cfg.bridge_stale_seconds,
                         not cfg.no_health_check, cfg.bridge_port)
    stalled = bool(journal["exists"] and journal["stall_seconds"] is not None
                   and journal["stall_seconds"] >= cfg.stall_seconds)
    brain_dead = bool(pid["exists"] and pid["parse_ok"] and alive is False)
    bridge_lost = (not bridge["exists"]) or bridge["stale"] or (bridge["health_ok"] is False)
    trigger = bool(brain_dead and (journal["finish"] or stalled))

    reasons: list[str] = []
    if not pid["exists"]:
        reasons.append("PID 文件缺失 ⇒ 安全闸：无法证明脑死，不触发")
    elif not pid["parse_ok"]:
        reasons.append(f"PID 文件解析失败（原文 {pid['raw']!r}）⇒ 不触发")
    elif alive is None:
        reasons.append("脑进程存活探测失败 ⇒ 安全闸：不触发")
    elif alive is False and not journal["exists"]:
        reasons.append("脑已消失但账本不存在 ⇒ 无法判 finish/超时，不触发（人工核对）")
    elif alive is False and not trigger:
        reasons.append(f"脑已消失，但账本 {journal['stall_seconds']}s 前仍在更新"
                       f"（finish={journal['finish']}，阈值 {cfg.stall_seconds:.0f}s）⇒ 继续观察")
    elif alive is True and bridge_lost:
        reasons.append("脑活但桥失联 ⇒ 只告警，不退出（游戏必须开着）")
    elif alive is True:
        reasons.append("脑活、桥在 ⇒ 正常")
    if trigger:
        reasons.append("判据成立：脑死 且 " + ("finish 已出现" if journal["finish"]
                                              else f"账本已 {journal['stall_seconds']}s 无新行"))

    return {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": cfg.tag,
            "pid": pid, "brain_alive": alive, "brain_dead": brain_dead,
            "journal": journal, "finish_present": journal["finish"], "stalled": stalled,
            "stall_threshold": cfg.stall_seconds, "bridge": bridge,
            "bridge_lost": bridge_lost, "trigger": trigger, "reasons": reasons}


# ------------------------------------------------------------------ 执行 stop + 复核

def run_stop(cfg: argparse.Namespace, state: dict, log_path: Path) -> dict:
    stop_script = Path(cfg.stop_script)
    if not stop_script.is_absolute():
        stop_script = ROOT / stop_script
    cmd = [sys.executable, "-u", str(stop_script), "--wait", str(cfg.stop_wait_seconds)]
    rec: dict = {"cmd": cmd, "dry_run": cfg.dry_run, "executed": False, "rc": None,
                 "stdout_tail": [], "error": None}
    log_line(log_path, "[stop] 判据成立：" + "；".join(state["reasons"]))
    log_line(log_path, f"[stop] 命令：{' '.join(cmd)}")
    if cfg.dry_run:
        log_line(log_path, "[stop] --dry-run：只打印不执行（不退出游戏）")
        return rec
    if not stop_script.exists():
        rec["error"] = f"stop 脚本不存在：{stop_script}"
        log_line(log_path, f"[stop] !! {rec['error']}")
        return rec
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           errors="replace", timeout=cfg.stop_wait_seconds + 180)
        rec["executed"] = True
        rec["rc"] = r.returncode
        lines = (r.stdout or "").strip().splitlines()
        rec["stdout_tail"] = lines[-6:]
        for ln in rec["stdout_tail"]:
            log_line(log_path, f"[stop]   {ln}")
        if (r.stderr or "").strip():
            rec["stderr_tail"] = (r.stderr or "").strip().splitlines()[-4:]
            for ln in rec["stderr_tail"]:
                log_line(log_path, f"[stop]   stderr {ln}")
        log_line(log_path, f"[stop] rc={r.returncode}")
    except subprocess.TimeoutExpired:
        rec["error"] = "stop 脚本超时"
        log_line(log_path, f"[stop] !! {rec['error']}")
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
        log_line(log_path, f"[stop] !! {rec['error']}")
    return rec


def verify_after_stop(cfg: argparse.Namespace, log_path: Path) -> dict:
    pids = game_pids()
    port = port_listening(cfg.bridge_port)
    bridge_exists = Path(cfg.bridge_json).exists()
    rec = {"game_pids": pids, "game_process_count": len(pids),
           "bridge_json": str(cfg.bridge_json), "bridge_json_exists": bridge_exists,
           "port": cfg.bridge_port, "port_listening": port,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    log_line(log_path, f"[verify] 进程数={len(pids)} pids={pids}")
    log_line(log_path, f"[verify] bridge.json={cfg.bridge_json} exists={bridge_exists}")
    log_line(log_path, f"[verify] {cfg.bridge_port} LISTENING={port}")
    return rec


# ------------------------------------------------------------------ 日志/状态文件

def log_line(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")
    if _ECHO:
        try:
            print(text, flush=True)
        except Exception:  # noqa: BLE001 - 流被关掉也不能影响看护
            pass


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def fmt_state(state: dict) -> str:
    j = state["journal"]
    b = state["bridge"]
    return (f"brain pid={(state['pid'] or {}).get('pid')} alive={state['brain_alive']} · "
            f"journal lines={j['lines']} last={j['last_event']}@{j['last_t']} "
            f"age={j['stall_seconds']}s finish={j['finish']} stalled={state['stalled']} · "
            f"bridge exists={b['exists']} age={b['age_seconds']}s health={b['health_ok']} "
            f"lost={state['bridge_lost']} · trigger={state['trigger']}")


# ------------------------------------------------------------------ 主循环

def monitor(cfg: argparse.Namespace) -> int:
    log_path = Path(cfg.log_file)
    state_path = Path(cfg.state_file)
    log_line(log_path, f"[i] guardian start tag={cfg.tag} interval={cfg.interval}s "
                       f"stall={cfg.stall_seconds}s bridge_stale={cfg.bridge_stale_seconds}s "
                       f"dry_run={cfg.dry_run} once={cfg.once}")
    log_line(log_path, f"[i] pid_file={cfg.pid_file} journal={cfg.journal} "
                       f"bridge_json={cfg.bridge_json} stop={cfg.stop_script}")
    t0 = time.time()
    prev_key = None
    last_heartbeat = 0.0
    while True:
        state = evaluate(cfg)
        write_state(state_path, state)
        key = (state["brain_alive"], state["bridge_lost"], state["trigger"],
               state["pid"]["exists"], state["pid"]["parse_ok"])
        if key != prev_key or time.time() - last_heartbeat >= cfg.heartbeat_seconds:
            log_line(log_path, "[state] " + fmt_state(state))
            for reason in state["reasons"]:
                log_line(log_path, f"[state]   {reason}")
            last_heartbeat = time.time()
        prev_key = key

        if state["trigger"]:
            stop_rec = run_stop(cfg, state, log_path)
            verify = verify_after_stop(cfg, log_path)
            state["stop"] = stop_rec
            state["verify"] = verify
            write_state(state_path, state)
            if cfg.dry_run:
                log_line(log_path, "[exit] code=0（--dry-run 只演练，未退出游戏）")
                return 0
            if not stop_rec["executed"] and stop_rec["rc"] is None:
                log_line(log_path, f"[exit] code=3（stop 未执行：{stop_rec['error']}）")
                return 3
            if verify["game_process_count"] == 0:
                log_line(log_path, "[exit] code=0 ✅ 游戏已退出（进程 0）")
                return 0
            log_line(log_path, "[exit] code=2 ⚠ 已执行 stop，但游戏进程仍在跑 ⇒ 需要人工介入"
                               "（不要无人看护挂着）")
            return 2

        if cfg.once:
            log_line(log_path, "[exit] code=0（--once：只评估一拍，未触发）")
            return 0
        if cfg.max_seconds and time.time() - t0 >= cfg.max_seconds:
            log_line(log_path, f"[exit] code=0（--max-seconds {cfg.max_seconds}s 到，未触发）")
            return 0
        time.sleep(cfg.interval)


# ------------------------------------------------------------------ 脱离式起跑

def start_detached(argv: list[str]) -> int:
    """把自身以 DETACHED_PROCESS 重新拉起（活过 agent 回合边界）。"""
    tag = None
    for i, a in enumerate(argv):
        if a == "--tag" and i + 1 < len(argv):
            tag = argv[i + 1]
        elif a.startswith("--tag="):
            tag = a.split("=", 1)[1]
    if not tag:
        print("[x] --detach 需要显式 --tag")
        return 3
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    console = logs / f"{tag}-guardian.console.log"
    guardian_pid = logs / f"{tag}-guardian.pid"
    child_argv = [sys.executable, "-u", str(Path(__file__).resolve())]
    for a in argv:
        if a == "--detach":
            continue
        child_argv.append(a)
    child_argv.append("--no-detach")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    out_fh = open(console, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(child_argv, cwd=str(ROOT), env=env, stdout=out_fh,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
                                close_fds=True)
    finally:
        out_fh.close()
    guardian_pid.write_text(str(proc.pid), encoding="ascii")
    print("✅ 看护守护已脱离式起跑（返回后仍在跑）")
    print(f"    guardian PID = {proc.pid}")
    print(f"    tag          = {tag}")
    print(f"    log          = logs\\{tag}-guardian.log")
    print(f"    state        = logs\\{tag}-guardian-state.json")
    print(f"    console      = logs\\{tag}-guardian.console.log")
    return 0


# ------------------------------------------------------------------ 入口

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="长跑看护守护：脑死且收尾/超时后自动优雅退出游戏")
    ap.add_argument("--tag", required=True,
                    help="显式 run 标识（日志/pid 由它派生；无默认值 = 安全闸）")
    ap.add_argument("--pid-file", default="",
                    help="脑进程 pid 文件（默认 logs/<tag>.pid）")
    ap.add_argument("--journal", default="", help="长跑账本（默认 logs/<tag>.jsonl）")
    ap.add_argument("--log-file", default="", help="看护日志（默认 logs/<tag>-guardian.log）")
    ap.add_argument("--state-file", default="", help="状态快照（默认 logs/<tag>-guardian-state.json）")
    ap.add_argument("--bridge-json", default=os.path.join(
        os.environ.get("APPDATA", ""), "StardewValley", "AgentFarm", "bridge.json"),
        help="桥发现文件路径（默认 %%APPDATA%%\\StardewValley\\AgentFarm\\bridge.json）")
    ap.add_argument("--bridge-port", type=int, default=BRIDGE_PORT_DEFAULT)
    ap.add_argument("--bridge-stale-seconds", type=float, default=120.0,
                    help="bridge.json mtime 超过该秒数视为失联（默认 120）")
    ap.add_argument("--no-health-check", action="store_true", help="不做 GET /v1/health 探测")
    ap.add_argument("--stall-seconds", type=float, default=180.0,
                    help="脑死且账本超过该秒数无新行 ⇒ 视为收尾（默认 180）")
    ap.add_argument("--interval", type=float, default=10.0, help="轮询间隔秒（默认 10）")
    ap.add_argument("--heartbeat-seconds", type=float, default=300.0,
                    help="无状态变化时的心跳日志间隔秒（默认 300）")
    ap.add_argument("--stop-script", default=_STOP_SCRIPT_DEFAULT,
                    help="优雅退出脚本（默认 tools/stop-game.py；夹具可用假脚本）")
    ap.add_argument("--stop-wait-seconds", type=float, default=45.0,
                    help="传给 stop-game 的 --wait（默认 45）")
    ap.add_argument("--max-seconds", type=float, default=0.0,
                    help="最多看护多少秒（0=不限；仅测试/演练用）")
    ap.add_argument("--once", action="store_true", help="只评估一拍（夹具/演练）")
    ap.add_argument("--dry-run", action="store_true", help="只演练：命中判据也不执行 stop")
    ap.add_argument("--detach", action="store_true", help="脱离式起跑自身（返回后继续看护）")
    ap.add_argument("--no-detach", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-echo", action="store_true", help="日志不回显 stdout（默认回显）")
    return ap


def main(argv: list[str] | None = None) -> int:
    global _ECHO
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    _ECHO = not args.no_echo
    tag = args.tag.strip()
    if not tag:
        print("[x] --tag 不能为空")
        return 3
    args.tag = tag
    if not args.pid_file:
        args.pid_file = str(ROOT / "logs" / f"{tag}.pid")
    if not args.journal:
        args.journal = str(ROOT / "logs" / f"{tag}.jsonl")
    if not args.log_file:
        args.log_file = str(ROOT / "logs" / f"{tag}-guardian.log")
    if not args.state_file:
        args.state_file = str(ROOT / "logs" / f"{tag}-guardian-state.json")
    if args.detach and not args.no_detach:
        return start_detached(argv)
    return monitor(args)


if __name__ == "__main__":
    sys.exit(main())
