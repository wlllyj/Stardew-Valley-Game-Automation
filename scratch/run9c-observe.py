# -*- coding: utf-8 -*-
"""run9c 每日独立世界观测落盘（只读，Lead m01912 硬要求）。

run9c 每个游戏日至少一份**独立**的 `observe?detail=full` 原文，落到
`scratch\\run9c-observe-<day_key>.json`（day_key 形如 `summer13`）。
同日多份自动加 `-2`/`-3` 后缀（先到先得，**不覆盖**已有文件）。

用法
----
    python scratch\\run9c-observe.py --journal logs\\longrun-3day-llm-run9c.jsonl
    python scratch\\run9c-observe.py --journal ... --tag summer13      # 显式 day key
    python scratch\\run9c-observe.py --list                            # 列出已抓的观测
    python scratch\\run9c-observe.py --dry-run                         # 只推导 day key，不碰桥

退出码：0 = 成功（或 --list/--dry-run 正常）；2 = 桥不可达/观测失败；3 = 无法推导 day key（需 --tag）。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "brain"))

DEFAULT_JOURNAL = os.path.join(ROOT, "logs", "longrun-3day-llm-run9c.jsonl")
DEFAULT_DIR = os.path.join(ROOT, "scratch")
DEFAULT_PREFIX = "run9c-observe-"

DAY_KEY_RE = re.compile(r"^(?P<season>[a-z]+)(?P<day>\d+)$", re.I)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def journal_tail(path: str, want_day: bool = True):
    """返回 (行数, 末条记录, 最后一条带 day 的记录)。"""
    if not os.path.exists(path):
        return 0, None, None
    n = 0
    last = None
    last_day = None
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            last = rec
            if want_day:
                day = rec.get("day")
                if isinstance(day, list) and len(day) == 3:
                    last_day = day
                elif isinstance(day, dict) and day.get("season"):
                    last_day = [day.get("year"), day.get("season"), day.get("day")]
                fin = rec.get("final")
                if last_day is None and isinstance(fin, dict):
                    d = fin.get("day")
                    if isinstance(d, list) and len(d) == 3:
                        last_day = d
    return n, last, last_day


def day_key_from_journal(journal: str):
    n, last, day = journal_tail(journal)
    if not day:
        return None, n, last
    return f"{str(day[1]).lower()}{int(day[2])}", n, last


def next_path(out_dir: str, prefix: str, day_key: str, naming: str = "num") -> str:
    """同名绝不覆盖：naming=num ⇒ `-2`/`-3`…；naming=alpha ⇒ `-b`/`-c`…（run9d 卡面口径）。"""
    base = os.path.join(out_dir, f"{prefix}{day_key}.json")
    if not os.path.exists(base):
        return base
    i = 2
    while True:
        suffix = f"-{i}" if naming != "alpha" else f"-{chr(ord('a') + i - 1)}"
        cand = os.path.join(out_dir, f"{prefix}{day_key}{suffix}.json")
        if not os.path.exists(cand):
            return cand
        i += 1


def list_captures(out_dir: str, prefix: str):
    files = sorted(glob.glob(os.path.join(out_dir, f"{prefix}*.json")))
    rows = []
    for p in files:
        try:
            with io.open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            rows.append((os.path.basename(p), f"读取失败：{type(exc).__name__}", "", "", ""))
            continue
        obs = d.get("observe") or {}
        clock = obs.get("clock") or {}
        loc = (obs.get("location") or {}).get("name")
        rows.append((
            os.path.basename(p),
            d.get("captured_at") or obs.get("generatedAt") or "",
            f"{clock.get('season')} {clock.get('day')} tod={clock.get('timeOfDay')}",
            str(loc),
            f"worldSeq={obs.get('worldSeq')}",
        ))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=DEFAULT_JOURNAL)
    ap.add_argument("--out-dir", default=DEFAULT_DIR)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--tag", default=None, help="显式 day key（如 summer13）")
    ap.add_argument("--force", action="store_true", help="允许覆盖同名文件（默认不允许）")
    ap.add_argument("--naming", choices=("num", "alpha"), default="num",
                    help="同名时的后缀风格：num=-2/-3…；alpha=-b/-c…（run9d 卡面口径）")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="不调用桥，只打印将要写哪里")
    args = ap.parse_args()

    if args.list:
        rows = list_captures(args.out_dir, args.prefix)
        print(f"已抓观测 {len(rows)} 份（{args.out_dir}\\{args.prefix}*）：")
        for r in rows:
            print("  " + " | ".join(r))
        return 0

    day_key = args.tag
    if day_key:
        m = DAY_KEY_RE.match(day_key)
        if not m:
            print(f"day_key 形状不对：{day_key}（应为 summer13 这类）", file=sys.stderr)
            return 3
    else:
        day_key, n, last = day_key_from_journal(args.journal)
        print(f"账本 {os.path.basename(args.journal)}：{n} 行，末事件 = {(last or {}).get('event')}，"
              f"推导 day_key = {day_key}")
        if not day_key:
            print("无法从账本推导 day_key ⇒ 请用 --tag 显式指定（如 --tag summer13）", file=sys.stderr)
            return 3

    path = os.path.join(args.out_dir, f"{args.prefix}{day_key}.json")
    if os.path.exists(path) and not args.force:
        path = next_path(args.out_dir, args.prefix, day_key, args.naming)
    print(f"目标文件 = {path}")

    if args.dry_run:
        print("--dry-run：不调用桥、不写文件。")
        return 0

    from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

    try:
        c = BridgeClient()
        health = c.health()
        obs = c.observe("full")
    except BridgeError as exc:
        print(f"桥不可达/观测失败：{str(exc)[:300]}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"观测异常：{type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 2

    n, last, _ = journal_tail(args.journal)
    payload = {
        "captured_at": now_iso(),
        "day_key": day_key,
        "journal": os.path.relpath(args.journal, ROOT),
        "journal_lines": n,
        "journal_last_event": (last or {}).get("event"),
        "health": health,
        "observe": obs,
    }
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=1))
    clock = (obs or {}).get("clock") or {}
    loc = ((obs or {}).get("location") or {})
    print(f"已写入 {path}（{os.path.getsize(path)} B）")
    print(f"  clock = {clock.get('season')} {clock.get('day')} tod={clock.get('timeOfDay')} {clock.get('weather')}"
          f" | location = {loc.get('name')} isFarm={loc.get('isFarm')} | worldSeq = {(obs or {}).get('worldSeq')}"
          f" | tiles = {len(loc.get('tiles') or [])} truncated={loc.get('tilesTruncated')}"
          f" | ui.activeMenu = {((obs or {}).get('ui') or {}).get('activeMenu')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
