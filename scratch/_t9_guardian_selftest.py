# -*- coding: utf-8 -*-
"""task-9 夹具自测：tools/run-guardian.py 的「脑死⇒触发」「脑活⇒不触发」两态 + 安全闸/超时/演练/脱离式。

全部离线：假 pid 文件、假账本、假 bridge.json、**假 stop 脚本**（scratch/_g_fake_stop.py）。
绝不调用真 tools/stop-game.py、不发桥请求、不 taskkill、不碰存档/游戏。

用法（仓库根，PYTHONUTF8=1）：
    python scratch\\_t9_guardian_selftest.py

夹具与日志留在 scratch\\_gtest\\<case>\\ 下供复核；脱离式用例产物在 logs\\t9-F-detach-guardian.*。
退出码：0 = 全部用例 PASS；1 = 有 FAIL。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools" / "run-guardian.py"
FAKE_STOP = ROOT / "scratch" / "_g_fake_stop.py"
FIX = ROOT / "scratch" / "_gtest"
PY = sys.executable
DEAD_PID = 999999

results: list[tuple[str, bool, str]] = []
_buf: list[str] = []
OUT = ROOT / "logs" / "t9-guardian-selftest.txt"


def log(msg: str) -> None:
    _buf.append(msg)
    print(msg, flush=True)


def flush_out() -> None:
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(_buf) + "\n", encoding="utf-8")
    except OSError:
        pass


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    log(("PASS " if cond else "**FAIL** ") + name + (f"  [{detail}]" if detail else ""))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def run_guard(tag: str, extra: list[str], env_extra: dict[str, str] | None = None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    cmd = [PY, "-u", str(GUARD), "--tag", tag, *extra]
    return subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True,
                          errors="replace", timeout=180)


def fixture(tag: str, *, dead: bool = True, finish: bool = False,
            journal_age: float = 0.0, bridge: bool = True) -> dict:
    d = FIX / tag
    d.mkdir(parents=True, exist_ok=True)
    pid = d / "brain.pid"
    journal = d / "journal.jsonl"
    logf = d / "guardian.log"
    state = d / "state.json"
    bridgep = d / "bridge.json"
    receipt = d / "stop-receipt.json"
    pid.write_text(str(DEAD_PID if dead else os.getpid()), encoding="ascii")
    rows = [{"event": "day_start", "t": 0.0, "day": [1, "winter", 7]}]
    if finish:
        rows.append({"event": "finish", "t": 100.0, "code": 0})
    else:
        rows.append({"event": "day_end", "t": 90.0, "verified": True})
    write_jsonl(journal, rows)
    if journal_age:
        os.utime(journal, (time.time() - journal_age, time.time() - journal_age))
    if bridge:
        bridgep.write_text(json.dumps({"schema": "agentfarm-bridge/1", "port": 17890,
                                       "pid": 55555, "modVersion": "0.7.99"},
                                      ensure_ascii=False), encoding="utf-8")
    return {"dir": d, "pid": pid, "journal": journal, "log": logf, "state": state,
            "bridge": bridgep if bridge else d / "no-such-bridge.json", "receipt": receipt}


def args_for(fx: dict, extra: list[str] | None = None) -> list[str]:
    return ["--pid-file", str(fx["pid"]), "--journal", str(fx["journal"]),
            "--bridge-json", str(fx["bridge"]), "--log-file", str(fx["log"]),
            "--state-file", str(fx["state"]), "--stop-script", str(FAKE_STOP),
            "--stop-wait-seconds", "1", *(extra or [])]


def dump_log(name: str, path: Path, n: int = 8) -> None:
    lines = read(path).splitlines()
    log(f"  —— {name} 日志尾 {min(n, len(lines))} 行 ——")
    for ln in lines[-n:]:
        log("  " + ln)


def no_real_game() -> tuple[int, bool]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq StardewModdingAPI.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="replace").stdout
    n = sum(1 for ln in out.splitlines() if ln.lower().startswith("stardewmoddingapi"))
    real_bridge = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "AgentFarm" / "bridge.json"
    return n, real_bridge.exists()


def main() -> int:
    log(f"# task-9 run-guardian 夹具自测 @ {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    log(f"# python={PY}")
    log(f"# guardian={GUARD}")
    if FIX.exists():
        shutil.rmtree(FIX)
    FIX.mkdir(parents=True)
    n_game0, real_bridge0 = no_real_game()
    log(f"# 真机基线：StardewModdingAPI.exe 进程数={n_game0}，真 bridge.json 存在={real_bridge0}")
    log("")

    # ---------- 用例 A：脑死 + finish ⇒ 触发 stop（假脚本） ----------
    log("## A 脑死 + finish 已写入 ⇒ 必须触发 stop")
    fx = fixture("A-dead-finish", dead=True, finish=True)
    r = run_guard("t9-A-dead-finish", args_for(fx, ["--once"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("A rc=0", r.returncode == 0, f"rc={r.returncode}")
    check("A 判据成立 ⇒ 假 stop 被调用（receipt 存在）", fx["receipt"].exists())
    receipt = json.loads(read(fx["receipt"])) if fx["receipt"].exists() else {}
    check("A 假 stop 收到 --wait 参数", "--wait" in (receipt.get("argv") or []),
          f"argv={receipt.get('argv')}")
    check("A 日志含 时间/判据/finish/stop rc/进程 0", all(s in logt for s in (
        "[stop] 判据成立", "finish 已出现", "[stop] rc=0", "[verify] 进程数=0")))
    check("A 日志含 bridge.json / 17890 复核", "[verify] bridge.json=" in logt and
          "17890 LISTENING=False" in logt)
    check("A 日志含退出结论", "[exit] code=0" in logt)
    dump_log("A", fx["log"])
    log("")

    # ---------- 用例 B：脑死 + 无 finish ⇒ 未超时不触发；超时后触发 ----------
    log("## B 脑死 + 无 finish：账本新鲜 ⇒ 等；把 mtime 回拨到超时 ⇒ 触发")
    fx = fixture("B-dead-nofinish", dead=True, finish=False, journal_age=0.0)
    r = run_guard("t9-B1", args_for(fx, ["--once", "--stall-seconds", "180"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("B1 未超时 ⇒ 不触发（receipt 不存在）", not fx["receipt"].exists())
    check("B1 日志写明「继续观察」", "继续观察" in logt)
    check("B1 rc=0", r.returncode == 0, f"rc={r.returncode}")
    os.utime(fx["journal"], (time.time() - 600, time.time() - 600))  # 回拨 10 分钟
    r = run_guard("t9-B2", args_for(fx, ["--once", "--stall-seconds", "180"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("B2 超时无新行 ⇒ 触发（receipt 存在）", fx["receipt"].exists())
    check("B2 日志含「账本已 ...s 无新行」判据", "无新行" in logt, "含超时判据")
    check("B2 rc=0", r.returncode == 0, f"rc={r.returncode}")
    dump_log("B", fx["log"])
    log("")

    # ---------- 用例 C：脑活 + finish + 桥失联 ⇒ 只告警不退出 ----------
    log("## C 脑活（pid 存活）+ finish 已写入 + 桥失联 ⇒ 只告警，不调用 stop")
    fx = fixture("C-alive-finish-nobridge", dead=False, finish=True, bridge=False)
    r = run_guard("t9-C", args_for(fx, ["--once"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("C 不触发（receipt 不存在）", not fx["receipt"].exists())
    check("C 日志含「脑活但桥失联 ⇒ 只告警」", "脑活但桥失联" in logt and "只告警" in logt)
    check("C rc=0", r.returncode == 0, f"rc={r.returncode}")
    check("C 日志无 stop 调用", "[stop]" not in logt)
    dump_log("C", fx["log"])
    log("")

    # ---------- 用例 D：PID 文件缺失 ⇒ 安全闸不触发 ----------
    log("## D PID 文件缺失（无法证明脑死）⇒ 安全闸：不触发")
    fx = fixture("D-missing-pid", dead=True, finish=True)
    fx["pid"].unlink()
    r = run_guard("t9-D", args_for(fx, ["--once"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("D 不触发（receipt 不存在）", not fx["receipt"].exists())
    check("D 日志含「PID 文件缺失」安全闸", "PID 文件缺失" in logt)
    check("D rc=0", r.returncode == 0, f"rc={r.returncode}")
    dump_log("D", fx["log"])
    log("")

    # ---------- 用例 E：--dry-run 命中判据也不调用 stop ----------
    log("## E --dry-run：判据成立只打印命令，不调用 stop-game")
    fx = fixture("E-dryrun", dead=True, finish=True)
    r = run_guard("t9-E", args_for(fx, ["--once", "--dry-run"]),
                  {"GUARDIAN_FAKE_RECEIPT": str(fx["receipt"])})
    logt = read(fx["log"])
    check("E 不触发 stop（receipt 不存在）", not fx["receipt"].exists())
    check("E 日志含 --dry-run 与假 stop 命令", "--dry-run" in logt and "_g_fake_stop.py" in logt)
    check("E 日志含退出结论", "[exit] code=0（--dry-run" in logt)
    check("E rc=0", r.returncode == 0, f"rc={r.returncode}")
    dump_log("E", fx["log"])
    log("")

    # ---------- 用例 F：--detach 脱离式起跑（--once 子进程） ----------
    log("## F --detach：脱离式起跑自身（子进程 --once 评估后退出）")
    fx = fixture("F-detach", dead=False, finish=False, bridge=False)
    r = run_guard("t9-F-detach", args_for(fx, ["--once", "--detach"]), {})
    check("F 起跑 rc=0", r.returncode == 0, f"rc={r.returncode}")
    check("F 打印「已脱离式起跑」", "已脱离式起跑" in (r.stdout or ""), (r.stdout or "").strip()[:120])
    gpid_path = ROOT / "logs" / "t9-F-detach-guardian.pid"
    gconsole = ROOT / "logs" / "t9-F-detach-guardian.console.log"
    deadline = time.time() + 25
    while time.time() < deadline and not (read(gconsole).count("[exit] code=0") >= 1):
        time.sleep(0.5)
    check("F guardian pid 文件已写", gpid_path.exists(), str(gpid_path))
    check("F console 出现 start/exit", "guardian start" in read(gconsole) and "[exit] code=0" in read(gconsole))
    if gpid_path.exists():
        gp = gpid_path.read_text(encoding="utf-8", errors="replace").strip()
        gone = False
        for _ in range(20):
            out = subprocess.run(["tasklist", "/FI", f"PID eq {gp}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace").stdout
            if gp not in out:
                gone = True
                break
            time.sleep(0.5)
        check("F --once 子进程已自行退出（无残留看护进程）", gone, f"guardian pid={gp}")
    log(f"  —— F console 尾 6 行 ——")
    for ln in read(gconsole).splitlines()[-6:]:
        log("  " + ln)
    log("")

    # ---------- 收尾核对：真机没被碰过 ----------
    n_game1, real_bridge1 = no_real_game()
    check("真机未被本自测触碰（游戏进程数仍为 0）", n_game1 == 0, f"n={n_game1}")
    check("真 bridge.json 未被创建", not real_bridge1)

    passed = sum(1 for _, ok, _ in results if ok)
    log("")
    log(f"# RESULT: {passed}/{len(results)} PASS")
    if passed != len(results):
        log("# 失败项：")
        for name, ok, detail in results:
            if not ok:
                log(f"  - {name} [{detail}]")
        flush_out()
        return 1
    flush_out()
    return 0


if __name__ == "__main__":
    sys.exit(main())
