"""task-44 独立验收的**对抗抽检探针**（deputy-lead）。

不复用 dev-coder 的用例断言，只调用产线 API 并把**原文**打出来：

  A. 回执 ok 但背包没变 / 箱子没变        ⇒ `sell()` 必须判失败
  B. 白名单空 / 非白名单                  ⇒ 拒绝且背包不动（一次请求都不发 / 发一次被拒）
  C. `harvest()` 只摘下来而背包没多        ⇒ 不进白名单（不许凭空生成可卖物）
  D. task-43 两段式：超时回执 ⇒ 先接近再只重试一次；两次都失败 ⇒ 有界停手

跑法：`$env:PYTHONUTF8="1"; & $py scratch/_t44_probe.py`
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))

from tests.test_farmwork import MiniWorld, make_worker  # noqa: E402

RIPE = {"tile": [62, 15], "kind": "dirt", "feature": "HoeDirt", "crop": "24",
        "ripe": True, "watered": True, "standable": True, "actionable": True}


def hdr(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def show(tag: str, **kw) -> None:
    print(f"[{tag}] " + "  ".join(f"{k}={v!r}" for k, v in kw.items()))


def probe_a_ok_receipt_no_change() -> None:
    hdr("A. 回执 ok 但世界一动不动（sell_mode=no_effect）")
    w = MiniWorld()
    w.inventory = [{"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
                    "stack": 1, "isTool": False}]
    w.sell_mode = "no_effect"
    worker = make_worker(w)
    worker.harvested = {"(O)24": 1}
    st = worker.sell(0, whitelist=["(O)24"])
    show("A", ok=st.ok, code=st.code, reason=st.reason,
         shipping_bin=len(w.shipping_bin), inventory_slot0=w.inventory[0]["qualifiedId"],
         harvested_after=worker.harvested, after=st.after)


def probe_b_whitelist() -> None:
    hdr("B1. 白名单空（今天什么都没亲手收获）⇒ 一件不出、一次请求都不发")
    w = MiniWorld()
    w.inventory = [{"slot": 0, "id": "24", "qualifiedId": "(O)24", "name": "Parsnip",
                    "stack": 3, "isTool": False}]
    worker = make_worker(w)
    show("B1", sellable_slots=worker.sellable_slots(w.obs()),
         sell_loot=worker.sell_loot(), sell_calls=w.sell_calls, bin=w.shipping_bin)

    hdr("B2. 非白名单（工具/种子）⇒ Mod 拒绝且背包不动")
    w2 = MiniWorld()
    w2.inventory = [{"slot": 0, "id": "47", "qualifiedId": "(W)47", "name": "Scythe",
                     "stack": 1, "isTool": True}]
    worker2 = make_worker(w2)
    st = worker2.sell(0, whitelist=["(O)24"])
    show("B2", ok=st.ok, code=st.code, reason=st.reason, receipt=st.receipt,
         inventory_slot0=w2.inventory[0]["qualifiedId"], bin=w2.shipping_bin,
         calls=w2.sell_calls)


def probe_c_harvest_without_gain() -> None:
    hdr("C. harvest()：摘下来 + 背包多一件 ⇒ 进白名单；只摘下来 ⇒ 不进")
    w = MiniWorld(records=[dict(RIPE)])
    worker = make_worker(w)
    st = worker.harvest((62, 15))
    show("C1 背包有增长", ok=st.ok, harvested=worker.harvested,
         after=(st.after or {}).get("harvested"), reason=st.reason)

    w2 = MiniWorld(records=[dict(RIPE)])
    w2.harvest_item = None
    worker2 = make_worker(w2)
    st2 = worker2.harvest((62, 15))
    show("C2 背包没增长", ok=st2.ok, harvested=worker2.harvested,
         after=(st2.after or {}).get("harvested"), reason=st2.reason,
         sellable=worker2.sellable_slots(w2.obs()))


def probe_d_two_phase() -> None:
    hdr("D1. task-43 两段式：第 1 跳 timeout(剩余 52 步) ⇒ 先接近、再只重试一次 ⇒ 到达")
    w = MiniWorld()
    w.location_name = "Farm"
    w.move_to_location_script = [
        {"fail": {"status": "timeout",
                  "reason": "第 1 跳失败（timeout）：走向 Farm → FarmHouse 的 warp 源格 "
                            "(64,14) 超时（单跳预算 8000ms，剩余 52 步未走完）。"}},
        {"ok": True},
    ]
    r = make_worker(w).ensure_location("FarmHouse")
    show("D1", ok=r.ok, code=r.code, reason=r.reason,
         timeouts=[c["timeout_ms"] for c in w.move_to_location_calls],
         n_calls=len(w.move_to_location_calls),
         moves=[m.get("tile") for m in w.moves], location=w.location_name)

    hdr("D2. 两次都 timeout ⇒ 有界停手（恰 2 次请求）、原因带源格/剩余步数/现场")
    w2 = MiniWorld()
    w2.location_name = "Farm"
    w2.move_to_location_script = [
        {"fail": {"status": "timeout", "reason": "走向 Farm → FarmHouse 的 warp 源格 (64,14) "
                                                "超时（单跳预算 8000ms，剩余 52 步未走完）。"}},
        {"fail": {"status": "timeout", "reason": "走向 Farm → FarmHouse 的 warp 源格 (64,14) "
                                                "超时（单跳预算 20000ms，剩余 16 步未走完）。"}},
    ]
    r2 = make_worker(w2).ensure_location("FarmHouse")
    show("D2", ok=r2.ok, code=r2.code, inconclusive=r2.inconclusive,
         n_calls=len(w2.move_to_location_calls), reason=r2.reason,
         receipt=bool(r2.receipt))


def main() -> int:
    for fn in (probe_a_ok_receipt_no_change, probe_b_whitelist,
               probe_c_harvest_without_gain, probe_d_two_phase):
        try:
            fn()
        except Exception:
            print(f"!! {fn.__name__} 抛异常：")
            traceback.print_exc()
            return 1
    print("\nALL PROBES DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
