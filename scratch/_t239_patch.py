# -*- coding: utf-8 -*-
"""一次性补丁：把 _t239_probe.py 的 C 段对齐到 Lead 2026-10-18 升级后的判据文案。

只改我自己的 scratch 探针；改完即用于跑 C 段，随后可删。
"""
from pathlib import Path

P = Path(__file__).parent / "_t239_probe.py"
s = P.read_text(encoding="utf-8")

subs = [
    # case_c 里旧的 needle 变量（B 段已改，C 段漏改）
    ('    needle = "末次跨日未落盘"\n', ""),
    # C1b / C1c / C2b / C7b：改用 smapi_problem()
    ('needle in out, f"needle={needle in out}"',
     'smapi_problem(out), f"hit={smapi_problem(out)}"'),
    ('"已判红" if needle in out else "⚠ GAP-236-1：L16 让真形态假绿（作弊通道成立）"',
     '"已判红" if smapi_problem(out) else "⚠ GAP-236-1：L16 让真形态假绿（作弊通道成立）"'),
    ('needle in out2,\n              "已判红" if needle in out2 else',
     'smapi_problem(out2),\n              "已判红" if smapi_problem(out2) else'),
    ('needle in out7,\n              "仍判红" if needle in out7 else',
     'smapi_problem(out7),\n              "仍判红" if smapi_problem(out7) else'),
    # 237 marker：`target_free` 是 0.7.40 既有词 ⇒ 假真，只能用 harvest_demand
    ('has237 = "harvest_demand" in lr or "target_free" in lr',
     'has237 = "harvest_demand" in lr'),
    # C3a / C3b：SMAPI 侧兜住的防御性缺口 ⇒ info（不阻塞），不算 FAIL
    ('''    check("C3a 产品判据覆盖 finish.cleanup_modal_stuck 自相矛盾", stuck_is_checked,
          "verify-run3 已引用" if stuck_is_checked else "⚠ GAP-236-4：verify-run3 完全不看 cleanup 自述 ⇒ 矛盾账本无法被发现")''',
     '''    if stuck_is_checked:
        info("C3a 产品判据覆盖 finish.cleanup_modal_stuck 自相矛盾", "verify-run3 已引用")
    else:
        info("C3a 产品判据不查 cleanup 自述（GAP-236-6，防御性缺口、不阻塞）",
             "verify-run3 不看 cleanup_modal_stuck；伪造该矛盾需手改账本，底层缺落盘由 SMAPI 六串兜住")'''),
    ('''    check("C3b 检查器覆盖 finish.cleanup_modal_stuck 自相矛盾", stuck_in_checker,
          "检查器已引用" if stuck_in_checker else "⚠ GAP-236B-3：检查器只数 SMAPI 六串，不看账本 cleanup 自述")''',
     '''    if stuck_in_checker:
        info("C3b 检查器覆盖 finish.cleanup_modal_stuck 自相矛盾", "检查器已引用")
    else:
        info("C3b 检查器不查 cleanup 自述（GAP-236B-6，同上、不阻塞）",
             "检查器只数 SMAPI 六串，journal_brief 只陈述账本行数/day_end/finish")'''),
    # C3c：`def _finish(` 精确匹配（原先 find("def _finish") 命中了 _finish_intent_coverage）
    ('seg = lr[lr.find("def _finish"):]', 'seg = lr[lr.find("def _finish("):]'),
]

for old, new in subs:
    if old not in s:
        raise SystemExit(f"[FAIL] 锚点未命中：{old[:60]!r}")
    s = s.replace(old, new, 1)

P.write_text(s, encoding="utf-8", newline="\n")
print("patched:", P)
