r"""真机验收：**经济闭环**（task-42 的 `sell` 技能）能不能真的把东西放进出货箱、钱由游戏自己结算。

与 `docs\_il-sell-path.md` 的定案对齐：Mod 直调 **public** 的 `Farm.shipItem(item, who)`，钱由**下一次
`NewDay`** 由游戏自己结算（`player.Money = player.Money + total`）。判据一律**观测差分**：

  1. 出货前后：该**槽位**真的空了 / 该 `qualifiedId` 总数下降；`shippingBin.items` 增加；
  2. `player.money` 在出货当下**不变**（钱要等跨日；当下就变 ⇒ 怀疑自己写了 `Money +=`，铁律违反）；
  3. `--sleep`：睡过一夜后 `player.money` **增加**，且存档 size/mtime 前进（外部证据）；
  4. 白名单负例：工具 / 种子 / 建材 ⇒ `sell` 必须**拒绝**且背包一格不动；
  5. 脚本外铁律核验：`grep -rn "Money +="` 只允许出现在 docs/注释里。

关键实现事实（`brain\agentfarm\farmwork.py:1288` + `brain\agentfarm\bridge.py:809`）：
`FarmWorker.sell(slot, *, whitelist=None, timeout_ms=8000)` → `BridgeClient.sell(slot, ...)` →
`exec_skill("sell", {"slot": slot})`；**必须给槽位**，因为 Mod 取 `Game1.player.Items[slot]` 那个实例
（游戏自己的 `removeItemFromInventory` 用引用相等找物品）。**脑侧 `whitelist` 默认取 `self.harvested`**，
手工探针必须显式传 `whitelist=[qid]`，否则默认空表会让 Mod 一律拒绝。

用法（真机单写者 = Lead / machine-runner，跑前先 `tools\preflight.py`）：

  & $py scratch\verify-sell-brain.py --expect-version 0.7.24
  & $py scratch\verify-sell-brain.py --sleep           # 顺手验"跨日后钱到账"
  & $py scratch\verify-sell-brain.py --slot 5          # 指定背包槽位
"""

from __future__ import annotations

import argparse
import os
import re
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


_ID_PREFIX = re.compile(r"^\([^)]*\)")


def norm_id(value: str) -> str:
    """把 `(O)24` / `(T)Axe` / `24` / `(BC)390` 一律规范成裸 id（`24` / `Axe`）。"""
    s = str(value or "").strip()
    s = _ID_PREFIX.sub("", s)
    return s.split(":")[-1].strip()


def item_id(it: dict) -> str:
    """`ItemView` 只有 slot/id/qualifiedId/name/stack/isTool（`mod/AgentFarm.Bridge/Contracts.cs:322`）。"""
    return str(it.get("id") or it.get("qualifiedId") or "").strip()


def numeric_id(it: dict) -> str:
    return norm_id(item_id(it))


def slot_of(it: dict) -> int:
    try:
        return int(it.get("slot"))
    except (TypeError, ValueError):
        return -1


def items(obs: dict) -> list[dict]:
    player = (obs or {}).get("player") or {}
    return [it for it in (player.get("inventory") or []) if isinstance(it, dict)]


