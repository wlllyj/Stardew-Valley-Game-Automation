"""task-169 只读取证：把 runA/runB 账本里所有与 `harvest` 有关的记录**按格/按日/按事件**聚合。

用法：
  python scratch\\_harvest_audit.py [journal ...] [--json]
  默认 journal = logs\\longrun-runA-0732.jsonl + logs\\longrun-runB-0732.jsonl

输出：
  ① 逐格汇总（跨账本）：tile / 出现账本 / 尝试次数 / 首次-末次 t / 日 / zone / code / 账本行
  ② 逐日汇总：day / day_end.stages[harvest] 合计 / stage_stop_named 次数 / first-last t
  ③ 判据链：intent_verdict(harvest) / decision(harvest reason) / review.work_reasons + **缺失项**
  ④ 该格出现在哪些事件里（Lead m07935 Q1：窗口字段缺证据时的可查面）
  ⑤ 守卫与开路：intent_vetoed(sleep) 理由计数、frontier_clear 概况、「有 1 格作物熟了」次数
  ⑥ 结论行：harvest 成功/失败步数

⚠ 只读：只读账本、只打印，不写 logs/。
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_JOURNALS = [
    ("A", r"logs\longrun-runA-0732.jsonl"),
    ("B", r"logs\longrun-runB-0732.jsonl"),
]

TILE_KEYS = ("tile", "tiles", "coords", "cleared", "cleared_tiles", "targets")


def walk_coords(obj, out: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in TILE_KEYS or k.endswith("_tiles"):
                walk_coords(v, out)
            else:
                walk_coords(v, out)
    elif isinstance(obj, list):
        if len(obj) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in obj):
            out.add((obj[0], obj[1]))
        else:
            for v in obj:
                walk_coords(v, out)


def as_label(day) -> str:
    return " ".join(str(x) for x in day) if isinstance(day, list) else str(day)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    journals = [(str(i), a) for i, a in enumerate(args)] if args else DEFAULT_JOURNALS
    as_json = "--json" in sys.argv

    data = {}
    for tag, path in journals:
        try:
            rows = [json.loads(l) for l in io.open(path, encoding="utf-8", errors="replace") if l.strip()]
        except FileNotFoundError:
            print(f"== {tag} 缺文件 {path}")
            continue
        data[tag] = rows

    harvest_outcomes: list[tuple[str, int, dict]] = []
    stage_recs: list[tuple[str, int, dict]] = []
    day_ends: list[tuple[str, int, dict]] = []
    verdicts: list[tuple[str, int, dict]] = []
    reviews: list[tuple[str, int, dict]] = []
    decisions: list[tuple[str, int, dict]] = []
    vetoes: list[tuple[str, int, dict]] = []
    frontiers: list[tuple[str, int, dict]] = []
    mentions: dict[tuple[int, int], list[tuple[str, int, str, dict]]] = defaultdict(list)

    for tag, rows in data.items():
        for i, r in enumerate(rows, 1):
            ev = r.get("event")
            if ev == "outcome" and r.get("kind") == "harvest":
                harvest_outcomes.append((tag, i, r))
            elif ev in ("stage_stop_named", "stage_shortfall", "stage_exhausted") and r.get("stage") == "harvest":
                stage_recs.append((tag, i, r))
            elif ev == "day_end":
                day_ends.append((tag, i, r))
            elif ev == "intent_verdict":
                verdicts.append((tag, i, r))
            elif ev == "review":
                reviews.append((tag, i, r))
            elif ev == "decision":
                decisions.append((tag, i, r))
            elif ev == "intent_vetoed":
                vetoes.append((tag, i, r))
            elif ev == "frontier_clear":
                frontiers.append((tag, i, r))
            coords = set()
            walk_coords(r, coords)
            for c in coords:
                mentions[c].append((tag, i, str(ev), r))

    spans: dict[str, list[tuple[float, float, str]]] = {}
    for tag, rows in data.items():
        starts = [r for r in rows if r.get("event") == "day_start"]
        ends = [r for r in rows if r.get("event") == "day_end"]
        sp: list[tuple[float, float, str]] = []
        for k, s in enumerate(starts):
            lo = float(s.get("t") or 0.0)
            hi = float(ends[k].get("t") or 0.0) if k < len(ends) else float("inf")
            label = as_label((ends[k].get("day") if k < len(ends) else None) or s.get("day"))
            sp.append((lo, hi, label))
        spans[tag] = sp

    def day_of(tag: str, t) -> str:
        try:
            tv = float(t or 0.0)
        except (TypeError, ValueError):
            return "?"
        for lo, hi, label in spans.get(tag, []):
            if lo <= tv < hi:
                return label
        return "?"

    by_tile: dict[tuple[int, int], dict] = {}
    for tag, i, r in stage_recs:
        for tile in r.get("tiles") or []:
            if not (isinstance(tile, list) and len(tile) == 2):
                continue
            key = (int(tile[0]), int(tile[1]))
            d = by_tile.setdefault(key, {"tags": set(), "attempts": 0, "first_t": None, "last_t": None,
                                        "days": set(), "zones": set(), "codes": Counter(), "lines": []})
            d["tags"].add(tag)
            d["attempts"] += 1
            t = r.get("t")
            d["first_t"] = t if d["first_t"] is None else min(d["first_t"], t)
            d["last_t"] = t if d["last_t"] is None else max(d["last_t"], t)
            d["days"].add(f"{tag}:{day_of(tag, t)}")
            if r.get("zone") is not None:
                d["zones"].add(str(r.get("zone")))
            d["codes"][str(r.get("code") or r.get("cause") or r.get("stage"))] += 1
            d["lines"].append(f"{tag}L{i}")

    print("== 账本：" + "，".join(f"{tag} {path}（{len(data[tag])} 行）" for tag, path in journals if tag in data))
    print(f"== harvest outcome {len(harvest_outcomes)} 条；harvest stage 记录 {len(stage_recs)} 条；day_end {len(day_ends)} 条")

    print("\n== ① 逐格汇总（尝试次数 / 首次-末次 t / 日 / zone / code / 账本行）")
    for key, d in sorted(by_tile.items(), key=lambda kv: -kv[1]["attempts"]):
        print(f"  {key}: 账本 {sorted(d['tags'])}；尝试 {d['attempts']} 次；t {d['first_t']}→{d['last_t']}；"
              f"日 {sorted(d['days'])[:8]}{'…' if len(d['days']) > 8 else ''}；zone {sorted(d['zones'])}；"
              f"code {dict(d['codes'])}；行 {d['lines'][:6]}{'…' if len(d['lines']) > 6 else ''}")

    print("\n== ② 逐日汇总（day_end.stages[harvest] 合计 / stage_stop_named 次数）")
    for tag, rows in data.items():
        print(f"  --- 账本 {tag}")
        ends = [(i, r) for i, r in enumerate(rows, 1) if r.get("event") == "day_end"]
        per_day_stop = Counter(day_of(tag, r.get("t")) for _, _, r in
                               ((t, i, r) for t, i, r in stage_recs if t == tag and r.get("event") == "stage_stop_named"))
        per_day_all = Counter(day_of(tag, r.get("t")) for t, _, r in stage_recs if t == tag)
        for i, r in ends:
            label = as_label(r.get("day"))
            hs = [s for s in (r.get("stages") or []) if s.get("stage") == "harvest"]
            if not hs:
                print(f"    {label} (L{i}): 没有 harvest stage 条目")
                continue
            ts = [float(s.get("t") or 0) for t, _, s in stage_recs if t == tag and day_of(tag, s.get("t")) == label]
            print(f"    {label} (L{i}): harvest 条目 {len(hs)} 个；合计 tiles={sum(int(s.get('tiles') or 0) for s in hs)} "
                  f"ok={sum(int(s.get('ok') or 0) for s in hs)} skipped={sum(int(s.get('skipped') or 0) for s in hs)} "
                  f"failed={sum(int(s.get('failed') or 0) for s in hs)} "
                  f"stopped={sorted({str(s.get('stopped')) for s in hs})} "
                  f"undone={sum(int(s.get('assigned_undone') or 0) for s in hs)}；"
                  f"stop_named {per_day_stop.get(label, 0)} 次；三类记录 {per_day_all.get(label, 0)} 条；"
                  f"t {min(ts):.2f}→{max(ts):.2f}" if ts else "")

    print("\n== ③ 判据链")
    print("  [3a] intent_verdict 里的 harvest 条目：")
    for tag, i, r in verdicts:
        for v in r.get("verdicts") or []:
            if v.get("task") == "harvest":
                print(f"    {tag}L{i} t={r.get('t')} zone={r.get('zone')!r} verdict={v.get('verdict')} "
                      f"targets={v.get('targets')} reason={v.get('reason')}")
    print("  [3b] decision 里 harvest 意图的 reason（前 6 条）：")
    n = 0
    for tag, i, r in decisions:
        for it in r.get("intents") or []:
            if it.get("task") == "harvest" and n < 6:
                print(f"    {tag}L{i} t={r.get('t')} source={r.get('source')} reason={it.get('reason')!r}")
                n += 1
    print("  [3c] review.work_reasons 提到熟的（前 8 条）：")
    n = 0
    for tag, i, r in reviews:
        wr = [w for w in (r.get("work_reasons") or []) if "熟" in str(w) or "没做完" in str(w)]
        if wr and n < 8:
            print(f"    {tag}L{i} t={r.get('t')} day={as_label(r.get('day'))} work_reasons={wr}")
            n += 1
    print("  [3d] 【缺失】账本里没有：Mod interact 回执原文（含 checkAction 返回的 acted）、")
    print("       交互后该格的观测字段（kind/crop/currentPhase/phaseDays/dayOfCurrentPhase/fullyGrown/dead/forageCrop）、")
    print("       窗口 tiles[] 的逐格快照（只有汇总计数）——所以『(60,29) 到底属于未熟/regrow/死苗/采集作物』")
    print("       无法从账本判定（缺失 ≠ 否定）；要定案必须有一次真机 observe 读该格。")

    print("\n== ④ 该格出现在哪些事件里（Q1 可查面）")
    for key in sorted(by_tile, key=lambda k: -by_tile[k]["attempts"])[:3]:
        evs = mentions.get(key, [])
        cnt = Counter(e[2] for e in evs)
        print(f"  {key}: 共 {len(evs)} 条事件提到它；事件类型 {dict(cnt)}")
        for tag, i, name, r in evs[:4]:
            body = json.dumps(r, ensure_ascii=False)
            print(f"    {tag}L{i} t={r.get('t')} {name}: {body[:300]}{'…' if len(body) > 300 else ''}")

    print("\n== ⑤ 守卫与开路（run B 的钉住现象）")
    veto_cnt = Counter()
    for tag, i, r in vetoes:
        veto_cnt[(str(r.get("task")), str(r.get("reason"))[:60])] += 1
    for (task, reason), c in veto_cnt.most_common(6):
        print(f"  intent_vetoed task={task} ×{c}: {reason}")
    print(f"  frontier_clear 事件 {len(frontiers)} 条："
          f"acted_true={sum(1 for _, _, r in frontiers if r.get('acted'))}、"
          f"tiles={sorted({tuple(r.get('tile') or []) for _, _, r in frontiers})}、"
          f"attempt_max={max([int(r.get('attempt') or 0) for _, _, r in frontiers], default=0)}")
    ripe_cnt = 0
    for _, _, r in reviews:
        ripe_cnt += sum(1 for w in (r.get("work_reasons") or []) if "熟了" in str(w))
    print(f"  review.work_reasons 里『有 N 格作物熟了』出现 {ripe_cnt} 次")

    print("\n== ⑥ 结论行")
    for tag, rows in data.items():
        ends = [r for r in rows if r.get("event") == "day_end"]
        ok = sum(int(s.get("ok") or 0) for e in ends for s in (e.get("stages") or []) if s.get("stage") == "harvest")
        bad = sum(int(s.get("failed") or 0) for e in ends for s in (e.get("stages") or []) if s.get("stage") == "harvest")
        outs = sum(1 for t, _, r in harvest_outcomes if t == tag)
        print(f"  账本 {tag}：harvest 成功 {ok} 步 / 失败 {bad} 步；harvest outcome {outs} 条")

    if as_json:
        print("\n" + json.dumps({f"{k[0]},{k[1]}": {"attempts": v["attempts"], "days": sorted(v["days"]),
                                                     "codes": dict(v["codes"])} for k, v in by_tile.items()},
                                ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
