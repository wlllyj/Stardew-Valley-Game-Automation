"""task-198 ç¦»çº¿æŽ¨æ¼”ï¼šç”¨ run Aâ€²ï¼ˆ`logs/longrun-runA3-0736.jsonl`ï¼‰çš„çœŸå®žåºåˆ—æž„é€ å‡ä¸–ç•Œï¼Œ
çœ‹åŒä¸€å½¢æ€åœ¨**ä¿®å‰/ä¿®åŽ**åˆ†åˆ«ä¼šæ€Žæ ·ã€‚

Aâ€² çš„çœŸå®žè¯»æ•°ï¼ˆåªè¯»æ‰«æï¼Œä¸è·‘æ¸¸æˆï¼‰ï¼š
  * day_start/day_end 4 å¤©ï¼›`harvest` é˜¶æ®µ `stage_stop_named{assigned:12, assigned_undone:12, codes:["failed"]}`ï¼›
  * 45 æ¡åŒå¥å¤±è´¥ï¼š`(63, 18): èƒŒåŒ…æ»¡ï¼ˆç©ºæ§½ = inventoryCount å®¹é‡ âˆ’ inventory[] è¡Œæ•° = 0â€¦ï¼‰â‡’ å…ˆå‡ºè´§/æ•´ç†èƒŒåŒ…å†æ¥æ”¶`ï¼›
  * `harvest_gave_up` 80 æ¡ï¼ˆæ¯æ ¼ attempts=2/limit=2ï¼‰ï¼›
  * æ•´å¤© `no_hard_failures=false` â‡’ ä¸å¯èƒ½ VERIFIEDï¼Œæ”¶å°¾æ˜¯ `stuck:è¿žç»­ 3 è½®ä¸–ç•Œæ²¡æœ‰ä»»ä½•å˜åŒ–â€¦`ï¼›
  * èƒŒåŒ…æ»¡æ˜¯**å…¨å±€**é˜»å¡žï¼ˆä¸æ˜¯æŸä¸€æ ¼æ‘˜ä¸ä¸‹æ¥ï¼‰ï¼Œè€Œ `sell`/`ship` å½“æ—¶éƒ½åœ¨è·‘ â‡’ ç¼ºçš„æ˜¯"å…ˆè…¾æ ¼å†æ”¶"ã€‚

ç”¨æ³•ï¼špython scratch/_t198_replay.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))

from agentfarm.farmwork import FarmWorker, player_free_slots          # noqa: E402
from tests.test_longrun import (                                      # noqa: E402
    FakeWorld, _LootClient, make_run,
)

ASSIGNED = 12          # Aâ€² day13 harvest åˆ†é… 12 æ ¼
CAPACITY = 12          # èƒŒåŒ…å®¹é‡ï¼ˆç©ºæ§½æŒ‰ inventory[] è¡Œæ•°ç®—ï¼‰


class _LiveFarmWorld(FakeWorld):
    """farm æ‰«æéšä¸–ç•Œåˆ·æ–°ï¼ˆçœŸæ¡¥æ¯å¸§éƒ½å‘ï¼‰â€”â€”é¿å…é™æ€ farm é€ æˆ"å†œåœºå£å¾„è¿˜æœ‰ç†Ÿä½œç‰©"çš„å‡ stuckã€‚"""

    def obs(self):
        obs = super().obs()
        ripe = sum(1 for c in self.crops.values() if c.get("ripe"))
        self.farm = {"loaded": True, "complete": True, "crops": len(self.crops),
                     "ripeCrops": ripe, "deadCrops": 0, "unwateredCrops": 0,
                     "dryCrops": 0, "dryDeadCrops": 0, "dryTiles": [],
                     "dryTilesTruncated": False, "hoeDirt": len(self.dirt),
                     "emptyDirt": len(self.dirt - set(self.crops)), "stumps": 0,
                     "logs": 0, "boulders": 0, "rockPiles": 0, "greenRain": 0,
                     "clumpsTotal": 0, "clumpsUnclassified": 0}
        obs["farm"] = dict(self.farm)
        return obs


def _world(*, rows: int, ripe: int = ASSIGNED) -> FakeWorld:
    """æŒ‰ Aâ€² å½¢æ€é€ ä¸€ä¸ªæœˆï¼šç”°é—´ `ripe` æ ¼ç†Ÿä½œç‰©ã€èƒŒåŒ… `rows` è¡Œï¼ˆæ»¡ = CAPACITYï¼‰ã€‚"""
    w = _LiveFarmWorld(seeds=0, money=0, weeds=0)
    tiles = [(60 + i, 10) for i in range(ripe)]
    w.dirt = set(tiles)
    w.crops = {t: {"ripe": True, "watered": True} for t in tiles}
    inv = [{"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe",
            "stack": 1, "isTool": True},
           {"slot": 1, "id": "Hoe", "qualifiedId": "(T)Hoe", "name": "Hoe",
            "stack": 1, "isTool": True}]
    while len(inv) < rows:
        inv.append({"slot": len(inv), "id": "388", "qualifiedId": "(O)388",
                    "name": "Wood", "stack": 99, "isTool": False})
    w.inventory = inv[:rows]
    return w


def _run_day(**kw):
    w = _world(**kw)
    run = make_run(w, max_days=1, target_days=1)
    client = _LootClient(w)
    # `run()` ç”¨å·¥åŽ‚é‡å»º client/worker â‡’ å¿…é¡»æ”¹å·¥åŽ‚ï¼Œä¸èƒ½åªèµ‹å±žæ€§
    run.client_factory = lambda: client
    run.worker_factory = lambda c: FarmWorker(c, log=lambda *_: None,
                                              pause=lambda *_: None)
    run.run()
    rep = run.days[0]
    relief = [e for e in run.entries if e["event"] == "slot_relief"]
    blocked = [e for e in run.entries if e["event"] == "inventory_blocked"]
    free_after = player_free_slots({"inventory": w.inventory,
                                    "inventoryCount": CAPACITY})[0]
    return {
        "ended_by": rep.ended_by,
        "reason": rep.ended_reason[:120],
        "failed_steps": rep.failed_steps,
        "no_hard_failures": rep.checks.get("no_hard_failures"),
        "verified": rep.verified,
        "ok_steps": rep.ok_steps,
        "crops_left": len(w.crops),
        "relief_rounds": len(relief),
        "relief_freed": sum(int(e.get("freed") or 0) for e in relief),
        "relief_before": [e.get("freeSlots_before") for e in relief],
        "inventory_blocked_events": len(blocked),
        "free_slots_after": free_after,
        "sold": list(getattr(client, "sold", [])),
    }


def main() -> int:
    print("run Aâ€² çœŸå®žåºåˆ—ï¼ˆlogs\\longrun-runA3-0736.jsonlï¼Œåªè¯»ï¼‰")
    print("  æ—§ä»£ç ï¼šharvest 45 æ¡ `èƒŒåŒ…æ»¡â€¦` å¤±è´¥ Â· harvest_gave_up 80 Â· "
          "stage_stop_named{assigned:12, assigned_undone:12} Â· no_hard_failures=false Â· æ”¶å°¾ stuck")
    print()
    print("A. ä¿®åŽï¼šæ»¡åŒ… 12 è¡Œ + 12 æ ¼ç†Ÿ + å†œåœºæ²¡æœ‰ç©ºè€•åœ°ï¼ˆè…¾ä¸å‡ºï¼‰")
    a = _run_day(rows=CAPACITY, ripe=ASSIGNED, )
    for k, v in a.items():
        print(f"   {k}: {v}")
    print()
    print("B. ä¿®åŽï¼šåªå‰© 2 ç©ºæ ¼ + 12 æ ¼ç†Ÿï¼ˆè¾¹æ”¶è¾¹è…¾ == åŒä¸€å¤©æ”¶å®Œï¼‰")
    b = _run_day(rows=CAPACITY - 2, ripe=ASSIGNED, )
    for k, v in b.items():
        print(f"   {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

