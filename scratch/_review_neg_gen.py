#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""deputy-lead 的 verify-run3.py 负例生成器（只读工具、只往 scratch/ 写账本）。

目的：证明 tools\\verify-run3.py 在两类"账本自己说自己绿"的情形下会不会漏判。
  A) day_end 里**没有** verified / checks 字段（字段缺失）—— 工具是否会当成"通过"。
  B) day_end.checks 自称全绿（no_unmet_stages=true, no_hard_failures=true）
     但 day_end.stages 里明明有 leftover>0 与 failed>0 —— 工具是否只信自述、不做交叉核对。

用法：python scratch\\_review_neg_gen.py   （生成 scratch\\review-neg-*.jsonl）
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def day_block(d: int, *, mode: str) -> list[dict]:
    nxt = d + 1
    rows: list[dict] = []
    rows.append({
        "t": float(d * 600 + 1), "event": "day_start", "day": ["1", "spring", d],
        "final": {"day": ["1", "spring", d], "stamina": 270.0, "crops": 32,
                  "unwatered_crops": 32, "money": 200},
    })
    rows.append({
        "t": float(d * 600 + 5), "event": "decision", "day": ["1", "spring", d],
        "boundary": "new_day", "source": "llm", "llm": True,
        "intents": [{"task": "water_area", "area_hint": "anchor:field_ne"}],
    })
    rows.append({
        "t": float(d * 600 + 500), "event": "sleep", "day": ["1", "spring", d], "ok": True,
        "before": {"day": ["1", "spring", d], "timeOfDay": 2200},
        "after": {"day": ["1", "spring", nxt], "timeOfDay": 600},
    })
    end = {
        "t": float(d * 600 + 520), "event": "day_end", "day": ["1", "spring", d],
        "ended_by": "sleep", "ended_reason": "night:到点了",
        "final": {"day": ["1", "spring", nxt], "timeOfDay": 600, "stamina": 270.0,
                  "crops": 33, "unwatered_crops": 0, "money": 200},
        "day_text": "spring %d：phase water_area..." % d,
        "outcomes": [], "notes": [],
    }
    if mode == "no_verified":
        # 干净阶段 + 干净计数，但**整块**省略 verified / checks（模拟字段漏写）
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0}]
    elif mode == "self_report_green":
        # 自述全绿，但阶段记录里 leftover>0 且 failed>0，day_end.failed_steps 却写 0
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True}
        end["ok_steps"] = 10
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [{"stage": "plant_area", "tiles": 15, "ok": 10, "skipped": 0,
                          "failed": 3, "stopped": "no_seed", "leftover": 5}]
    elif mode == "missing_self_report":
        # 对照组：自述字段(failed_steps / no_unmet_stages)全部缺省，但阶段记录如实写着
        # leftover=5 / failed=3 —— 用来验证工具的"回退自算"路径确实是有效的。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True}
        end["ok_steps"] = 10
        end["skipped_steps"] = 0
        end["stages"] = [{"stage": "plant_area", "tiles": 15, "ok": 10, "skipped": 0,
                          "failed": 3, "stopped": "no_seed", "leftover": 5}]
    elif mode == "self_report_unmet_but_verified":
        # neg-D：**自述与阶段记录一致地"未完成"**，但 day_end 仍自称 verified=true。
        # 用来检查"交叉核对一致"是否被误当成"通过"（no_unmet_stages=false 本身就该是问题）。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": False}
        end["ok_steps"] = 10
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [{"stage": "plant_area", "tiles": 15, "ok": 10, "skipped": 0,
                          "failed": 0, "stopped": "no_seed", "leftover": 5}]
    elif mode == "watered_no_evidence":
        # neg-E：自称睡过去了、crops_watered=true、其余全绿，但**整块没有 watered_outdoor**
        # （Lead 2026-10-13 新口径：浇水证据只能来自 checks.watered_outdoor；缺失 ≠ 通过）。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True}
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0}]
    elif mode == "watered_outdoor_false":
        # neg-F：字段在、但明说"睡前还有没浇的作物"，而 crops_watered 自述 true（窗口口径白过）。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True,
                         "watered_outdoor": False}
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0}]
    elif mode == "env_info_item":
        # neg-G：**合法绿日** + task-22/task-15④ 新增的 env 信息项（stage 级 env_block_count /
        # day 级 env_fail 事件）。断言：信息项**不得**改变 exit code（仍 VERIFIED）。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True, "watered_outdoor": True}
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block"] = 1
        end["env_block_count"] = 1
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0,
                          "env_block": 1, "env_block_count": 1, "inconclusive_count": 0}]
        # ⚠ t 必须单调（verify-run3.py 的"账本内部自洽"检查）：插在 decision(600d+5) 之后、
        # sleep(600d+500) 之前；插在 sleep 之后会造出时间戳回退的假问题（deputy-lead 2026-10-13 修正）。
        rows.insert(2, {"t": float(d * 600 + 100), "event": "env_fail", "day": ["1", "spring", d],
                        "stage": "water_area", "tiles": [[60, 10]],
                        "statuses": ["world_fading"], "count": 1,
                        "note": "环境挡路，已 clear_modals 后重跑并做成"})
    elif mode == "env_info_cannot_mask":
        # neg-H：env 信息项 + **真实未完成**（自述与阶段记录一致地 leftover>0）。
        # 断言：信息项不得把真问题盖掉（exit 必须仍为 1）。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": False, "watered_outdoor": True}
        end["ok_steps"] = 10
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block"] = 1
        end["env_block_count"] = 1
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "plant_area", "tiles": 15, "ok": 10, "skipped": 0,
                          "failed": 0, "stopped": "no_seed", "leftover": 5,
                          "env_block": 1, "env_block_count": 1, "inconclusive_count": 0}]
        # ⚠ t 必须单调（verify-run3.py 的"账本内部自洽"检查）：插在 decision(600d+5) 之后、
        # sleep(600d+500) 之前；插在 sleep 之后会造出时间戳回退的假问题（deputy-lead 2026-10-13 修正）。
        rows.insert(2, {"t": float(d * 600 + 100), "event": "env_fail", "day": ["1", "spring", d],
                        "stage": "plant_area", "tiles": [[60, 10]],
                        "statuses": ["ui_modal"], "count": 1})
    elif mode == "env_explained":
        # neg-I（Lead bfb8649 的差额容错正向分支）：stage 求和 failed=3，而 day 级 failed_steps=0，
        # 差额 3 **完全**被 env_block_count=3 解释 ⇒ 期望 exit 0，并把差额记成信息项。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True, "watered_outdoor": True}
        end["ok_steps"] = 35
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block"] = 3
        end["env_block_count"] = 3
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 35, "ok": 35, "skipped": 0,
                          "failed": 3, "stopped": "", "leftover": 0,
                          "env_block": 3, "env_block_count": 3, "inconclusive_count": 0}]
        # ⚠ t 必须单调（verify-run3.py 的"账本内部自洽"检查）：插在 decision(600d+5) 之后、
        # sleep(600d+500) 之前；插在 sleep 之后会造出时间戳回退的假问题（deputy-lead 2026-10-13 修正）。
        rows.insert(2, {"t": float(d * 600 + 100), "event": "env_fail", "day": ["1", "spring", d],
                        "stage": "water_area", "tiles": [[60, 10], [60, 11], [60, 12]],
                        "statuses": ["world_fading"], "count": 3,
                        "note": "环境挡路，同一天重跑并做成 ⇒ 不计当天硬失败"})
    elif mode == "env_understated":
        # neg-J：差额 3 只被 env_block_count=1 解释掉 1 ⇒ 剩 2 无人认领 ⇒ 期望 exit 1「账目不可信」。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_hard_failures": True, "crops_watered": True,
                         "day_justified": True, "no_unmet_stages": True, "watered_outdoor": True}
        end["ok_steps"] = 35
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block"] = 1
        end["env_block_count"] = 1
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 35, "ok": 35, "skipped": 0,
                          "failed": 3, "stopped": "", "leftover": 0,
                          "env_block": 1, "env_block_count": 1, "inconclusive_count": 0}]
        # ⚠ t 必须单调（verify-run3.py 的"账本内部自洽"检查）：插在 decision(600d+5) 之后、
        # sleep(600d+500) 之前；插在 sleep 之后会造出时间戳回退的假问题（deputy-lead 2026-10-13 修正）。
        rows.insert(2, {"t": float(d * 600 + 100), "event": "env_fail", "day": ["1", "spring", d],
                        "stage": "water_area", "tiles": [[60, 10]],
                        "statuses": ["world_fading"], "count": 1})
    elif mode == "forged_consistent":
        # neg-K（Lead m00877 第 4 条）：**最大化自洽的伪造账本** —— 一切字段都写成"完美的一天"，
        # 且 failed_steps 与 stage 求和严格相等、leftover 全 0、env/inconclusive 计数为 0。
        # 它**没有**任何外部锚点（没有存档 mtime、没有 SMAPI 时间戳、没有 worldSeq）。
        # 预期：tools\verify-run3.py 报 exit 0 / VERIFIED ⇒ 证明它是**账本检查器，不是世界校验器**。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 40
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block_count"] = 0
        end["inconclusive_count"] = 0
        end["stages"] = [
            {"stage": "clear_area", "tiles": [[60, 10], [60, 11]], "ok": 2, "skipped": 0,
             "failed": 0, "stopped": "", "leftover": 0, "env_block_count": 0, "inconclusive_count": 0},
            {"stage": "till_area", "tiles": [[60, 10], [60, 11], [61, 10], [61, 11],
                                             [62, 10], [62, 11]], "ok": 6, "skipped": 0,
             "failed": 0, "stopped": "", "leftover": 0, "env_block_count": 0, "inconclusive_count": 0},
            {"stage": "plant_area", "tiles": [[60, 10], [60, 11], [61, 10], [61, 11],
                                              [62, 10], [62, 11]], "ok": 6, "skipped": 0,
             "failed": 0, "stopped": "", "leftover": 0, "env_block_count": 0, "inconclusive_count": 0},
            {"stage": "water_area", "tiles": [[60, 10], [60, 11], [61, 10], [61, 11],
                                              [62, 10], [62, 11]], "ok": 6, "skipped": 0,
             "failed": 0, "stopped": "", "leftover": 0, "env_block_count": 0, "inconclusive_count": 0},
        ]
        end["plots"] = [{"zone": "field_ne", "tillable": 6, "plantable": 6, "watered": 6}]
        end["outcomes"] = [{"task": "water_area", "verdict": "completed"}]
        end["notes"] = ["伪造账本：字段全自洽，但没有任何外部锚点证明这一天真的发生过"]
        end["final_water"] = {"t": float(d * 600 + 510), "location": "Farm", "tiles": 6,
                              "crops": 6, "dry": 0, "scope": "farm"}
    elif mode == "forged_empty":
        # neg-K2：更极端的自洽伪造 —— **整天没有任何阶段、没有任何动作**（ok=skipped=failed=0、
        # stages=[]），但照样自称睡过去了、跨日、checks 全绿。工具仍应 exit 0 ⇒ 说明连
        # "什么都没做"的自洽账本都过得了账本检查。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 0
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = []
        end["plots"] = []
        end["outcomes"] = []
        end["notes"] = ["伪造账本：这一天什么都没做，却自称 VERIFIED"]
        end["final_water"] = {"t": float(d * 600 + 510), "location": "FarmHouse", "tiles": 0,
                              "crops": 0, "dry": 0, "scope": "window"}
    elif mode == "t19_window_no_outdoor":
        # neg-R（task-19 验收前的盲区探针）：自称 watered_outdoor=true，但 final_water 明说走的是
        # window 口径、且覆盖 0 格（= 当天**没有任何户外快照**）。task-19 要求 4 明令这种情形
        # "如实 False/缺省，禁止默认 true" ⇒ 这条"true"在账本里**无法被证明**。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block_count"] = 0
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0,
                          "env_block_count": 0, "inconclusive_count": 0}]
        end["plots"] = [{"zone": "field_ne", "tillable": 32, "plantable": 32, "watered": 32}]
        end["final_water"] = {"t": float(d * 600 + 510), "location": "FarmHouse", "tiles": 0,
                              "crops": 0, "dry": 0, "scope": "window"}
    elif mode == "t19_farm_scope_ok":
        # neg-S（正对照）：farm 口径、有覆盖、dry=0 ⇒ 合法绿日，必须 exit 0。
        # 用来守"给 watered_outdoor 加证明力检查"时不会误杀合法的一天。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 32
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["env_block_count"] = 0
        end["inconclusive_count"] = 0
        end["stages"] = [{"stage": "water_area", "tiles": 32, "ok": 32, "skipped": 0,
                          "failed": 0, "stopped": "", "leftover": 0,
                          "env_block_count": 0, "inconclusive_count": 0}]
        end["plots"] = [{"zone": "field_ne", "tillable": 32, "plantable": 32, "watered": 32}]
        end["final_water"] = {"t": float(d * 600 + 510), "location": "Farm", "tiles": 32,
                              "crops": 32, "dry": 0, "scope": "farm"}
    elif mode == "t15_last_round_done":
        # neg-P（task-15 口径，Lead 权威定义）：**同一阶段种类当天两条记录** —— 更早一轮因种子
        # 用完 leftover=5、最后一条把同一批做净 leftover=0。日级后置条件应以**最后一条**为准 ⇒
        # 期望 exit 0；`stage_midway_leftover` 只记信息项（证明遮蔽已被显式记录）。
        # 旧工具会把两条字面相加成 5 ⇒ 误报"checks.no_unmet_stages=true 与自算不一致"。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 5
        end["skipped_steps"] = 0
        end["failed_steps"] = 0
        end["stages"] = [
            {"stage": "plant_area", "tiles": 5, "ok": 0, "skipped": 0, "failed": 0,
             "failed_any": 1, "env_block": 1, "inconclusive": 0,
             "stopped": "no_seed", "leftover": 5},
            {"stage": "plant_area", "tiles": 5, "ok": 5, "skipped": 0, "failed": 0,
             "failed_any": 1, "env_block": 1, "inconclusive": 0,
             "stopped": "", "leftover": 0},
        ]
        end["plots"] = [{"zone": "field_ne", "tillable": 5, "plantable": 5, "watered": 5}]
        # t 单调：decision(d*600+5) 之后、sleep(d*600+500) 之前
        rows.insert(2, {"t": float(d * 600 + 100), "event": "stage_midway_leftover",
                        "day": ["1", "spring", d], "stage": "plant_area", "tiles": 5,
                        "leftover": 5, "round": 1,
                        "note": "更早一轮因种子用完留下 leftover=5，同日买到种子后做净（日级以最后一轮为准）"})
    elif mode == "t15_earlier_done_last_leftover":
        # neg-Q（遮蔽的反方向）：更早一轮做净 leftover=0，**最后一条**却有 leftover=5
        # （例如换了另一片地、前一片干净后一片没做完）⇒ 必须仍报"未完成"，不许被更早的干净记录遮蔽。
        end["verified"] = True
        end["checks"] = {"slept_by_us": True, "no_blocking_modal": True, "no_hard_failures": True,
                         "crops_watered": True, "watered_outdoor": True, "no_unmet_stages": True,
                         "day_justified": True}
        end["ok_steps"] = 5
        end["skipped_steps"] = 0
        end["failed_steps"] = 5
        end["stages"] = [
            {"stage": "water_area", "tiles": 5, "ok": 5, "skipped": 0, "failed": 0,
             "stopped": "", "leftover": 0},
            {"stage": "water_area", "tiles": 5, "ok": 0, "skipped": 0, "failed": 5,
             "stopped": "bridge", "leftover": 5},
        ]
    else:
        raise SystemExit("unknown mode " + mode)
    rows.append(end)
    return rows