def counts_by_qid(obs: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items(obs):
        key = str(it.get("qualifiedId") or item_id(it)).strip()
        if not key:
            continue
        try:
            out[key] = out.get(key, 0) + int(it.get("stack") or 0)
        except (TypeError, ValueError):
            continue
    return out


def stack_at_slot(obs: dict, slot: int) -> int:
    for it in items(obs):
        if slot_of(it) == int(slot):
            try:
                return int(it.get("stack") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def name_of(it: dict) -> str:
    return str(it.get("name") or "").strip()


def is_whitelisted(it: dict) -> tuple[bool, str]:
    """出货白名单：作物/觅食/鱼/矿物/工匠品；工具/种子/建材一律拒绝。

    ⚠️ `ItemView` 不暴露 `sellPrice`/`Category`/`isPlaceable`，脚本侧只能靠 `isTool` + 名字 + id；
    **权威判定在 Mod 侧**（task-42 卡面）。这里宽松判"可卖"，只用于挑目标；负例用工具/种子/建材。
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
    return True, "可卖"


def bin_entries(obs: dict) -> list[dict]:
    """观测里出货箱的两种可能形态：根级 `shippingBin{count,items}`（0.7.24 实现）或 `farm.shippingBin[]`。"""
    top = (obs or {}).get("shippingBin")
    if isinstance(top, dict) and isinstance(top.get("items"), list):
        return [e for e in top["items"] if isinstance(e, dict)]
    if isinstance(top, list):
        return [e for e in top if isinstance(e, dict)]
    farm = (obs or {}).get("farm") or {}
    for container in (farm.get("shippingBin"), farm.get("shippingBinItems")):
        if isinstance(container, dict) and isinstance(container.get("items"), list):
            return [e for e in container["items"] if isinstance(e, dict)]
        if isinstance(container, list):
            return [e for e in container if isinstance(e, dict)]
    return []


def bin_count(obs: dict, want_id: str) -> int:
    want = norm_id(want_id)
    total = 0
    for e in bin_entries(obs):
        key = str(e.get("id") or e.get("itemId") or e.get("qualifiedId") or e.get("qualifiedItemId") or "")
        if norm_id(key) == want:
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


def do_sell(client: BridgeClient, worker: FarmWorker, slot: int, qid: str):
    """优先走脑侧 `FarmWorker.sell`（生产路径），退回 `BridgeClient.sell`，再退回裸 exec。

    `whitelist=[qid]` 必须显式传：脑侧默认取 `self.harvested`，手工探针下那是空表 ⇒ Mod 会一律拒绝。
    """
    fn = getattr(worker, "sell", None)
    if callable(fn):
        try:
            return "worker.sell", fn(int(slot), whitelist=[qid])
        except TypeError:
            return "worker.sell", fn(int(slot))
    cf = getattr(client, "sell", None)
    if callable(cf):
        return "client.sell", cf(int(slot), whitelist=[qid])
    return "client.exec_skill('sell')", client.exec_skill("sell", {"slot": int(slot)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-version", default="0.7.24")
    ap.add_argument("--slot", type=int, default=-1, help="指定背包槽位；默认自动挑一个白名单物品")
    ap.add_argument("--sleep", action="store_true", help="出货后睡一夜，验跨日结算（会跨日）")
    ap.add_argument("--skip-negative", action="store_true")
    args = ap.parse_args()

    problems: list[str] = []
    t0 = time.monotonic()
    try:
        client = BridgeClient()
    except BridgeError as exc:
        print(f"❌ 桥不可达（{getattr(exc, 'status', '?')}）：{exc}")
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
    print(f"出货前：money={money0}g · 背包 {len(items(obs))} 格 · 出货箱 {len(bin_entries(obs))} 件")
    if not items(obs):
        print("❌ 背包是空的：先收获/买东西再来")
        return 1

    target = None
    if args.slot >= 0:
        target = next((it for it in items(obs) if slot_of(it) == args.slot), None)
        if target is None:
            print(f"❌ 槽位 {args.slot} 上没有物品")
            return 1
    else:
        for it in items(obs):
            if is_whitelisted(it)[0] and stack_at_slot(obs, slot_of(it)) > 0:
                target = it
                break
    if target is None:
        print("❌ 找不到可出货的目标（背包里全是工具/种子/建材）")
        return 1

    slot = slot_of(target)
    qid = str(target.get("qualifiedId") or item_id(target))
    ok, why = is_whitelisted(target)
    print(f"目标：槽位 {slot} · {name_of(target)} qid={qid} stack={stack_at_slot(obs, slot)} · 脚本白名单={'✅' if ok else '❌(' + why + ')'}")

    before_total = counts_by_qid(obs).get(qid, 0)
    bin_before = bin_count(obs, qid)
    used, receipt = do_sell(client, worker, slot, qid)
    print(f"sell（{used}）回执：{receipt!r}")

    time.sleep(1.2)
    obs2 = client.observe(detail="full")
    after_total = counts_by_qid(obs2).get(qid, 0)
    bin_after = bin_count(obs2, qid)
    print(f"出货后：qid 总数 {before_total}→{after_total} · 槽位 {slot} stack={stack_at_slot(obs2, slot)} · 出货箱 {bin_before}→{bin_after} · money={money_of(obs2)}g")

    if ok:
        if after_total >= before_total:
            problems.append(f"背包该 qid 总数没减少（{before_total}→{after_total}）⇒ 出货没真的发生")
        if bin_after <= bin_before:
            problems.append(f"出货箱没增加（{bin_before}→{bin_after}）")
        if money_of(obs2) != money0:
            problems.append(f"出货当下钱就变了（{money0}→{money_of(obs2)}）⇒ 怀疑自己写了 Money +=（铁律违反）")
    else:
        print("（显式指定的目标不在脚本白名单里 ⇒ 当负例看）")
        if after_total != before_total:
            problems.append(f"负例被出掉了（{before_total}→{after_total}）")

    # 白名单负例：工具/种子/建材，脑侧白名单放行该 qid，看 Mod 是否仍拒绝
    if not args.skip_negative and ok:
        neg = next((it for it in items(obs2) if not is_whitelisted(it)[0] and stack_at_slot(obs2, slot_of(it)) > 0), None)
        if neg is None:
            print("（背包里找不到工具/种子/建材做负例，跳过）")
        else:
            n_slot = slot_of(neg)
            n_qid = str(neg.get("qualifiedId") or item_id(neg))
            n_before = stack_at_slot(obs2, n_slot)
            _used, n_rec = do_sell(client, worker, n_slot, n_qid)
            time.sleep(1.0)
            obs3 = client.observe(detail="full")
            n_after = stack_at_slot(obs3, n_slot)
            print(f"负例：槽位 {n_slot} {name_of(neg)}（{is_whitelisted(neg)[1]}）回执：{n_rec!r} · stack {n_before}→{n_after}")
            if n_after != n_before:
                problems.append(f"负例 {name_of(neg)} 被出掉了（{n_before}→{n_after}）⇒ 白名单失效")

    if args.sleep:
        sig0 = save_sig()
        m_before = money_of(client.observe(detail="full"))
        res = worker.sleep()
        print(f"sleep 回执：{res!r}")
        time.sleep(1.0)
        obs4 = client.observe(detail="full")
        m_after = money_of(obs4)
        sig1 = save_sig()
        print(f"跨日后：money {m_before}→{m_after}g · 存档 {sig0[0]}/{sig0[1]:.1f} → {sig1[0]}/{sig1[1]:.1f}")
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
