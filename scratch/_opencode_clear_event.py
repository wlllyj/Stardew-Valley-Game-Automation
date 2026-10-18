# -*- coding: utf-8 -*-
"""受控推进 Spring1Y2 的 Kent 返乡事件对话（非提问），直到模态消失。

只用游戏自己的入口（Mod 的 advance_dialogue → DialogueBox.receiveLeftClick），
不合成键鼠、不跳句（不是 closeDialogue）。判据看观测差分。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402

c = BridgeClient(timeout=30.0)

for rnd in range(1, 13):
    obs = c.observe(detail="full")
    ui = obs.get("ui") or {}
    print(f"[round {rnd}] isModal={ui.get('isModal')} activeMenu={ui.get('activeMenu')} "
          f"eventUp={ui.get('eventUp')} eventId={ui.get('eventId')} "
          f"isQuestion={ui.get('dialogueIsQuestion')} menus={ui.get('onScreenMenus')}")
    if not ui.get("isModal"):
        print("=> 模态已消失")
        break
    if ui.get("dialogueIsQuestion"):
        print("=> 是提问对话，停手（不替游戏选）")
        break
    try:
        res = c.advance_dialogue(max_steps=20, timeout_ms=90000)
        print(f"    advance_dialogue status={res.get('status')} reason={res.get('reason')} "
              f"stepped={res.get('stepped')} stalled={res.get('stalled')} "
              f"before={res.get('before')} after={res.get('after')}")
    except BridgeError as exc:
        # 非 ok 状态不代表没推进：照实打印，继续按观测差分决定下一步
        print(f"    advance_dialogue BridgeError: {exc}")

obs = c.observe(detail="full")
ui = obs.get("ui") or {}
p = obs.get("player") or {}
print("=== 终态 ===")
print(f"ui: isModal={ui.get('isModal')} activeMenu={ui.get('activeMenu')} eventUp={ui.get('eventUp')}")
print(f"player: canMove={p.get('canMove')} location={p.get('location')} tile={p.get('tile')}")
print(f"clock: {obs.get('clock')}  worldSeq={obs.get('worldSeq')}")
