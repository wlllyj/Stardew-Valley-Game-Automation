# -*- coding: utf-8 -*-
"""一次性探针（run2 前置）：把"睡觉会不会把游戏搞崩"单独隔离出来验一次。

背景：2026-10-11 21:59:59 游戏在 `soft_oal.dll`（OpenAL Soft）内以 0xc0000409 硬崩，
崩溃前最后一条日志是 21:56:00 的 `sleep`（Sleep_Yes）。所以先用一次**单次睡觉**探针
分辨"是 sleep 触发崩溃"还是"音频库偶发"，再决定要不要拿 90 分钟长跑去赌。

判据（三条全中才算通过）：
  ① 日期变了：`clock.(year,season,day)` 前进（observe 差分，唯一权威）；
  ② 进程还活着：`pid_alive(bridge.json 的 pid)` 为 True（Win32 OpenProcess，不用 os.kill）；
  ③ 跨日落盘：存档主文件 mtime 前进。

纪律：只调 brain 的 BridgeClient；不合成键鼠、不改游戏状态、不 quit。
回执（reason）只做参考，**不作为证据**。
用法：
    set PYTHONPATH=<repo>\\brain  &  set PYTHONUTF8=1
    python scratch\\probe_sleep.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, load_bridge_info, pid_alive  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
APPDATA = Path(os.environ.get("APPDATA", ""))
SAVE_DIR = APPDATA / "StardewValley" / "Saves" / "Wahaha_450799035"
SAVE_MAIN = SAVE_DIR / "Wahaha_450799035"
SAVE_INFO = SAVE_DIR / "SaveGameInfo"
SMAPI_LOG = APPDATA / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
LOG_OUT = REPO / "logs" / "probe-sleep-run2.txt"

OUT: list[str] = []


def p(text: str = "") -> None:
    print(text, flush=True)
    OUT.append(str(text))


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def obs_of(client: BridgeClient, label: str) -> dict:
    """观测快照（唯一证据来源）。"""
    r = client.observe("summary")
    clock = r.get("clock") or {}
    player = r.get("player") or {}
    d = {
        "at": stamp(),
        "worldSeq": r.get("worldSeq"),
        "hasSaveLoaded": r.get("hasSaveLoaded"),
        "year": clock.get("year"),
        "season": clock.get("season"),
        "day": clock.get("day"),
        "timeOfDay": clock.get("timeOfDay"),
        "weather": clock.get("weather"),
        "location": player.get("location"),
        "tile": player.get("tile"),
        "money": player.get("money"),
        "stamina": player.get("stamina"),
        "maxStamina": player.get("maxStamina"),
        "isInBed": player.get("isInBed"),
    }
    p(f"[observe:{label}] {json.dumps(d, ensure_ascii=False)}")
    return d


def file_state(path: Path) -> dict | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return {
        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": st.st_mtime,
        "size": st.st_size,
    }


def save_state() -> dict:
    return {"main": file_state(SAVE_MAIN), "info": file_state(SAVE_INFO)}


CRASH_RE = re.compile(r"(?i)shut ?down|game ended|exiting|crash|fatal|unhandled|BEX64|0xc0000409")


def smapi_state() -> dict:
    try:
        st = SMAPI_LOG.stat()
        lines = SMAPI_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"error": str(exc)}
    return {
        "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "lines": len(lines),
        "tail": lines[-25:],
        "crash_hits": [l for l in lines[-200:] if CRASH_RE.search(l)],
    }


def key(d: dict) -> tuple:
    return (d.get("year") or 0, str(d.get("season") or ""), d.get("day") or 0)


def main() -> int:
    p("== 单次睡觉探针（run2 前置）==")
    p(f"开始 {stamp()}  ALSOFT_DRIVERS={os.environ.get('ALSOFT_DRIVERS')!r}")
    p(f"存档 {SAVE_MAIN}")
    p(f"SMAPI 日志 {SMAPI_LOG}")

    try:
        info = load_bridge_info()
    except BridgeError as exc:
        p(f"[FATAL] 读不到 bridge.json：{exc}")
        _flush()
        return 2
    pid = info.pid
    p(f"[bridge.json] port={info.port} pid={pid} modVersion={info.mod_version}")
    p(f"[pid_alive] 睡前：{pid_alive(pid)}")

    client = BridgeClient(timeout=10.0)
    try:
        h = client.health()
        p(f"[health] {json.dumps({k: h.get(k) for k in ('ok', 'status', 'modVersion', 'hasSaveLoaded', 'worldSeq')}, ensure_ascii=False)}")
        p(f"[health.runtime] {json.dumps(h.get('runtime'), ensure_ascii=False)}")
    except BridgeError as exc:
        p(f"[FATAL] 桥不健康：{exc}")
        _flush()
        return 2

    before = obs_of(client, "before")
    save_before = save_state()
    smapi_before = smapi_state()
    p(f"[save:before] {json.dumps(save_before, ensure_ascii=False)}")
    p(f"[smapi:before] mtime={smapi_before.get('mtime')} lines={smapi_before.get('lines')}")

    p("")
    p("[sleep] 调 BridgeClient().sleep(timeout_ms=180000) ...")
    t0 = time.time()
    sleep_resp = None
    sleep_err = None
    try:
        sleep_resp = client.sleep(timeout_ms=180000)
    except BridgeError as exc:
        sleep_err = exc
    except Exception as exc:  # noqa: BLE001
        sleep_err = exc
    p(f"[sleep] 耗时 {time.time() - t0:.1f}s")
    if sleep_resp is not None:
        # 回执：只作参考，不作证据
        p(f"[sleep.receipt] {json.dumps(sleep_resp, ensure_ascii=False)[:900]}")
    else:
        p(f"[sleep.error] {type(sleep_err).__name__}: {sleep_err}")

    time.sleep(3.0)

    alive_after = pid_alive(pid)
    after = None
    obs_err = None
    try:
        after = obs_of(client, "after")
    except Exception as exc:  # noqa: BLE001
        obs_err = exc
        p(f"[observe:after][ERROR] {type(obs_err).__name__}: {obs_err}")

    save_after = save_state()
    smapi_after = smapi_state()
    p(f"[save:after]  {json.dumps(save_after, ensure_ascii=False)}")
    p(f"[smapi:after]  mtime={smapi_after.get('mtime')} lines={smapi_after.get('lines')}")
    p(f"[pid_alive] 睡后：{alive_after}")

    p("")
    p("--- SMAPI 日志尾部 25 行 ---")
    for line in smapi_after.get("tail", []):
        p("  " + line)
    hits = smapi_after.get("crash_hits") or []
    p(f"--- 尾部 200 行内的崩溃/shutdown 关键词命中：{len(hits)} 条 ---")
    for line in hits:
        p("  ! " + line)

    p("")
    if after is None:
        c1 = False
    else:
        c1 = key(after) > key(before)
    c2 = alive_after is True
    main_before = (save_before.get("main") or {}).get("epoch")
    main_after = (save_after.get("main") or {}).get("epoch")
    c3 = bool(main_before is not None and main_after is not None and main_after > main_before)

    p("== 三判据 ==")
    p(f"  ① 日期前进   : {c1}   before={key(before)}  after={key(after) if after else 'N/A'}")
    p(f"  ② 进程还活着 : {c2}   pid={pid}  pid_alive={alive_after}")
    p(f"  ③ 存档 mtime 前进: {c3}  before={(save_before.get('main') or {}).get('mtime')}  after={(save_after.get('main') or {}).get('mtime')}")
    verdict = "PASS" if (c1 and c2 and c3) else "FAIL"
    p(f"PROBE VERDICT: {verdict}")
    p(f"结束 {stamp()}")
    _flush()
    return 0 if verdict == "PASS" else 1


def _flush() -> None:
    try:
        LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
        LOG_OUT.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    except OSError as exc:  # pragma: no cover
        print(f"[warn] 写 {LOG_OUT} 失败：{exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
