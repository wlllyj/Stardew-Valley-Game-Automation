import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\OpenCode Workspace\星露谷游戏自动化\brain")))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from agentfarm.bridge import BridgeClient
c = BridgeClient(timeout=30.0)
for i in range(6):
    time.sleep(15)
    obs = c.observe(detail="full")
    ui = obs.get("ui") or {}
    p = obs.get("player") or {}
    print(f"[+{(i+1)*15:>3}s] isModal={ui.get('isModal')} activeMenu={ui.get('activeMenu')} "
          f"eventUp={ui.get('eventUp')} eventId={ui.get('eventId')} menus={ui.get('onScreenMenus')} "
          f"canMove={p.get('canMove')} seq={obs.get('worldSeq')} clock={obs.get('clock',{}).get('timeOfDay')}")
