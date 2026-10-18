# -*- coding: utf-8 -*-
"""task-239 探针补丁 3（稳健版）：C3c 改 INFO、C8c/C8d 动态装载树内模块。"""
from pathlib import Path

P = Path(__file__).parent / "_t239_probe.py"
s = P.read_text(encoding="utf-8")

# ---- 1) C3c 整块替换（按起止标记定位，不依赖精确空白） ----
start = s.find("    # C3c 若 236 脑侧已落地")
end_marker = 'skip("C3c 脑侧 finish.code 与 cleanup 一致性", "task-236 未落地")'
end = s.find(end_marker)
if start < 0 or end < 0:
    raise SystemExit("[FAIL] C3c 起止标记未命中")
end += len(end_marker)
new_c3c = '''    # C3c 236 脑侧：设计上 cleanup 卡住只作运行级诚实记账、不上抬 finish.code
    #      （源码明文：不进 checks、不给洗白面）。代价=账本可能 code=0 + stuck=true；
    #      真机缺落盘的权威判据是 smoke 步 6 的 SMAPI 六串 ⇒ 记 INFO、不阻塞。
    if has236:
        after = lr[lr.find("cleanup = self._cleanup_modals_before_finish()"):][:3000]
        escalated = bool(re.search(r"^\\s{8}code\\s*=\\s*[^=]", after, re.M))
        if escalated:
            info("C3c 脑侧 cleanup 卡住 ⇒ finish.code 上抬", "已 fail-closed 上抬")
        else:
            info("C3c 脑侧 design：cleanup 卡住只作运行级记账、不上抬 finish.code（GAP-236-7，非阻塞）",
                 "账本可能 code=0 + cleanup_modal_stuck=true；权威判据是 smoke 步 6 的 SMAPI 六串（一红一绿本轮已验）")
    else:
        skip("C3c 脑侧 finish.code 与 cleanup 一致性", "task-236 未落地")'''
s = s[:start] + new_c3c + s[end:]

# ---- 2) C8 动态：改用树内模块装载 ----
old_dyn = '''            w = TL.FakeWorld()'''
new_dyn = '''            _lr_mod, TL = _load_tree(tree)
            w = TL.FakeWorld()'''
if old_dyn not in s:
    raise SystemExit("[FAIL] C8 动态锚点未命中")
s = s.replace(old_dyn, new_dyn, 1)

# ---- 3) 插入装载器 ----
anchor = "def sha16(text: str) -> str:"
loader = '''def _load_tree(tree: Tree):
    """按 tree.base 装载 `agentfarm.longrun` 与 `tests.test_longrun`（动态通道用）。"""
    import importlib
    base = tree.base
    for p in (str(base / "brain"), str(base)):
        if p not in sys.path:
            sys.path.insert(0, p)
    lr = importlib.import_module("agentfarm.longrun")
    tl = importlib.import_module("tests.test_longrun")
    return lr, tl


def sha16(text: str) -> str:'''
if anchor not in s:
    raise SystemExit("[FAIL] loader 锚点未命中")
s = s.replace(anchor, loader, 1)

P.write_text(s, encoding="utf-8", newline="\n")
print("patched3:", P)
