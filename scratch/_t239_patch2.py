# -*- coding: utf-8 -*-
"""task-239 探针补丁 2：C4 对齐 237 实现、C3c 强化为精确放行检查、补自想通道 C8/C9。

只改 `scratch/_t239_probe.py`（我自己的探针）。
"""
from pathlib import Path

P = Path(__file__).parent / "_t239_probe.py"
s = P.read_text(encoding="utf-8")

old_c3c = '''    # C3c 若 236 脑侧已落地：cleanup 卡住时 finish.code 必须非 0（正文找得到强约束才算过）
    if has236:
        seg = lr[lr.find("def _finish("):]
        seg = seg[:4000] if seg else ""
        check("C3c 脑侧：cleanup 卡住 ⇒ finish.code 非 0（stuck 上抬）",
              bool(seg) and ("cleanup_modal_stuck" in seg) and ("code" in seg), seg[:60])
    else:
        skip("C3c 脑侧 finish.code 与 cleanup 一致性", "task-236 未落地")'''

new_c3c = '''    # C3c 若 236 脑侧已落地：cleanup 卡住时 finish.code 必须被上抬（精确找重赋值）
    if has236:
        seg = lr[lr.find("def _finish("):]
        seg = seg[:5000] if seg else ""
        escalated = bool(re.search(
            r'cleanup(?:_modal_stuck|\\["stuck"\\]|\\[.stuck.\\])[\\s\\S]{0,600}?'
            r'\\bcode\\s*=\\s*(?!code\\b)', seg))
        check("C3c 脑侧：cleanup 卡住 ⇒ finish.code 非 0（stuck 上抬为 fail-closed）",
              escalated,
              "已上抬" if escalated else
              "⚠ GAP-236-7（候选，防御性）：_finish 只把 stuck 写进 summary/journal，return code 不变 ⇒ "
              "账本可同时出现 finish.code=0 与 cleanup_modal_stuck=true（真机缺落盘由 smoke 步 6 的 SMAPI 判据兜住）")
    else:
        skip("C3c 脑侧 finish.code 与 cleanup 一致性", "task-236 未落地")'''

old_c4 = '''        cap_src = re.findall(r"min\\([^\\n]*12[^\\n]*\\)", lr)
        check("C4a 源码存在 min(...,12) 钉上界", bool(cap_src), str(cap_src[:2]))
        check("C4b 需求来自可收格数而非手写", ("harvest_demand" in lr) and ("12" in lr),
              "落地后在 B 段用账本抽查")'''

new_c4 = '''        cap_m = re.search(r"HARVEST_DEMAND_CAP\\s*=\\s*(\\d+)", lr)
        clamp_cap = bool(re.search(r"min\\(int\\(HARVEST_DEMAND_CAP\\),\\s*int\\(demand\\)\\)", lr))
        clamp_zero = bool(re.search(r"max\\(0,\\s*min\\(", lr))
        check("C4a 237 上界钉死：HARVEST_DEMAND_CAP=12 且 clamp 到 [0,12]",
              bool(cap_m) and cap_m.group(1) == "12" and clamp_cap and clamp_zero,
              f"cap={cap_m.group(1) if cap_m else None} clamp_cap={clamp_cap} clamp_zero={clamp_zero}")
        check("C4b 需求来自可收格数而非手写", ("_harvest_demand" in lr) and ("harvest_demand" in lr),
              "引擎在 _harvest_demand；字段名 harvest_demand 由 _slot_relief 写入")

    # ---- C8（我自想通道·Lead m10120 方向）：收尾清理不得关不可逆模态 ----
    if has236:
        seg = lr[lr.find("def _cleanup_modals_before_finish"):]
        seg = seg[:9000] if seg else ""
        guard_event = "eventUp" in seg
        guard_prof = ("LevelUpMenu" in seg) and ("professionsToChoose" in seg)
        wait_only = "MODAL_WAIT_ONLY" in seg
        skipped_logged = "cleanup_skipped" in lr
        check("C8a 收尾清理守卫：eventUp/职业弹窗绝不关、存档菜单只等不关、跳过如实记账",
              guard_event and guard_prof and wait_only and skipped_logged,
              f"eventUp={guard_event} profession={guard_prof} wait_only={wait_only} skipped={skipped_logged}")
        md = tree.src("mod/AgentFarm.Bridge/ModalDismiss.cs")
        mod_guard = ("wait_only" in md) and ("ShippingMenu" in md) and ("IsSaveMenu" in md)
        check("C8b Mod 侧兜底：dismiss 存档/出货菜单必拒（wait_only）", mod_guard, "ModalDismiss.cs 双保险")
        # 假世界：职业弹窗在收尾时挂着 ⇒ 清理必须 skip、一次 dismiss 都不发
        try:
            w = TL.FakeWorld()
            w.ui_script = [{"activeMenu": "LevelUpMenu", "isModal": True,
                            "professionsToChoose": [{"index": 0, "name": "Tiller"}]}]
            run = TL.make_run(w, target_days=1, max_days=1)
            res = run._cleanup_modals_before_finish()
            check("C8c 职业弹窗挂着 ⇒ cleanup 跳过且零 dismiss",
                  res.get("skipped") == "profession_pending" and w.dismiss_calls == 0,
                  f"skipped={res.get('skipped')} dismiss_calls={w.dismiss_calls}")
            w2 = TL.FakeWorld()
            w2.ui_script = [{"activeMenu": "DialogueBox", "isModal": True, "eventUp": True}]
            run2 = TL.make_run(w2, target_days=1, max_days=1)
            res2 = run2._cleanup_modals_before_finish()
            check("C8d 事件对话挂着 ⇒ cleanup 跳过且零 dismiss",
                  res2.get("skipped") == "event_up" and w2.dismiss_calls == 0,
                  f"skipped={res2.get('skipped')} dismiss_calls={w2.dismiss_calls}")
        except Exception as exc:  # noqa: BLE001 — 夹具不可用记 SKIP，不冒充通过
            skip("C8c/C8d 动态：职业/事件弹窗挂着时 cleanup 跳过", f"假世界构造失败：{type(exc).__name__}: {exc}")'''

for old, new in ((old_c3c, new_c3c), (old_c4, new_c4)):
    if old not in s:
        raise SystemExit(f"[FAIL] 锚点未命中：{old[:70]!r}")
    s = s.replace(old, new, 1)

P.write_text(s, encoding="utf-8", newline="\n")
print("patched2:", P)
