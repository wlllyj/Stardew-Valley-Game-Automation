"""一次性探针：现在的模态弹窗（LevelUpMenu）能不能用 dismiss_modal 关掉。

判据只看观测：`ui.isModal` / `ui.activeMenu` / `liveness.worldAdvancing` / `clock`。
用法： PYTHONPATH=<repo>/brain python scratch/dismiss_now.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402


def brief(obs: dict) -> str:
    return json.dumps(
        {
            "clock": obs.get("clock"),
            "ui": obs.get("ui"),
            "canMove": (obs.get("player") or {}).get("canMove"),
            "liveness": obs.get("liveness"),
            "game": obs.get("game"),
            "worldSeq": obs.get("worldSeq"),
        },
        ensure_ascii=False,
    )


def main() -> int:
    client = BridgeClient(timeout=30.0)
    before = client.observe("full")
    print("BEFORE", brief(before))
    try:
        receipt = client.dismiss_modal(timeout_ms=8000)
        print("RECEIPT", json.dumps(receipt, ensure_ascii=False))
    except BridgeError as exc:
        print("RECEIPT-ERROR", exc.status, str(exc)[:400])
    after = client.observe("full")
    print("AFTER ", brief(after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
