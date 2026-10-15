"""task-94 只读：run7（对照 run5/run6）播种与开垦"散乱"基线量化。

只读账本；结果写 UTF-8 文本文件（python 自己写，避免 pwsh 重定向成 UTF-16）。
用法： python scratch/_t94_baseline.py <out.txt>
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGERS = {
    "run5": os.path.join(ROOT, "logs", "longrun-3day-llm-run5.jsonl"),
    "run6": os.path.join(ROOT, "logs", "longrun-3day-llm-run6.jsonl"),
    "run7": os.path.join(ROOT, "logs", "longrun-3day-llm-run7.jsonl"),
}
ZONE_RE = re.compile(r"作业区\s*([a-z_]+)")
DAY_RE = re.compile(r"目标\s*(\d+)\s*步：做成\s*(\d+)、跳过\s*(\d+)、失败\s*(\d+)")
STAGES_OF_INTEREST = ("plant_area", "till_area", "clear_dead")


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                rows.append((i, json.loads(line)))
    return rows


def sessions(rows):
    """按 day_start 切会话，返回 [(start_line, start_ev, [events])]"""
    out, cur = [], None
    for ln, ev in rows:
        if ev.get("event") == "day_start":
            cur = [ln, ev, []]
            out.append(cur)
        elif cur is not None:
            cur[2].append((ln, ev))
    return out


def comps(points):
    """四邻连通块（曼哈顿距离 1）。"""
    pts = {tuple(p) for p in points}
    seen, sizes = set(), []
    for p in pts:
        if p in seen:
            continue
        stack, size = [p], 0
        seen.add(p)
        while stack:
            x, y = stack.pop()
            size += 1
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) in pts and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        sizes.append(size)
    sizes.sort(reverse=True)
    return sizes


def nn_stats(points):
    if len(points) < 2:
        return None
    pts = [tuple(p) for p in points]
    dists = []
    for i, a in enumerate(pts):
        best = min(math.dist(a, b) for j, b in enumerate(pts) if j != i)
        dists.append(best)
    dists.sort()
    return {
        "n": len(pts),
        "mean": sum(dists) / len(dists),
        "median": dists[len(dists) // 2],
        "max": dists[-1],
    }


def main(out_path):
    lines = []

    def w(s=""):
        lines.append(s)

    for name, path in LEDGERS.items():
        if not os.path.isfile(path):
            w(f"== {name}: 缺文件")
            continue
        rows = load(path)
        w(f"===== {name}（{len(rows)} 行）=====")
        for si, (sln, sev, evs) in enumerate(sessions(rows), 1):
            day = sev.get("day")
            day_end = None
            for ln, ev in evs:
                if ev.get("event") == "day_end":
                    day_end = (ln, ev)
            if day_end is None:
                w(f"-- 第{si}天 {day}：没有 day_end（跳过）")
                continue
            deln, dev = day_end
            stages = [s for s in (dev.get("stages") or [])
                      if isinstance(s, dict) and s.get("stage") in STAGES_OF_INTEREST]
            w(f"-- 第{si}天 {day} day_start L{sln} day_end L{deln} ended_by={dev.get('ended_by')}")
            fin = dev.get("final") or {}
            w(f"   final: crops={fin.get('crops')} tillable={fin.get('tillable')} "
              f"ripe={fin.get('ripe')} seeds={fin.get('seeds')} "
              f"farm={json.dumps(fin.get('farm'), ensure_ascii=False)[:200]}")
            for st in stages:
                w("   stage " + json.dumps(st, ensure_ascii=False)[:260])
            # 时间序的 plant/till 阶段事件
            seq = []
            for ln, ev in evs:
                e = ev.get("event")
                if e == "outcome" and ev.get("kind") in STAGES_OF_INTEREST:
                    z = ZONE_RE.search(str(ev.get("reason") or ""))
                    m = DAY_RE.search(str(ev.get("reason") or ""))
                    seq.append((ln, "outcome", ev.get("kind"), (z.group(1) if z else ""),
                                tuple(int(x) for x in m.groups()) if m else None))
                elif e in ("stage_exhausted", "stage_no_target"):
                    if ev.get("stage") in STAGES_OF_INTEREST:
                        seq.append((ln, e, ev.get("stage"), str(ev.get("zone") or ""), None))
            w("   时间序（plant/till）：")
            for ln, kind, task, zone, counts in seq:
                w(f"     L{ln} {kind} {task} zone={zone or '?'} counts={counts}")
            zones = [z for _, _, _, z, _ in seq if z]
            runs = []
            for z in zones:
                if not runs or runs[-1] != z:
                    runs.append(z)
            w(f"   zone 序列={zones} 去重={sorted(set(zones))} 连续段={runs} "
              f"切换次数={max(0, len(runs) - 1)}")
            # plot 事件（锚点）
            plots = [(ln, ev) for ln, ev in evs if ev.get("event") == "plot"]
            w(f"   plot×{len(plots)}：" + "；".join(
                f"L{ln} {ev.get('zone')} anchor={ev.get('anchor')} tiles={ev.get('tiles')}"
                for ln, ev in plots))
            anchors = [tuple(ev["anchor"]) for _, ev in plots if isinstance(ev.get("anchor"), list)]
            if len(anchors) >= 2:
                d = [round(math.dist(anchors[i], anchors[i + 1]), 2) for i in range(len(anchors) - 1)]
                w(f"   相邻 plot 锚点距离={d} 最近邻={nn_stats(anchors)}")
            # work_spot / stage_midway_leftover
            ws = [ev for _, ev in evs if ev.get("event") == "work_spot"]
            if ws:
                w(f"   work_spot×{len(ws)}：" + "；".join(
                    f"{x.get('zone') or '(空)'}tiles={x.get('tiles')}" for x in ws[:8]))
            ml = [ev for _, ev in evs if ev.get("event") == "stage_midway_leftover"]
            if ml:
                w(f"   stage_midway_leftover×{len(ml)}：" + "；".join(
                    f"{x.get('stage')}@L{x.get('round')} tiles={x.get('tiles')} leftover={x.get('leftover')}"
                    for x in ml))
            # 失败/不可达坐标（唯一有坐标的一类）
            doomed = []
            for _, ev in evs:
                if ev.get("event") == "stage_exhausted" and isinstance(ev.get("tiles"), list):
                    doomed += [tuple(t) for t in ev["tiles"]]
                if ev.get("event") == "unreachable" and isinstance(ev.get("tile"), list):
                    doomed.append(tuple(ev["tile"]))
                if ev.get("event") == "tool_refused" and isinstance(ev.get("tile"), list):
                    doomed.append(tuple(ev["tile"]))
            if doomed:
                cs = comps(doomed)
                w(f"   失败/不可达坐标×{len(set(doomed))}（去重）连通块={cs} 占比最大={cs[0] / len(set(doomed)):.2f} "
                  f"最近邻={nn_stats(list(set(doomed)))}")
            w("")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "scratch", "_t94_baseline.txt"))
