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
        rows.insert(3, {"t": float(d * 600 + 300), "event": "env_fail", "day": ["1", "spring", d],
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
        rows.insert(3, {"t": float(d * 600 + 300), "event": "env_fail", "day": ["1", "spring", d],
                        "stage": "plant_area", "tiles": [[60, 10]],
                        "statuses": ["ui_modal"], "count": 1})
    else:
        raise SystemExit("unknown mode " + mode)
    rows.append(end)
    return rows


def build(mode: str) -> list[dict]:
    rows: list[dict] = []
    for d in (10, 11, 12):
        rows.extend(day_block(d, mode=mode))
    rows.append({"t": 1900.0, "event": "finish", "code": 0, "verified_streak": 3, "days": 3})
    return rows


def main() -> int:
    for mode, name in (("no_verified", "review-neg-A-no-verified.jsonl"),
                       ("self_report_green", "review-neg-B-self-report-green.jsonl"),
                       ("missing_self_report", "review-neg-C-fallback-ok.jsonl"),
                       ("self_report_unmet_but_verified", "review-neg-D-unmet-but-verified.jsonl"),
                       ("watered_no_evidence", "review-neg-E-watered-no-evidence.jsonl"),
                       ("watered_outdoor_false", "review-neg-F-watered-outdoor-false.jsonl"),
                       ("env_info_item", "review-neg-G-env-info-item.jsonl"),
                       ("env_info_cannot_mask", "review-neg-H-env-info-cannot-mask.jsonl")):
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as fh:
            for row in build(mode):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("wrote", path, os.path.getsize(path), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
