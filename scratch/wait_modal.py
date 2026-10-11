"""等模态自己消失（例如 SaveGameMenu），并报告时钟是否恢复推进 + 存档 mtime。

只读：只 observe，不发技能。用法： PYTHONPATH=<repo>/brain python scratch/wait_modal.py [秒数]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient  # noqa: E402

SAVE = Path.home() / "AppData" / "Roaming" / "StardewValley" / "Saves" / "Wahaha_450799035" / "Wahaha_450799035"


def brief(obs: dict) -> str:
    return json.dumps(
        {
            "clock": obs.get("clock"),
            "menu": (obs.get("ui") or {}).get("activeMenu"),
            "isModal": (obs.get("ui") or {}).get("isModal"),
            "liveness": obs.get("liveness"),
            "worldSeq": obs.get("worldSeq"),
            "saveMtime": time.strftime("%H:%M:%S", time.localtime(SAVE.stat().st_mtime)) if SAVE.exists() else None,
            "saveBytes": SAVE.stat().st_size if SAVE.exists() else None,
        },
        ensure_ascii=False,
    )


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    client = BridgeClient(timeout=30.0)
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        obs = client.observe("summary")
        line = brief(obs)
        if line != last:
            print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)
            last = line
        if not (obs.get("ui") or {}).get("isModal") and (obs.get("liveness") or {}).get("worldAdvancing"):
            print("=> 模态已清空且时钟在走", flush=True)
            return 0
        time.sleep(3.0)
    print("=> 超时仍未恢复", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
