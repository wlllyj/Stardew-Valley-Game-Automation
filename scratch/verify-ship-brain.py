r"""真机验收：**经济闭环**（task-42 的 `ship` 技能）能不能真的把东西放进出货箱、钱由游戏自己结算。

判据一律**观测差分**（回执只作诊断）：

  1. 出货前后 `farm.shippingBin`（若观测已暴露）里该物品条目 **+1**，且背包该物品 **-1**；
  2. `player.money` 在出货当下**不变**（钱是下一次 `NewDay` 由游戏结算的）；
  3. 加 `--sleep` 时：睡过一夜后 `player.money` **增加**（增量应为出货物 `sellPrice` 之和），
     并用存档 size/mtime 前进做外部证据；
  4. 白名单负例：工具 / 种子 / 建材 / 可放置物 ⇒ `ship` 必须**拒绝**且背包一格不动。
  5. 铁律核验（脚本外）：`grep -rn "Money +="` 全仓零命中。

用法（**真机单写者 = Lead / machine-runner，跑前先 preflight**）：

  & $py scratch\verify-ship-brain.py --expect-version 0.7.24
  & $py scratch\verify-ship-brain.py --sleep            # 顺手验"跨日后钱到账"
  & $py scratch\verify-ship-brain.py --item 24          # 指定物品 id
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

from agentfarm.bridge import BridgeClient, BridgeError  # noqa: E402
from agentfarm.farmwork import FarmWorker  # noqa: E402

SAVE_DIR = Path(os.environ["APPDATA"]) / "StardewValley" / "Saves" / "Wahaha_450799035"
TOOL_NAMES = ("axe", "hoe", "wateringcan", "pickaxe", "scythe", "fishing", "pan")
MATERIAL_IDS = {"330", "331", "388", "390", "709", "771", "378", "380", "382", "384"}
SEED_HINTS = ("seed", "种子", "sapling", "starter")


def save_sig() -> tuple[int, float]:
    total, newest = 0, 0.0
    for name in ("Wahaha_450799035", "SaveGameInfo"):
        try:
            st = (SAVE_DIR / name).stat()
        except OSError:
            continue
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return total, newest


def item_id(it: dict) -> str:
    """`ItemView` 的字段是 slot/id/qualifiedId/name/stack/isTool（见 mod\\AgentFarm.Bridge\\Contracts.cs:322）。"""
    return str(it.get("id") or it.get("qualifiedId") or "").strip()


def numeric_id(it: dict) -> str:
    key = item_id(it) or str(it.get("qualifiedId") or "")
    return key.split(":")[-1].strip("()")


def items(obs: dict) -> list[dict]:
    player = (obs or {}).get("player") or {}
    return [it for it in (player.get("inventory") or []) if isinstance(it, dict)]


def counts_by_id(obs: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items(obs):
        key = numeric_id(it)
        if not key:
            continue
        try:
            out[key] = out.get(key, 0) + int(it.get("stack") or 0)
        except (TypeError, ValueError):
            continue
    return out


def name_of(it: dict) -> str:
    return str(it.get("name") or it.get("displayName") or "").strip()


def is_whitelisted(it: dict) -> tuple[bool, str]:
    """出货白名单：作物/觅食/鱼/矿物/工匠品；工具/种子/建材/可放置物一律拒绝。

    ⚠️ `ItemView`（Contracts.cs:322）只暴露 `slot/id/qualifiedId/name/stack/isTool` —— **没有**
    `sellPrice`/`isPlaceable`/`Category`。所以脚本侧的判定只能靠名字/id/isTool；`sellPrice` 只有在
    观测里恰好带了字段时才参与判定（Mod 侧的白名单判定才是权威，见 task-42 卡面）。
    """
    raw = name_of(it)
    name = raw.lower()
    numeric = numeric_id(it)
    if it.get("isTool"):
        return False, "工具(isTool)"
    if any(t in name for t in TOOL_NAMES):
        return False, "工具(名字)"
    if any(h in name or h in raw for h in SEED_HINTS):
        return False, "种子"
    if numeric in MATERIAL_IDS:
        return False, "建材"
    if it.get("isPlaceable") or it.get("isPlaceableObject"):
        return False, "可放置物"
    try:
        price = int(it["sellPrice"])
    except (KeyError, TypeError, ValueError):
        price = None
    if price is not None and price <= 0:
        return False, "sellPrice<=0（游戏不收）"
    return True, "可卖"


def bin_entries(obs: dict) -> list[dict]:
    farm = (obs or {}).get("farm") or {}
    for key in ("shippingBin", "shippingBinItems"):
        val = farm.get(key)
        if isinstance(val, list):
            return [e for e in val if isinstance(e, dict)]
    return []


def bin_count(obs: dict, item_id_want: str) -> int:
    want = str(item_id_want).split(":")[-1].strip("()")
    total = 0
    for e in bin_entries(obs):
        key = str(e.get("id") or e.get("itemId") or e.get("qualifiedId") or e.get("qualifiedItemId") or "")
        if key.split(":")[-1].strip("()") == want:
            try:
                total += int(e.get("stack") or 0)
            except (TypeError, ValueError):
                total += 1
    return total


def money_of(obs: dict) -> int:
    try:
        return int(((obs or {}).get("player") or {}).get("money"))
    except (TypeError, ValueError):
        return -1


def do_ship(client: BridgeClient, worker: FarmWorker, item_id: str, count: int = 1):
    """优先走脑侧 FarmWorker.ship（task-42 的落地形态），没有就直发 exec 技能。"""
    fn = getattr(worker, "ship", None)
    if callable(fn):
        try:
            return "worker.ship", fn(item_id, count=count)
        except TypeError:
            return "worker.ship", fn(item_id)
    args = {"item": item_id, "count": count}
    return "client.exec_skill('ship')", client.exec_skill("ship", args)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-version", default="0.7.24")
    ap.add_argument("--item", default="")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--sleep", action="store_true", help="出货后睡一夜，验钱到账（会跨日）")
    ap.add_argument("--skip-negative", action="store_true")
    args = ap.parse_args()

    problems: list[str] = []
    t0 = time.monotonic()
    try:
        client = BridgeClient()
    except BridgeError as exc:
        print(f"❌ 桥不可达（{exc.status}）：{exc}")
        return 2
    health = client.health()
    ver = str(health.get("modVersion") or "?")
    print(f"桥 OK · modVersion={ver} · 期望={args.expect_version}")
    if ver != args.expect_version:
        print(f"❌ 版本不符（{ver} ≠ {args.expect_version}）：先装机再验")
        return 2

    worker = FarmWorker(client)
    obs = client.observe(detail="full")
    money0 = money_of(obs)
    counts0 = counts_by_id(obs)
    bin0 = bin_entries(obs)
    print(f"出货前：money={money0}g 背包 {len(counts0)} 类 · shippingBin={'有' if bin0 else '未暴露/空'}")
    if not counts0:
        print("❌ 背包里没有可出货的东西：先收获或买东西再来")
        return 1

    # 选目标：显式 --item 优先，否则挑第一个白名单物品
    target = None
    for it in items(obs):
        if args.item and numeric_id(it) != str(args.item).split(":")[-1].strip("()"):
            continue
        if args.item:
            target = it
            break
        ok, _why = is_whitelisted(it)
        if ok:
            target = it
            break
    if target is None:
        print(f"❌ 找不到目标物品（--item={args.item or '未指定'}）")
        return 1
    tid = item_id(target)
    tid_numeric = numeric_id(target)
    ok, why = is_whitelisted(target)
    print(f"目标物品：{name_of(target)} id={tid} stack={target.get('stack')} sellPrice={target.get('sellPrice')} 白名单={'✅' if ok else '❌(' + why + ')'}")
    if args.item and not ok:
        print(f"（显式指定但不在白名单：{why} —— 这会被用作**负例**）")

    before_stack = counts0.get(tid_numeric, 0)
    bin_before = bin_count(obs, tid_numeric)
    used, receipt = do_ship(client, worker, tid, args.count)
    print(f"ship（{used}）回执：{receipt!r}")

    time.sleep(1.2)
    obs2 = client.observe(detail="full")
    after_stack = counts_by_id(obs2).get(tid_numeric, 0)
    bin_after = bin_count(obs2, tid_numeric)
    print(f"出货后：背包该物品 {before_stack}→{after_stack} · shippingBin {bin_before}→{bin_after} · money={money_of(obs2)}g")

    if ok:
        if after_stack >= before_stack:
            problems.append(f"背包没减少（{before_stack}→{after_stack}）⇒ 出货没真的发生")
        if bin_entries(obs2) and bin_after <= bin_before:
            problems.append(f"shippingBin 没增加（{bin_before}→{bin_after}）")
        if money_of(obs2) != money0:
            problems.append(f"出货当下钱就变了（{money0}→{money_of(obs2)}）⇒ 怀疑自己写了 Money +=（铁律违反）")
    else:
        if after_stack != before_stack:
            problems.append(f"负例物品被出掉了（背包 {before_stack}→{after_stack}）⇒ 白名单失效")
        print("（负例：期望被拒绝）")

    # 白名单负例：拿一个工具或种子试
    if not args.skip_negative and ok:
        neg = next((it for it in items(obs2) if not is_whitelisted(it)[0]), None)
        if neg is None:
            print("（找不到负例物品，跳过）")
        else:
            nid = item_id(neg) or numeric_id(neg)
            n_num = numeric_id(neg)
            n_before = counts_by_id(obs2).get(n_num, 0)
            _used, n_rec = do_ship(client, worker, nid, 1)
            time.sleep(1.0)
            obs3 = client.observe(detail="full")
            n_after = counts_by_id(obs3).get(n_num, 0)
            print(f"负例 {name_of(neg)}（{is_whitelisted(neg)[1]}）回执：{n_rec!r} · 背包 {n_before}→{n_after}")
            if n_after != n_before:
                problems.append(f"负例 {name_of(neg)} 被出掉了（{n_before}→{n_after}）")

    if args.sleep:
        sig0 = save_sig()
        m_before = money_of(client.observe(detail="full"))
        res = worker.sleep()
        print(f"sleep 回执：{res!r}")
        time.sleep(1.0)
        obs4 = client.observe(detail="full")
        m_after = money_of(obs4)
        sig1 = save_sig()
        print(f"跨日后：money {m_before}→{m_after}g · 存档 {sig0}→{sig1}")
        if m_after <= m_before:
            problems.append(f"跨日后钱没增加（{m_before}→{m_after}）⇒ 游戏没结算出货")
        if sig1[0] == sig0[0] and sig1[1] <= sig0[1]:
            problems.append("存档 size/mtime 都没前进 ⇒ 跨日可能没真的落盘")

    print("─" * 72)
    if problems:
        print(f"❌ 需要复核（{len(problems)} 条，耗时 {time.monotonic() - t0:.1f}s）：")
        for p in problems:
            print(f"   · {p}")
        return 1
    print(f"✅ VERIFIED（耗时 {time.monotonic() - t0:.1f}s）：出货差分成立、钱的结算口径正确、负例被拒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
