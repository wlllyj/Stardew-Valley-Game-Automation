"""task-40 B：独立审计 `docs/_run3-evidence.md` 的 5 条可核查断言。只读。

用法：python scratch/_t40_audit.py
"""
import json
import pathlib
import re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
J = ROOT / "logs" / "longrun-3day-llm-run3.jsonl"
OBS_START = ROOT / "logs" / "run3-observe-start.json"
OBS_END = ROOT / "logs" / "run3-observe-end.json"
SMAPI = pathlib.Path(r"C:\Users\admin\AppData\Roaming\StardewValley\ErrorLogs\SMAPI-latest.txt")
SAVES = pathlib.Path(r"C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035")
WINDOW_FROM = 2965  # 文档声明的 run3 窗口起点（SMAPI 行号）

print(f"journal exists={J.exists()} size={J.stat().st_size if J.exists() else '-'}")

rows = []
bad = 0
with J.open(encoding="utf-8") as fh:
    for i, line in enumerate(fh, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"  !! line {i} 解析失败：{exc}")
print(f"journal lines={len(rows)} bad={bad} events={dict(Counter(r.get('event') for r in rows))}")


def dig(obj, *keys):
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


print("\n=== 断言3：day_start / day_end 逐日 ===")
for r in rows:
    ev = r.get("event")
    if ev == "day_start":
        print(f"  day_start day={r.get('day')} loc={r.get('location')!r} tod={r.get('timeOfDay')} "
              f"crops={r.get('crops')} unwatered={r.get('unwatered')}")
    elif ev == "day_end":
        d = r.get("day_end") or r
        end = d.get("final") or {}
        fw = d.get("final_water") or {}
        checks = d.get("checks") or {}
        print(f"  day_end  day={d.get('day')} ended_by={d.get('ended_by')} verified={d.get('verified')}")
        print(f"           final.location={dig(end, 'location')!r} counts_scope={end.get('counts_scope')!r} "
              f"tillable={end.get('tillable')} crops={end.get('crops')}")
        print(f"           final_water={fw}")
        print(f"           checks={checks}")
        print(f"           day_after={d.get('day_after')}")

print("\n=== 断言1：farm.dryCrops / dry 读数链 ===")
for label, path in (("start", OBS_START), ("end", OBS_END)):
    if path.exists():
        o = json.loads(path.read_text(encoding="utf-8"))
        farm = o.get("farm") or {}
        can = dig(o, "player", "wateringCan") or {}
        print(f"  obs-{label}: day={dig(o,'clock','year')}/{dig(o,'clock','season')}/{dig(o,'clock','day')} "
              f"loc={dig(o,'location','name')!r} farm.dryCrops={farm.get('dryCrops')} "
              f"farm.crops={farm.get('crops')} farm.unwateredCrops={farm.get('unwateredCrops')} "
              f"waterLeft={can.get('waterLeft')}")
    else:
        print(f"  obs-{label}: 缺文件 {path}")

print("\n=== 断言2：waterLeft 在账本里的读数 ===")
def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj

hits = 0
for r in rows:
    for p, v in walk(r):
        if p.endswith("waterLeft"):
            hits += 1
            print(f"  line#{r.get('t')} {r.get('event')} {p}={v}")
print(f"  waterLeft 命中 {hits} 处")

print("\n=== 断言4：SMAPI NewDay / SaveGame 行号 ===")
if SMAPI.exists():
    text = SMAPI.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"  SMAPI 行数={len(text)}（文档称 2965→4236）")
    pats = {
        "SynchronizingNewDay": re.compile(r"Synchronizing 'NewDay'"),
        "beforeSave": re.compile(r"Context: before save"),
        "SaveCalled": re.compile(r"SaveGame\.Save\(\) called"),
        "SyncSave": re.compile(r"Synchronizing 'Save'"),
        "SaveCompleted": re.compile(r"SaveGame\.Save\(\) completed"),
        "AfterSave": re.compile(r"Context: after save, starting"),
    }
    for name, pat in pats.items():
        allhits = [(i, text[i - 1]) for i in range(1, len(text) + 1) if pat.search(text[i - 1])]
        inwin = [h for h in allhits if h[0] >= WINDOW_FROM]
        print(f"  {name}: 全文 {len(allhits)} 处；窗口(>={WINDOW_FROM}) {len(inwin)} 处 "
              f"行号 {[h[0] for h in inwin][:8]}")
    for i in range(WINDOW_FROM - 1, len(text)):
        s = text[i]
        if re.search(r"Synchronizing 'NewDay'|SaveGame\.Save\(\) completed|Context: after save", s):
            print(f"    L{i+1}: {s.strip()[:110]}")
    kws = ["ERROR", "Disconnected", "Disposing", "ClosedGame", "Exception", "soft_oal", "no_day_progress"]
    for k in kws:
        print(f"  关键词 {k}: 窗口内 {sum(1 for i in range(WINDOW_FROM-1, len(text)) if k in text[i])} 处")
else:
    print(f"  !! 缺 SMAPI 日志 {SMAPI}")

print("\n=== 断言4b：存档 mtime/size ===")
if SAVES.exists():
    for p in sorted(SAVES.iterdir(), key=lambda x: x.stat().st_mtime):
        st = p.stat()
        print(f"  {p.name}: size={st.st_size} mtime={st.st_mtime}")
else:
    print(f"  !! 缺存档目录 {SAVES}")

print("\n=== 断言5：崩溃/掉线/模态 ===")
print(f"  账本事件 modal_timeout={sum(1 for r in rows if r.get('event')=='modal_timeout')} "
      f"bridge_down={sum(1 for r in rows if r.get('event')=='bridge_down')} "
      f"watchdog_stop={sum(1 for r in rows if r.get('event')=='watchdog_stop')} "
      f"no_day_progress={sum(1 for r in rows if r.get('event')=='no_day_progress')} "
      f"modal_dismissed={sum(1 for r in rows if r.get('event')=='modal_dismissed')}")
fw = [r for r in rows if r.get("event") == "finish"]
print(f"  finish={fw}")