def build(mode: str) -> list[dict]:
    rows: list[dict] = []
    for d in (10, 11, 12):
        rows.extend(day_block(d, mode=mode))
    # finish 的 t 必须晚于最后一天 day_end（12*600+520=7720），否则触发 verify-run3 的时间戳回退检查
    rows.append({"t": 7900.0, "event": "finish", "code": 0, "verified_streak": 3, "days": 3})
    return rows


def main() -> int:
    for mode, name in (("no_verified", "review-neg-A-no-verified.jsonl"),
                       ("self_report_green", "review-neg-B-self-report-green.jsonl"),
                       ("missing_self_report", "review-neg-C-fallback-ok.jsonl"),
                       ("self_report_unmet_but_verified", "review-neg-D-unmet-but-verified.jsonl"),
                       ("watered_no_evidence", "review-neg-E-watered-no-evidence.jsonl"),
                       ("watered_outdoor_false", "review-neg-F-watered-outdoor-false.jsonl"),
                       ("env_info_item", "review-neg-G-env-info-item.jsonl"),
                       ("env_info_cannot_mask", "review-neg-H-env-info-cannot-mask.jsonl"),
                       ("env_explained", "review-neg-I-env-explained.jsonl"),
                       ("env_understated", "review-neg-J-env-understated.jsonl"),
                       ("forged_consistent", "review-neg-K-forged-consistent.jsonl"),
                       ("forged_empty", "review-neg-K2-forged-empty.jsonl"),
                       ("t19_window_no_outdoor", "review-neg-R-t19-window-no-outdoor.jsonl"),
                       ("t19_farm_scope_ok", "review-neg-S-t19-farm-scope-ok.jsonl"),
                       ("t15_last_round_done", "review-neg-P-t15-last-round-done.jsonl"),
                       ("t15_earlier_done_last_leftover",
                        "review-neg-Q-t15-masked-leftover.jsonl")):
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as fh:
            for row in build(mode):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("wrote", path, os.path.getsize(path), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
