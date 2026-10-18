# -*- coding: utf-8 -*-
"""product-observer: 报告二次校对（口径/数字/措辞），只改文字不动结论。"""
from pathlib import Path

P = Path("docs/_review-product-gaps.md")
s = P.read_text(encoding="utf-8")

REPS = [
    # §4 表有 6 行
    ("以下五类问题它们**看不见**", "以下六类问题它们**看不见**"),
    # §4-5 行号漂移
    ("截断按 unobserved，工作树 `:4988-4991`", "截断按 unobserved，工作树 `:4993` 起"),
    # §3.2② 小麦 4 天成熟，不是 10 天
    ("先买不到 472 就只能种 10 粒 Wheat，10 天后收获 1 叠 Wheat，仍卡 12 格",
     "先买不到 472 就只能种 10 粒 Wheat（4 天成熟），收成 1 叠 Wheat 仍只占 1 格、腾不出新格"),
    # §5-A4 分母应为 33 条进校验的意图
    ("`unknown ∕ cancel` 意图占比从 29/36 降到 <50%", "`unknown ∕ cancel` 意图占比从 29/33 降到 <50%"),
    # §2.4 L2：FAIL 5 天 = stuck 2 + 回片区 3
    ("12 天形态未下降（`no_progress_burst` 3 次、`stuck` 5 天）",
     "12 天形态未下降（FAIL 5 天 = `stuck` 2 天 + 回片区 3 天，`no_progress_burst` 3 次）"),
    # §5-A1 验收判据歧义
    ("`day_end` 里 `checks.day_justified=true` 的每一天都必须带 `pending_executable=0 / pending_blocked>0 / pending_unobserved>0` 且不变式成立",
     "`day_end` 里 `checks.day_justified=true` 的每一天都必须同时落 `pending_executable/pending_blocked/pending_unobserved` 三个读数、`pending_executable=0`、且不变式成立"),
    # §6-6 diff stat 改为不写死数字
    ("工作树 `M brain/agentfarm/longrun.py (+242/−24)` 未提交、未评审",
     "工作树 `M brain/agentfarm/longrun.py`（task-15 在制，审计期间仍在变动，行号会漂）未提交、未评审"),
]

for old, new in REPS:
    if new in s:
        continue
    assert old in s, "missing: " + old[:50]
    s = s.replace(old, new)

# §0 加"快照口径"说明（放在复跑脚本说明之后）
anchor = "关键事件计数（我自己重跑核对，非引用）："
note = (
    "口径说明：\n"
    "- 代码行号钉在**审计时工作树快照**（HEAD `4cb6721` + task-15 在制改动）；task-15 提交后行号会漂，"
    "关键点一律同时给函数名（`sleep_guard`/`_pending_snapshot`/`is_justified_end`/`_review_facts` 等），以函数名 grep 为准。\n"
    "- `A8 Lxxx` = `logs/longrun-runA8-0743.jsonl` 的第 xxx 行；`smoke-llm.jsonl:N` = 该文件第 N 行（1=冬26 decision，2=冬26 review，3=冬27 decision，4=冬27 review）。\n"
    "- LLM 意图归属口径：`decision.source=llm` 的 12 条 × 3 条意图 = 36 条，意图 id 为 `<day>#01..#03`；其中 33 条进了 `_verify_intents`（`review` 类不进）。\n\n"
)
if note not in s:
    assert anchor in s
    s = s.replace(anchor, note + anchor)

P.write_text(s, encoding="utf-8", newline="\n")
print("patched", len(s), "chars")
