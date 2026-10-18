"""只读探针：把 SeedShop 的**结构化货架清单**（availableItems）完整落盘。

背景（Lead m00822）：0.7.45 冒烟账本里 buy 事件 `available=20`，但回执文字清单
（BuySkill.Listing）**最多 12 条**再加「…」⇒ 剩余 8 条未知。Pierre SeedShop 货架
里到底有没有背包升级条目（Backpack / Deluxe Backpack），决定 0.7.46 的卡 A
走「买背包」还是「Plan B」。

做法：
1. 直连桥 `POST /v1/exec`，skill=buy，item=`__probe_none__`（**不存在的名字**，
   不可能真买成），count=1，shop=SeedShop；
2. 失败回执（item_not_sold）里 `availableItems` 会带完整货架（最多 30 条）；
3. 把 HTTP 原始响应体、解析后的回执、货架三元组（id/name/price）、背包候选
   逐条落 `scratch/_t18_shop_shelf.json`；同时把货架表打印到 stdout；
4. 退出前 dismiss_modal，避免把商店菜单留在游戏里（后续 stop-game 才干净）。
**不买任何东西、不改存档、不写世界。**
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError, inspect_bridge_json  # noqa: E402

OUT = REPO / "scratch" / "_t18_shop_shelf.json"
PROBE_ITEM = "__probe_none__"
PROBE_ARGS = {"shop": "SeedShop", "item": PROBE_ITEM, "count": 1}


def _dig(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return default


def _row(it: dict) -> dict:
    return {
        "id": _dig(it, "id", "itemId", "item_id", "qualifiedItemId"),
        "name": _dig(it, "name", "displayName", "display_name"),
        "price": _dig(it, "price", "unitPrice", "unit_price"),
    }


def main() -> int:
    rec: dict = {
        "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "probe": {"skill": "buy", "args": PROBE_ARGS, "note": "item 名不存在 ⇒ 只会 item_not_sold，不会真买"},
    }
    rec["bridge_json"] = inspect_bridge_json()
    c = BridgeClient(timeout=15.0)
    rec["health"] = c.health()
    obs = c.observe("summary")
    ui = obs.get("ui") if isinstance(obs, dict) else None
    rec["before"] = {
        "location": _dig(obs, "location", "locationName"),
        "player_tile": _dig(obs, "player", "tile"),
        "money": _dig(obs, "player", "money", "Money"),
        "ui": ui,
        "world_seq": _dig(obs, "worldSeq", "world_seq"),
    }

    body = {"skill": "buy", "timeout_ms": 12000, "args": PROBE_ARGS}
    url = c.info.base_url + "/v1/exec"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "X-Auth-Token": c.info.token,
    }
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST"
    )
    t0 = time.time()
    raw, http_status = "", 0
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw, http_status = resp.read().decode("utf-8", errors="replace"), resp.status
    except urllib.error.HTTPError as exc:
        raw, http_status = exc.read().decode("utf-8", errors="replace"), exc.code
    rec["http"] = {
        "url": url,
        "status": http_status,
        "elapsed_ms": round((time.time() - t0) * 1000.0, 1),
        "raw": raw,
    }
    receipt = {}
    try:
        receipt = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        rec["receipt_parse_error"] = True
    rec["receipt"] = receipt

    rows_src = _dig(receipt, "availableItems", "available") or []
    if isinstance(rows_src, dict):
        rows_src = rows_src.get("items") or []
    rows = [_row(it) for it in rows_src if isinstance(it, dict)]
    rec["items"] = rows
    rec["items_count"] = len(rows)
    rec["backpack_hits"] = [
        r for r in rows if "backpack" in f"{r.get('name')} {r.get('id')}".lower()
    ]
    rec["receipt_status"] = _dig(receipt, "status")
    rec["receipt_ok"] = _dig(receipt, "ok")
    rec["receipt_reason"] = _dig(receipt, "reason")

    # 收掉可能被 buy 技能打开的商店菜单（只关 UI，不改变世界）
    try:
        rec["dismiss_modal"] = c.dismiss_modal()
    except BridgeError as exc:
        rec["dismiss_modal_error"] = {"status": exc.status, "reason": str(exc)}
    obs2 = c.observe("summary")
    rec["after"] = {
        "money": _dig(obs2, "player", "money", "Money"),
        "ui": obs2.get("ui") if isinstance(obs2, dict) else None,
        "world_seq": _dig(obs2, "worldSeq", "world_seq"),
        "location": _dig(obs2, "location", "locationName"),
    }

    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"== bridge: modVersion={_dig(rec['bridge_json'].get('parsed') or {}, 'modVersion')} "
          f"port={_dig(rec['bridge_json'].get('parsed') or {}, 'port')} pid={_dig(rec['bridge_json'].get('parsed') or {}, 'pid')}")
    print(f"== health ok={receipt is not None} modVersion={_dig(rec['health'], 'modVersion')}")
    print(f"== HTTP {http_status} {rec['http']['elapsed_ms']}ms  receipt_status={rec['receipt_status']!r} ok={rec['receipt_ok']!r}")
    print(f"== reason: {str(rec['receipt_reason'])[:300]}")
    print(f"== availableItems count={len(rows)}")
    for i, r in enumerate(rows, 1):
        idv = "".join(ch for ch in str(r['id']) if ord(ch) < 128)
        idv = idv.encode('ascii', 'ignore').decode('ascii') or "<non-ascii-qualified-id>"
        name = str(r['name']).encode('ascii', 'replace').decode('ascii')
        print(f"   [{i:02d}] id={idv} price={r['price']} name={name}")
    print(f"== backpack_hits: {json.dumps(rec['backpack_hits'], ensure_ascii=False)}")
    print(f"== before/after money: {rec['before']['money']} -> {rec['after']['money']}  "
          f"ui_modal={_dig(rec['after']['ui'] or {}, 'isModal')}  worldSeq={rec['before']['world_seq']}->{rec['after']['world_seq']}")
    print(f"== wrote {OUT} ({OUT.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
