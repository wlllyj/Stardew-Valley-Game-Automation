# -*- coding: utf-8 -*-
"""task-17: 0.7.44 冒烟账本 pending 归属分析（只读账本，不改判据）。"""
import json
import sys
from collections import Counter, OrderedDict

PATH = "logs/longrun-smoke-0744.jsonl"
if len(sys.argv) > 1:
    PATH = sys.argv[1]

rows = []
with open(PATH, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append((i, json.loads(line)))
        except Exception:
            pass


def tiles_of(ev, *keys):
    out = []
    for k in keys:
        v = ev.get(k)
        if isinstance(v, list):
            for t in v:
                if isinstance(t, (list, tuple)) and len(t) == 2:
                    out.append((int(t[0]), int(t[1])))
    return out


# 按 day_start 切天
days = []
cur = None
for lineno, ev in rows:
    name = ev.get("event") or ev.get("event_name")
    kind = ev.get("kind")
    if name is None and "day_start" in ev:
        name = "day_start"
    if name == "day_start":
        cur = {"start_line": lineno, "events": [], "day_end": None}
        days.append(cur)
    if cur is None:
        continue
    cur["events"].append((lineno, ev))
    if name == "day_end":
        cur["day_end"] = (lineno, ev)
        cur = None

out = OrderedDict()
print("file:", PATH, "lines:", len(rows), "days:", len(days))
for d in days:
    de_lineno, de = d["day_end"]
    label = "%s-%s d%d" % (de.get("season"), de.get("day"), len(days))
    g = OrderedDict()
    ev_names = Counter()
    ex = []  # plot_exhausted
    burst = []  # no_progress_burst
    walk = []  # resume_walk
    blocked = []  # blocked events
    plots = []
    plot_walks = []
    outcomes = []
    unres_ev = []
    enc_ev = []
    clears = []
    for lineno, ev in d["events"]:
        name = ev.get("event") or ev.get("kind") or ""
        ev_names[name] += 1
        if name == "plot_exhausted":
            ex.append((lineno, ev))
        elif name == "no_progress_burst":
            burst.append((lineno, ev))
        elif name == "resume_walk":
            walk.append((lineno, ev))
        elif name == "blocked":
            blocked.append((lineno, ev))
        elif name == "plot":
            plots.append((lineno, ev))
        elif name == "plot_walk":
            plot_walks.append((lineno, ev))
        elif name == "outcome":
            outcomes.append((lineno, ev))
        elif name == "unreachable":
            unres_ev.append((lineno, ev))
        elif name == "encircled":
            enc_ev.append((lineno, ev))
        elif name == "clear_neighbor":
            clears.append((lineno, ev))

    g["label"] = label
    g["start_line"] = d["start_line"]
    g["day_end_line"] = de_lineno
    g["event_names"] = dict(ev_names)
    # 守卫 pending 数字
    g["plot_exhausted"] = [
        OrderedDict(
            line=ln,
            source=ev.get("source"),
            recovered=ev.get("recovered"),
            switches=ev.get("switches"),
            pending=ev.get("pending"),
            stalled_tiles=ev.get("stalled_tiles"),
            stalled_total=ev.get("stalled_total"),
            from_area=ev.get("from_area"),
            to_area=ev.get("to_area"),
            to_anchor=ev.get("to_anchor"),
            note=(ev.get("note") or "")[:160],
        )
        for ln, ev in ex
    ]
    g["no_progress_burst"] = [
        OrderedDict(
            line=ln,
            source=ev.get("source"),
            count=ev.get("count"),
            exhausted=ev.get("exhausted"),
            tiles=ev.get("tiles"),
            stalled_tiles=ev.get("stalled_tiles"),
            switches=ev.get("switches"),
            from_area=ev.get("from_area"),
            from_anchor=ev.get("from_anchor"),
            samples=ev.get("samples"),
            note=(ev.get("note") or "")[:160],
        )
        for ln, ev in burst
    ]
    g["resume_walk"] = [
        OrderedDict(
            line=ln,
            where=ev.get("where"),
            walked=ev.get("walked"),
            switched=ev.get("switched"),
            to_area=ev.get("to_area"),
            to_anchor=ev.get("to_anchor"),
        )
        for ln, ev in walk
    ]
    g["blocked_events"] = [
        OrderedDict(
            line=ln,
            tile=ev.get("tile"),
            action=ev.get("action"),
            alloc_no_progress=ev.get("alloc_no_progress"),
            limit=ev.get("limit"),
            stage=ev.get("stage"),
        )
        for ln, ev in blocked
    ]
    # stage 记录（日级拆分）
    stages = de.get("stages") or []
    stage_rows = []
    un_exec = un_block = un_left = 0
    split_missing = 0
    mismatch = 0
    cap_tiles = []
    left_blocked_coords = []
    unreachable_coords = []
    enclosed_coords = []
    already_coords = []
    cleared_coords = []
    already_sum = 0
    ok_sum = 0
    failed_sum = 0
    occurred = []
    for idx, st in enumerate(stages):
        le = st.get("leftover_executable")
        lb = st.get("leftover_blocked")
        lo = st.get("leftover")
        if le is None or lb is None:
            split_missing += 1
            exe, blk = None, None
        else:
            exe, blk = int(le), int(lb)
            un_exec += exe
            un_block += blk
            un_left += int(lo or 0)
            if exe + blk != int(lo or 0):
                mismatch += 1
        cap_tiles.extend(tiles_of(st, "alloc_capped_tiles"))
        left_blocked_coords.extend(tiles_of(st, "leftover_blocked_tiles"))
        already_coords.extend(tiles_of(st, "already_tiles"))
        already_sum += int(st.get("already") or 0)
        ok_sum += int(st.get("ok") or 0)
        failed_sum += int(st.get("failed_tiles") or 0) if isinstance(st.get("failed_tiles"), int) else int(st.get("failed") or 0)
        stage_rows.append(
            OrderedDict(
                idx=idx,
                stage=st.get("stage"),
                tiles=st.get("tiles"),
                ok=st.get("ok"),
                already=st.get("already"),
                assigned=st.get("assigned"),
                assigned_undone=st.get("assigned_undone"),
                leftover=lo,
                exec=le,
                blocked=lb,
                stopped=st.get("stopped"),
                alloc_capped=st.get("alloc_capped_tiles"),
            )
        )
    for ln, ev in unres_ev:
        unreachable_coords.extend(tiles_of(ev, "tiles") or [tuple(ev.get("tile") or [])])
    for ln, ev in enc_ev:
        c = ev.get("tiles") or [ev.get("tile")]
        enclosed_coords.extend([tuple(t) for t in c if t])
    for ln, ev in clears:
        cleared_coords.extend(tiles_of(ev, "targets") + tiles_of(ev, "neighbours") + tiles_of(ev, "tiles"))
    de_unreach = de.get("unreachable_tiles") or []
    g["guard"] = OrderedDict(
        pending_values=Counter(ev.get("pending") for _, ev in ex if ev.get("pending") is not None),
        burst_pending=Counter(
            ev.get("stalled_tiles") for _, ev in burst if ev.get("stalled_tiles") is not None
        ),
    )
    g["stages"] = OrderedDict(
        count=len(stages),
        split_missing=split_missing,
        mismatch=mismatch,
        exec_sum=un_exec,
        blocked_sum=un_block,
        leftover_sum=un_left,
        max_exec=max([r["exec"] for r in stage_rows if r["exec"] is not None], default=None),
        max_blocked=max([r["blocked"] for r in stage_rows if r["blocked"] is not None], default=None),
        max_leftover=max([r["leftover"] for r in stage_rows if r["leftover"] is not None], default=None),
        ok_sum=ok_sum,
        already_sum=already_sum,
        failed_sum=failed_sum,
        cap_stages=sum(1 for r in stage_rows if r["alloc_capped"]),
        cap_tiles=sorted(set(cap_tiles)),
        blocked_tiles=sorted(set(left_blocked_coords)),
        already_tiles=sorted(set(already_coords)),
    )
    g["day_end"] = OrderedDict(
        ended_by=de.get("ended_by"),
        ended_reason=de.get("ended_reason"),
        ok_steps=de.get("ok_steps"),
        unreachable=de.get("unreachable"),
        unreachable_bound=de.get("unreachable_bound"),
        unreachable_tiles=sorted(set(tuple(t) for t in de_unreach)),
        encircled=de.get("encircled"),
        encircled_tiles=sorted(set(tuple(t) for t in (de.get("encircled_tiles") or []))),
        refused=de.get("refused"),
        plot_pending=de.get("plot_pending"),
        plot_pending_by_kind=de.get("plot_pending_by_kind"),
        plot_pending_executable=de.get("plot_pending_executable"),
        plot_pending_blocked=de.get("plot_pending_blocked"),
        slept_ok=de.get("slept_ok"),
        checks=de.get("checks"),
        day_justified=de.get("day_justified"),
        stamina_budget=de.get("stamina_budget"),
        plots=[{k: p.get(k) for k in ("zone", "anchor", "tiles", "tilesTruncated")} for p in (de.get("plots") or [])],
    )
    g["events"] = OrderedDict(
        unreachable=[(ln, ev.get("tile") or ev.get("tiles")) for ln, ev in unres_ev],
        encircled=[(ln, ev.get("tile") or ev.get("tiles")) for ln, ev in enc_ev],
        clear_neighbor=[
            (ln, ev.get("targets"), ev.get("neighbours"), ev.get("opened")) for ln, ev in clears
        ],
        plot=[(ln, ev.get("zone"), ev.get("anchor"), (ev.get("note") or "")[:80]) for ln, ev in plots],
        plot_walk=[(ln, ev) for ln, ev in plot_walks],
        outcome=[(ln, ev.get("kind"), ev.get("terminal"), ev.get("reason")) for ln, ev in outcomes],
    )
    g["coord_union"] = OrderedDict(
        day_end_unreachable=len(set(tuple(t) for t in de_unreach)),
        day_end_encircled=len(set(tuple(t) for t in (de.get("encircled_tiles") or []))),
        stage_blocked=len(set(left_blocked_coords)),
        events_unreachable=len(set(unreachable_coords)),
        events_encircled=len(set(enclosed_coords)),
        events_clear=len(set(cleared_coords)),
        stage_already=len(set(already_coords)),
        all=None,
    )
    out[label] = g

with open("scratch/_t17_attr.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)

for label, g in out.items():
    print("=" * 20, label, "lines", g["start_line"], "-", g["day_end_line"])
    print("guard:", g["guard"])
    print("stages:", json.dumps(g["stages"], ensure_ascii=False))
    print("day_end:", json.dumps({k: g["day_end"][k] for k in ("ended_by", "ok_steps", "unreachable", "unreachable_bound", "encircled", "plot_pending", "plot_pending_executable", "plot_pending_blocked", "slept_ok", "day_justified")}, ensure_ascii=False))
    print("coord_union:", json.dumps(g["coord_union"], ensure_ascii=False))
    print("ex:", json.dumps(g["plot_exhausted"], ensure_ascii=False))
    print("burst:", json.dumps(g["no_progress_burst"], ensure_ascii=False))
    print("walk:", json.dumps(g["resume_walk"], ensure_ascii=False))
    print("blocked:", json.dumps(g["blocked_events"], ensure_ascii=False))
    print("unres:", json.dumps(g["events"]["unreachable"], ensure_ascii=False))
    print("enc:", json.dumps(g["events"]["encircled"], ensure_ascii=False))
    print("clears:", json.dumps(g["events"]["clear_neighbor"], ensure_ascii=False))
    print("plots:", json.dumps(g["day_end"]["plots"], ensure_ascii=False))
    print("stamina:", json.dumps(g["day_end"]["stamina_budget"], ensure_ascii=False))

