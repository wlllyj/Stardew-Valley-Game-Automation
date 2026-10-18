# -*- coding: utf-8 -*-
"""product-observer: 把报告里因 task-15 在制改动而漂移的代码行号对齐到当前工作树快照。

只改行号，不改结论。幂等：每次运行前断言旧串存在。
"""
from pathlib import Path

P = Path("docs/_review-product-gaps.md")
s = P.read_text(encoding="utf-8")

REPS = [
    ("`brain/agentfarm/longrun.py:5519-5520`；挡死格拦截 `:5525-5529` 是 task-15 在制新增，冻结树无",
     "`brain/agentfarm/longrun.py:5535`（`if not reasons:` 之后才判 no_work）；挡死格拦截 `:5540-5544` 是 task-15 在制新增，0.7.44 冻结树无"),
    ("`longrun.py:4282 _review_before_sleep`、`:4225 _review_facts`",
     "`longrun.py:4287 _review_before_sleep`、`:4230 _review_facts`（字段 `ended_by/ended_reason` 在 `:4237-4238` 有，但复盘时尚未定稿 ⇒ 值为空）"),
    ("校验点 `longrun.py:7675 _verify_intents`", "校验点 `longrun.py:7690 _verify_intents`"),
    ("说明 `longrun.py:4245/4247` 的 `recent_notes→lessons_hints` 生效", "说明 `longrun.py:4319/4321` 的 `recent_notes→lessons_hints` 生效"),
    ("代码自述 `longrun.py:4257` `note=", "代码自述 `longrun.py:4331` `note="),
    ("`longrun.py:7757`", "`longrun.py:7772`"),
    ("账本；`longrun.py:6156-6169`", "账本；`longrun.py:6213-6220`"),
    ("`_buy_seed`（longrun.py:6451）", "`_buy_seed`（longrun.py:6466）"),
    ("（longrun.py:5567/5680/5745）", "（longrun.py:5582/5695/5760）"),
    ("（工作树 `longrun.py:774` 已有断言）", "（工作树 `longrun.py:776` 注释：`pending_guard == pending_executable + pending_unobserved`）"),
]

for old, new in REPS:
    if new in s:
        continue
    assert old in s, "missing: " + old[:50]
    s = s.replace(old, new)

P.write_text(s, encoding="utf-8", newline="\n")
print("patched", len(s), "chars")
