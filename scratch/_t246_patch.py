"""task-246 一次性补丁：analyzer 收录 `event_wait` + `event_blocked` 新字段 + `ui.eventId`。

原则：每处替换都断言"原文恰好出现一次"，任何一处不匹配就整体不落盘（不做半成品）。
跑法：PYTHONUTF8=1 python scratch\\_t246_patch.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "analyze-longrun.py"

NEW_FIELD_PROBES = '''    # task-246（dev task-245 `0a13973`）：`eventUp` 且无对话盒 ⇒ **有界等待 4×15s** 的逐轮留痕，
    # 以及事件归因 `eventId` 的**三态**（有值 / null=读不到 / 缺字段=旧 Mod）。都属 info，不进 rc。
    ("event:event_wait", "event_wait",
     "事件进行中的有界等待（tries/limit/eventId/eventUp/hasDialogue/worldSeq/waitSeconds）："
     "**不是失败、不是豁免**；有 event_blocked 却一条 event_wait 都没有 ⇒ 没走等待路径（可判红）"),
    ("event:event_wait.eventId", "event_wait_event_id",
     "等待时读到的事件 id（三态：有值 / null=读不到 / 缺字段=旧 Mod）；缺失 ⇒【无法判定】不许猜"),
    ("event:event_blocked.eventId", "event_blocked_event_id",
     "事件阻断时的事件 id（三态同上；缺失 ⇒【无法判定】）"),
    ("event:event_blocked.eventWaitTries", "event_blocked_wait_tries",
     "event_blocked 前等了几轮（缺字段=旧 Mod ⇒【无法判定】；有键且 0 且整本无 event_wait ⇒ 没走等待路径 ⇒ 红）"),
    ("event:event_blocked.eventWaitSeconds", "event_blocked_wait_seconds",
     "event_blocked 前等了多久（秒；brain = EVENT_WAIT_TRIES×EVENT_WAIT_SECONDS，task-245）"),
    ("ui.eventId", "ui.eventId",
     "观测 `ui` 块里的事件 id（task-245 Mod 新增，三态：有值 / null=读不到 / 缺字段=旧 Mod）"),
'''

PATCHES: list[tuple[str, str, str]] = []


def patch(tag: str, old: str, new: str) -> None:
    PATCHES.append((tag, old, new))


# ---------------------------------------------------------------- 1) FIELD_PROBES
patch(
    "FIELD_PROBES_tail",
    "     \"**没有证据的 no_target 一律判红**）\"),\n]",
    "     \"**没有证据的 no_target 一律判红**）\"),\n" + NEW_FIELD_PROBES + "]",
)

# ---------------------------------------------------------------- 2) resolver：支持 ui.<key>
patch(
    "resolver_spec",
    "            _spec = label.split(\":\", 1)[1]\n        if _spec is not None:",
    "            _spec = label.split(\":\", 1)[1]\n"
    "        elif probe.startswith(\"ui.\"):\n"
    "            # task-246：`ui.eventId` 这类观测块字段（旧账本没有 ui 块 ⇒ 缺失 = 旧 Mod）\n"
    "            _spec = probe\n"
    "        if _spec is not None:",
)
patch(
    "resolver_ui_branch",
    "            elif \".\" in _spec:\n                _evname, _field = _spec.split(\".\", 1)",
    "            elif _spec.startswith(\"ui.\"):\n"
    "                # task-246：`ui` 是每行观测里的嵌套 dict，要真去找键（不能拿 \"ui.eventId\" 当整串文本找）\n"
    "                _uk = _spec.split(\".\", 1)[1]\n"
    "                absent = not any(isinstance(ev.get(\"ui\"), dict) and _uk in ev[\"ui\"]\n"
    "                                 for _, ev in rows)\n"
    "            elif \".\" in _spec:\n                _evname, _field = _spec.split(\".\", 1)",
)

# ---------------------------------------------------------------- 3) EVENT_BUCKETS
patch(
    "EVENT_BUCKETS_tail",
    "    \"gaps_write_failed\": \"gaps_write_failures\",\n}",
    "    \"gaps_write_failed\": \"gaps_write_failures\",\n"
    "    # task-246（dev task-245）：`eventUp` 且无对话盒 ⇒ **有界等待**（info / 环境类，不是失败、不进 rc）。\n"
    "    \"event_wait\": \"event_waits\",\n}",
)

# ---------------------------------------------------------------- 4) NEW_EVENT_BUCKETS
patch(
    "NEW_EVENT_BUCKETS_tail",
    "    \"gaps_load_failures\", \"gaps_write_failures\",\n)",
    "    \"gaps_load_failures\", \"gaps_write_failures\",\n"
    "    # task-246（dev task-245）：事件进行中的有界等待（4×15s；info，不进 rc）\n"
    "    \"event_waits\",\n)",
)

# ---------------------------------------------------------------- 5) _event_gate 聚合
EVENT_GATE = '''    # 【task-246】事件闸门（dev task-245 `0a13973`）：`eventUp` 且无对话盒 ⇒ 有界等待 4×15s。
    # 口径：`event_wait` = 等待的逐轮留痕（**info**：不是失败、不是豁免）；`event_blocked` = 等满仍挂住
    # 或推不动 ⇒ 诚实收尾（当天不判 VERIFIED）。唯一可判红 = 「event_blocked 里 `eventWaitTries` **有键
    # 且 0**，同时整本没有任何 `event_wait`」⇒ 没走等待路径（= 0.7.42 冬 7 白烧 4.92 分钟的行为）。
    # `eventWaitTries` **整键缺失**是 task-245 之前的旧 Mod ⇒ 只能【无法判定】（缺失 ≠ 通过，也不许当红）。
    # `eventId` 三态：有值 / null=读不到 / 缺字段=旧 Mod ⇒ 缺字段只能【无法判定】。
    def _event_id_tri(event_name):
        _vals, _states = [], {"value": 0, "null": 0, "missing": 0}
        for _ln, _ev in rows:
            if _ev.get("event") != event_name:
                continue
            if "eventId" not in _ev:
                _states["missing"] += 1
                continue
            _v = _ev.get("eventId")
            if _v is None or str(_v) == "":
                _states["null"] += 1
            else:
                _states["value"] += 1
                if str(_v) not in _vals:
                    _vals.append(str(_v))
        return _vals, _states

    _ew_lines = [ln for ln, ev in rows if ev.get("event") == "event_wait"]
    _eb_pairs = [(ln, ev) for ln, ev in rows if ev.get("event") == "event_blocked"]
    _eb_lines = [ln for ln, _ev in _eb_pairs]
    _ew_ids, _ew_id_states = _event_id_tri("event_wait")
    _eb_ids, _eb_id_states = _event_id_tri("event_blocked")
    _ew_tries = sorted({as_int(ev.get("tries"), 0)
                        for _ln, ev in rows if ev.get("event") == "event_wait"})
    _ew_seq = {ev.get("worldSeq") for _ln, ev in rows if ev.get("event") == "event_wait"}
    _eb_tries = [as_int(ev.get("eventWaitTries"), -1) for _ln, ev in _eb_pairs]
    _eb_secs = []
    for _ln, ev in _eb_pairs:
        try:
            _eb_secs.append(float(ev.get("eventWaitSeconds") or 0))
        except (TypeError, ValueError):
            pass
    _no_wait_path_lines = [ln for ln, ev in _eb_pairs
                           if as_int(ev.get("eventWaitTries"), -1) == 0] if not _ew_lines else []
    _id_known = _ew_ids + _eb_ids
    _event_gate = {
        "wait_events": len(_ew_lines),
        "wait_lines": _ew_lines,
        "wait_tries": _ew_tries,
        "wait_seconds": as_int(((_ew_tries or [0])[-1]), 0),
        "wait_worldseq_moved": len({s for s in _ew_seq if s is not None}) > 1,
        "wait_ids": _ew_ids,
        "wait_id_states": _ew_id_states,
        "blocked_events": len(_eb_lines),
        "blocked_lines": _eb_lines,
        "blocked_tries": sorted({t for t in _eb_tries if t >= 0}),
        "blocked_seconds_max": max(_eb_secs) if _eb_secs else 0.0,
        "blocked_ids": _eb_ids,
        "blocked_id_states": _eb_id_states,
        "no_wait_path_lines": _no_wait_path_lines,
        # 旧 Mod（task-245 之前）才有事件却缺 eventId：判不了"是哪个事件"
        "event_id_undecidable": bool((_ew_lines or _eb_lines)
                                     and (_ew_id_states["missing"] or _eb_id_states["missing"])),
        "id_text": "、".join(_id_known[:3]) if _id_known else "无法归因",
        "has_events": bool(_ew_lines or _eb_lines),
    }
'''
patch(
    "event_gate_block",
    "    # 0 步 VERIFIED 的弱日（已有 task-88 口径）；这里只做信息项。\n",
    EVENT_GATE + "    # 0 步 VERIFIED 的弱日（已有 task-88 口径）；这里只做信息项。\n",
)

# ---------------------------------------------------------------- 6) report 挂载
patch(
    "report_keys",
    "    report[\"gaps\"] = _gaps_report\n",
    "    report[\"gaps\"] = _gaps_report\n"
    "    # 【task-246】事件闸门（eventUp 的有界等待 / 事件归因）—— info 为主，唯一红见 cat_event\n"
    "    report[\"event_gate\"] = _event_gate\n",
)

# ---------------------------------------------------------------- 7) cat_event（第 8 类）
CAT_EVENT = '''def cat_event(rows, top):
    """【task-246】第 8 类：事件闸门（`eventUp` 的有界等待 / 事件归因）。

    唯一可判红：`event_blocked` 里 `eventWaitTries` **有键且 0**，同时整本没有任何 `event_wait`
    ⇒ 没走 task-245 的「有界等待」路径（等于又回到 0.7.42 冬 7 的"立刻硬停、白烧一整天"）。
    旧 Mod（整键缺失）只走【无法判定】，绝不判红（缺失 ≠ 通过，也不许当失败）。
    """
    out = []
    has_wait = any(ev.get("event") == "event_wait" for _, ev in rows)
    if has_wait:
        return out
    for ln, ev in rows:
        if ev.get("event") != "event_blocked":
            continue
        tries = as_int(ev.get("eventWaitTries"), -1)
        if tries != 0:
            continue
        _id = ev.get("eventId")
        out.append(finding(
            ln, "manual",
            "事件阻断没走「有界等待」路径：`eventWaitTries=0` 且整本 0 条 `event_wait`"
            f"（eventId={_id if _id else '未知（无法归因）'}）⇒ task-245 之前的旧行为会立刻硬停，"
            "把一整天白烧（0.7.42 冬 7 事故原样复现）",
            hint="task-245 口径：`eventUp` 且无对话盒 ⇒ 先 `_wait_event_up`（4×15s，不 dismiss/不 sleep/"
                 "不 load_save）再诚实收尾；这条是**问题**不是 info",
            subject="manual:event_blocked_without_wait"))
    return out[:top] if top else out


'''
patch(
    "cat_event_def",
    "\n\ndef build_advice(",
    "\n\n" + CAT_EVENT + "def build_advice(",
)

# ---------------------------------------------------------------- 8) categories 接线
patch(
    "categories",
    "        \"intent\": cat_intent(rows, sessions, _gaps_merged, args.top),\n",
    "        \"intent\": cat_intent(rows, sessions, _gaps_merged, args.top),\n"
    "        \"event\": cat_event(rows, args.top),\n",
)
patch(
    "categories_total",
    "        \"intent\": len(cat_intent(rows, sessions, _gaps_merged, 0)),\n",
    "        \"intent\": len(cat_intent(rows, sessions, _gaps_merged, 0)),\n"
    "        \"event\": len(cat_event(rows, 0)),\n",
)
patch(
    "red_pool",
    "                  cat_intent(rows, sessions, _gaps_merged, 0)):",
    "                  cat_intent(rows, sessions, _gaps_merged, 0),\n"
    "                  cat_event(rows, 0)):",
)

# ---------------------------------------------------------------- 9) advice
ADVICE = '''    # 0s-9（task-246，dev task-245）：事件闸门 —— event_wait 是 info；唯一可判红 = 没走等待路径
    eg = report.get("event_gate") or {}
    if eg.get("no_wait_path_lines"):
        advice.append({
            "text": f"事件阻断没走有界等待 ×{len(eg['no_wait_path_lines'])}"
                    "（task-245：eventUp 且无对话盒 ⇒ 先等 4×15s 再诚实收尾；直接硬停会白烧一整天）",
            "lines": (eg.get("no_wait_path_lines") or [])[:10],
        })
    if eg.get("event_id_undecidable"):
        advice.append({
            "text": "事件记录缺 `eventId`（task-245 之前的旧 Mod）：挂了也答不出「是哪个事件」"
                    "⇒ 升级 Mod 后重跑才有归因",
            "lines": ((eg.get("wait_lines") or [])[:5] + (eg.get("blocked_lines") or [])[:5]),
        })
'''
patch(
    "advice",
    "    # 0c) 环境挡路 / 没拿到结论（task-22 记账）\n",
    ADVICE + "    # 0c) 环境挡路 / 没拿到结论（task-22 记账）\n",
)

# ---------------------------------------------------------------- 10) render 头部行
RENDER = '''    # task-246：事件闸门一行（event_wait 有界等待 / event_blocked 收尾 / eventId 三态）
    eg = report.get("event_gate") or {}
    if eg.get("wait_events") or eg.get("blocked_events"):
        _eg_txt = (f"事件等待: {eg.get('wait_events', 0)} 轮 / 阻断 {eg.get('blocked_events', 0)} 次"
                   f"（eventId={eg.get('id_text') or '无法归因'}")
        if eg.get("wait_events") and not eg.get("blocked_events"):
            _eg_txt += "；事件已自行结束（正常）"
        if eg.get("no_wait_path_lines"):
            _eg_txt += f"；⚠ 阻断没走等待路径（行 {(eg.get('no_wait_path_lines') or [])[:8]}）"
        if eg.get("event_id_undecidable"):
            _eg_txt += "；eventId 缺失 ⇒【无法判定】"
        add(_eg_txt + "）")
'''
patch(
    "render",
    "    # task-32：两种新事件形态的计数（信息项）；task-38：跨日证据覆盖度\n",
    RENDER + "    # task-32：两种新事件形态的计数（信息项）；task-38：跨日证据覆盖度\n",
)

# ---------------------------------------------------------------- 11) build_undecidable
UNDEC = '''    # task-246：事件闸门（旧账本没有 event_wait / event_wait_tries ⇒ 只能【无法判定】）
    _eg = report.get("event_gate") or {}
    if _eg.get("event_id_undecidable"):
        out.append("本账本有 event_wait/event_blocked，但事件记录里没有 `eventId` 键（task-245 之前的旧 Mod）："
                   "无法判定「是哪个事件挂住了长跑」（缺失 ≠ 无法归因 ⇒ 不许猜）")
    if not _eg.get("has_events"):
        out.append("本账本没有任何 event_wait / event_blocked（0.7.42 之前）："
                   "无法判定「事件进行中是否走了有界等待」—— 缺失 ≠ 没发生")
'''
patch(
    "undecidable",
    "    return out\n\n\n# ---------------------------------------------------------------- 报告渲染",
    UNDEC + "    return out\n\n\n# ---------------------------------------------------------------- 报告渲染",
)

# ---------------------------------------------------------------- 12) MAPPING_TEXT
MAPPING = '''    ("event:event_wait / event_blocked.eventId/eventWaitTries/eventWaitSeconds（task-245/task-246）",
     "5 环境挡路（信息项）：`event_wait` = 事件进行中的**有界等待**（4×15s；不 dismiss / 不 sleep / "
     "不 load_save），**不是失败、不是豁免**；`event_blocked` = 等满仍挂住或推不动 ⇒ 诚实收尾"
     "（当天不判 VERIFIED）。唯一可证伪红 = 「`event_blocked` 的 `eventWaitTries` **有键且 0**，"
     "且整本没有任何 `event_wait`」⇒ 没走等待路径（0.7.42 冬 7 白烧 4.92 分钟的行为）；"
     "`eventWaitTries` 整键缺失 = task-245 之前的旧 Mod ⇒【无法判定】只记信息，绝不判红；"
     "`eventId` 三态（有值 / null=读不到 / 缺字段=旧 Mod），缺失 ⇒【无法判定】不许猜；"
     "`verify-run3.py` 对两事件只作 info，本工具的这条红是补充、不与其冲突"),
'''
patch(
    "mapping",
    "\n    (\"idle\",",
    "\n" + MAPPING + "\n    (\"idle\",",
)

# ---------------------------------------------------------------- 13) 模块 docstring
patch(
    "docstring",
    "能力缺口（`deferred_capability`/`tool_level`）必须落进 `<journal>-gaps.json` 并被追修复卡。\n",
    "能力缺口（`deferred_capability`/`tool_level`）必须落进 `<journal>-gaps.json` 并被追修复卡。\n"
    "`eventUp` 且无对话盒 ⇒ 有界等待 `event_wait`（info）；`event_blocked` 没走等待路径 ⇒ 红（task-246）。\n",
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    text = TARGET.read_text(encoding="utf-8")
    for tag, old, new in PATCHES:
        count = text.count(old)
        if count != 1:
            print(f"[FAIL] {tag}: 原文命中 {count} 次（应为 1）")
            return 1
        text = text.replace(old, new, 1)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"[OK] 应用 {len(PATCHES)} 处替换 -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
