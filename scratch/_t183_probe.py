r"""task-183 独立对抗验收探针：task-181（脑侧四选一）+ task-182（Mod acted 跨观测证据）。

只写 `scratch/`；不读作者探针（作者的 `scratch/_t181_mutate.py` / `_t182_mutate.py` 已删）。
真机重放数据来自 `docs/_run10-harvest-verify-0734.md`（task-177，machine-runner `f851423`）：
  * 样本格 `(60,29)`：再生作物（`regrowsAfterHarvest=true`）收成后 crop 仍在、
    `ready true→false`、`farm.readyCrops 102→101`、背包 `(O)270 +1`、`worldSeq 60→61`；
  * 对照格 `(60,28)`：Scythe 一镰刀连带清 4 格、`(O)262 +4`、`(O)178 +2`、`readyCrops 101→97`；
  * 背包"满"= `inventory[]` **行数**占满容量（`inventoryCount` 是容量字段，腾格后仍读 12）。

用法：`$env:T183_ROOT = <树>` 可切树；输出写到 stdout（调用方 tee 到 `scratch/_t183_probe_out.txt`）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("T183_ROOT") or Path(__file__).resolve().parents[1])
for _p in (ROOT, ROOT / "brain", ROOT / "tests"):
    sys.path.insert(0, str(_p))

import test_farmwork as TF                      # noqa: E402
import agentfarm.farmwork as FW                 # noqa: E402

PASS = 0
FAIL = 0
FINDINGS: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {tag}")
    else:
        FAIL += 1
        print(f"  FAIL {tag}  :: {detail}")


def finding(tag: str, reproduced: bool, detail: str = "") -> None:
    if reproduced:
        FINDINGS.append(tag)
        print(f"  发现 {tag}  :: {detail}")
    else:
        print(f"  （未复现）{tag}  :: {detail}")


class World(TF.MiniWorld):
    """加一个 `hidden`：**观测里**看不见这些格，但世界真相（`records`）不变。

    用来复刻"动作后的观测缺了这一格"（窗口截断 / 快照丢了），看脑侧会不会把**缺失**当成功。
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.hidden: set[tuple[int, int]] = set()
        self.tool_calls: list[tuple] = []

    def obs(self) -> dict:
        o = super().obs()
        if self.hidden:
            o["location"]["tiles"] = [r for r in o["location"]["tiles"]
                                      if tuple(r["tile"]) not in self.hidden]
        return o


def crop(tile=(60, 29), **kw) -> dict:
    rec = {"tile": list(tile), "kind": "dirt", "feature": "HoeDirt", "crop": "270",
           "ripe": True, "ready": True, "readySource": "game", "harvestMethod": "Grab",
           "regrowsAfterHarvest": True, "watered": True, "standable": True, "actionable": True}
    rec.update(kw)
    return rec


def mk(w: World, bridge_cls=TF.MiniBridge) -> FW.FarmWorker:
    return TF.FarmWorker(bridge_cls(w), log=lambda _s: None, pause=lambda _s: None)


def farm(crops=102, ready=102) -> dict:
    return {"loaded": True, "complete": True, "crops": int(crops), "readyCrops": int(ready)}


def item(qid: str, stack: int, slot: int = 9, name: str = "Item", is_tool: bool = False) -> dict:
    return {"slot": int(slot), "id": qid.split(")")[-1], "qualifiedId": qid,
            "name": name, "stack": int(stack), "isTool": bool(is_tool)}


# ═══════════════════════════════ B：真机重放 ═══════════════════════════════
def case_b1() -> None:
    """(60,29) 再生作物重放：四选一里 b/c/d 三条同时命中 ⇒ 必须 ok。"""
    print("== B1 (60,29) 再生作物重放 ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            for r in self.w.records:
                if tuple(r["tile"]) == tuple(tile):
                    r["ready"] = False                     # 再生作物：crop 留着、阶段重置
                    r["readySource"] = "game"
            self.w.inventory.append(item("(O)270", 1, 9, "Corn"))
            self.w.farm["readyCrops"] = 101
            return {"ok": True, "status": "ok", "acted": False,
                    "reason": "再生作物收成（Mod 误报 acted=false）"}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    check("B1 判成功（旧判据在这里系统性假阴）", st.ok is True, st.reason)
    check("B1 reason 写明 ready 翻转", "ready true→False" in st.reason, st.reason)
    check("B1 reason 写明 loot 与 readyCrops 下降",
          "进背包" in st.reason and "readyCrops 102→101" in st.reason, st.reason)
    check("B1 Mod 的 acted=False 只作线索（不进成功文案）", "没有真的动手" not in st.reason, st.reason)
    check("B1 白名单逐 qid = (O)270×1", worker.harvested == {"(O)270": 1}, str(worker.harvested))
    check("B1 affected_tiles 指出 (60,29)", (st.after or {}).get("affected_tiles") == [[60, 29]],
          str(st.after))
    check("B1 世界真相：crop 仍在（再生作物）", bool(w.records[0].get("crop")), str(w.records[0]))


def case_b2() -> None:
    """(60,28) 对照格重放：Scythe 一镰刀连清 4 格、两个 qid、逐格 loot 记账。"""
    print("== B2 (60,28) 对照格：一镰刀多格 ==")
    tiles = [(60, 28), (61, 28), (60, 29), (61, 29)]
    recs = [crop(t, harvestMethod="Scythe", regrowsAfterHarvest=False, crop="262")
            for t in tiles]
    w = World(records=recs, inventory=[item("(O)388", 99)])
    w.farm = farm(crops=102, ready=102)

    class B(TF.MiniBridge):
        def use_tool(self, tile, *, tool=None, timeout_ms=None):
            self.w.tool_calls.append((tuple(tile), tool))
            for r in self.w.records:
                r.pop("crop", None)
                r.pop("ready", None)
            self.w.inventory.append(item("(O)262", 4, 6, "Wheat"))
            self.w.inventory.append(item("(O)178", 2, 7, "Hay"))
            self.w.farm["readyCrops"] = 98
            return {"ok": True, "status": "ok", "acted": True}

        def interact(self, tile=None, *, timeout_ms=None):
            raise AssertionError("Scythe 类作物绝不许走 interact")

    worker = mk(w, B)
    st = worker.harvest((60, 28))
    check("B2 判成功", st.ok is True, st.reason)
    check("B2 走的是 use_tool（工具路径）",
          [c[1] for c in w.tool_calls] == ["scythe"], str(w.tool_calls))
    check("B2 loot 逐 qid：(O)262×4 + (O)178×2",
          (st.after or {}).get("loot") == {"(O)262": 4, "(O)178": 2}, str(st.after))
    check("B2 白名单两件都在",
          worker.harvested == {"(O)262": 4, "(O)178": 2}, str(worker.harvested))
    check("B2 affected_tiles 覆盖 4 格",
          sorted(map(tuple, (st.after or {}).get("affected_tiles") or [])) == sorted(tiles),
          str((st.after or {}).get("affected_tiles")))


def case_b3() -> None:
    """四条判据全不成立：回执自称成功也必须 failed。"""
    print("== B3 四条全不成立 ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            return {"ok": True, "status": "ok", "acted": True, "reason": "回执说收了"}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    check("B3 failed", st.code == "failed" and st.ok is False, f"{st.code} {st.reason}")
    check("B3 文案点名四条判据", "四条判据全不成立" in st.reason, st.reason)
    check("B3 白名单必须空", worker.harvested == {}, str(worker.harvested))
    check("B3 世界没变 ⇒ crop 还在", bool(w.records[0].get("crop")), str(w.records[0]))


# ═══════════════════════════════ C：作弊通道 ═══════════════════════════════
def case_c1() -> None:
    """通道 ①：动作后**观测缺了这一格**（世界真相不变）⇒ 会不会被当成功。"""
    print("== C1 后观测缺失（窗口/快照丢格）==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            self.w.hidden.add((int(tile[0]), int(tile[1])))      # 只从**观测**里抹掉
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    finding("F1 后观测缺格 ⇒ 被当收获成功",
            st.ok is True and bool(w.records[0].get("crop")),
            f"ok={st.ok} code={st.code} 世界 crop 仍在={bool(w.records[0].get('crop'))} "
            f"reason={st.reason}")
    check("C1 世界没变时白名单不应凭空生成（当前实现的副作用）", worker.harvested == {},
          str(worker.harvested))


def case_c2() -> None:
    """通道 ②：`crop` 为 null 但 `ready` 仍 true（自相矛盾观测）⇒ 会不会被判成功。"""
    print("== C2 crop=null 但 ready=true ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            for r in self.w.records:
                r["crop"] = None                                  # 矛盾：没作物却仍可收
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    finding("F2 crop=null + ready=true ⇒ 被判成功（矛盾观测被采信）",
            st.ok is True, f"ok={st.ok} code={st.code} reason={st.reason}")


def case_c3() -> None:
    """通道 ③：背包 +N 来自**别的**来源（不是这次收获）⇒ 假成功 + 污染出货白名单。"""
    print("== C3 无关物品进背包 ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            self.w.inventory.append(item("(O)128", 1, 8, "Sardine"))   # 与收获无关
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    finding("F3 无关物品进背包 ⇒ 判成功并把该 qid 记进收获白名单",
            st.ok is True and worker.harvested == {"(O)128": 1},
            f"ok={st.ok} 白名单={worker.harvested} reason={st.reason}")
    # 下游后果：sell_loot 会把这条白名单里的东西真的出掉
    slots = worker.sellable_slots(w.obs())
    sold = worker.sell_loot()
    check("C3 下游：sell_loot 真的会出掉那件无关物品（白名单被污染）",
          bool(slots) and bool(sold) and any("(O)128" in c["whitelist"] for c in w.sell_calls),
          f"slots={slots} sell_calls={w.sell_calls}")


def case_c4() -> None:
    """通道 ④：背包"满"必须数 `inventory[]` 行数（容量字段不算）。"""
    print("== C4 背包满 = 行数口径 ==")
    rows12 = [item("(O)388", 99, i, "Wood") for i in range(12)]
    w = World(records=[crop()], inventory=[dict(r) for r in rows12], inventory_capacity=12)
    w.farm = farm()
    worker = mk(w)
    st = worker.harvest((60, 29))
    check("C4 12 行占满 12 槽 ⇒ 判满且**不发请求**",
          st.code == "failed" and "背包满" in st.reason and w.harvests == [],
          f"{st.code} {st.reason} harvests={w.harvests}")
    check("C4 判满文案点明容量字段不能用来判满",
          "inventoryCount" in st.reason and "容量" in st.reason, st.reason)

    # 正对照：11 行（腾出一格）+ 世界真收成
    w2 = World(records=[crop()], inventory=[dict(r) for r in rows12[:11]], inventory_capacity=12)
    w2.farm = farm()
    w2.harvest_item = item("(O)270", 1, 11, "Corn")

    class B2(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            self.w.harvest((int(tile[0]), int(tile[1])))
            self.w.farm["readyCrops"] = 101
            return {"ok": True, "status": "ok", "acted": True}

    worker2 = mk(w2, B2)
    st2 = worker2.harvest((60, 29))
    check("C4 对照：11 行（有空格）⇒ 真发请求并成功", st2.ok is True and w2.harvests,
          f"{st2.code} {st2.reason} harvests={w2.harvests}")

    # INFO：容量字段缺失 ⇒ 判满不触发（按"不知道"处理）
    w3 = World(records=[crop()], inventory=[dict(r) for r in rows12])
    w3.farm = farm()
    worker3 = mk(w3)
    st3 = worker3.harvest((60, 29))
    check("C4 INFO：容量字段缺失 ⇒ 不判满（不知道 ≠ 满），请求照发",
          w3.harvests != [] and st3.ok is True, f"{st3.code} harvests={w3.harvests}")


def case_c5() -> None:
    """通道 ⑤：一镰刀多格但只掉 1 个 qid ⇒ loot 1 条、affected 4 格，两边都要对。"""
    print("== C5 多格 / 单 qid ==")
    tiles = [(60, 28), (61, 28), (60, 29), (61, 29)]
    recs = [crop(t, harvestMethod="Scythe", regrowsAfterHarvest=False, crop="262") for t in tiles]
    w = World(records=recs, inventory=[item("(O)388", 99)])
    w.farm = farm(crops=102, ready=102)

    class B(TF.MiniBridge):
        def use_tool(self, tile, *, tool=None, timeout_ms=None):
            for r in self.w.records:
                r.pop("crop", None)
                r.pop("ready", None)
            self.w.inventory.append(item("(O)262", 4, 6, "Wheat"))
            self.w.farm["readyCrops"] = 98
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 28))
    check("C5 loot 只 1 个 qid 也照实记", (st.after or {}).get("loot") == {"(O)262": 4},
          str(st.after))
    check("C5 affected_tiles 仍是 4 格（不许因为 loot 只有 1 条就缩成 1 格）",
          len((st.after or {}).get("affected_tiles") or []) == 4, str(st.after))


def case_c6() -> None:
    """通道 ⑥：只有 `farm.readyCrops` 下降（格子上什么都没变）⇒ 算成功但不许污染白名单。"""
    print("== C6 只有 farm 级计数下降 ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = farm(crops=2, ready=2)

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            self.w.farm["readyCrops"] = 1
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    check("C6 判成功且文案写明 readyCrops 下降", st.ok is True and "readyCrops 2→1" in st.reason,
          st.reason)
    check("C6 没进背包 ⇒ 白名单必须空", worker.harvested == {}, str(worker.harvested))
    check("C6 affected_tiles 如实 unknown（格子级没变）",
          (st.after or {}).get("affected_tiles") == "unknown", str(st.after))


def case_c7() -> None:
    """通道 ⑦：旧路径（非再生作物 crop 消失）不许回归。"""
    print("== C7 旧路径回归 ==")
    w = World(records=[crop(regrowsAfterHarvest=False)], inventory=[item("(O)388", 99)])
    w.farm = farm()
    w.harvest_item = item("(O)270", 1, 9, "Corn")
    worker = mk(w)
    st = worker.harvest((60, 29))
    check("C7 crop 消失 ⇒ 成功", st.ok is True, st.reason)
    check("C7 文案走 crop 消失那条，不误标再生作物",
          "crop 已消失" in st.reason and "再生作物" not in st.reason, st.reason)
    check("C7 白名单 (O)270×1", worker.harvested == {"(O)270": 1}, str(worker.harvested))


def case_c8() -> None:
    """通道 ⑧：只有 `readySource` 标签变了（`ready` 仍 true、没进背包）⇒ 会不会被当成功。"""
    print("== C8 仅 readySource 变化 ==")
    w = World(records=[crop(ready=True, readySource="game")], inventory=[item("(O)388", 99)])
    w.farm = farm()

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            for r in self.w.records:
                r["readySource"] = "fields"      # ready 仍 true、世界没收获
            return {"ok": True, "status": "ok", "acted": True}

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    finding("F4 仅 readySource 标签变化 ⇒ 判成功（该格仍可收）",
            st.ok is True, f"ok={st.ok} code={st.code} reason={st.reason}")


def case_c9() -> None:
    """通道 ⑨：`farm.readyCrops` 缺失/类型不对 ⇒ 判不了（不许当 0 或下降）。"""
    print("== C9 readyCrops 判不了 ==")
    w = World(records=[crop()], inventory=[item("(O)388", 99)])
    w.farm = {}                                   # 没有 readyCrops

    class B(TF.MiniBridge):
        def interact(self, tile=None, *, timeout_ms=None):
            return {"ok": True, "status": "ok", "acted": True}   # 世界没变、无 loot

    worker = mk(w, B)
    st = worker.harvest((60, 29))
    check("C9 缺 readyCrops ⇒ 该通道不构成证据，其余三条也不成立 ⇒ failed",
          st.code == "failed", f"{st.code} {st.reason}")
    finding("F5 readyCrops 判不了时，失败文案仍断言「farm.readyCrops 没下降」",
            st.code == "failed" and "readyCrops 没下降" in st.reason, st.reason)


# ═══════════════════════════════ D：Mod 侧 ═══════════════════════════════
def case_d() -> None:
    print("== D Mod 侧（acted 跨观测证据 + ClumpRules 行为化）==")
    mod = ROOT / "mod" / "AgentFarm.Bridge"
    skills = (mod / "Skills.cs").read_text(encoding="utf-8")
    rules = (mod / "ClumpRules.cs").read_text(encoding="utf-8")
    meta = (mod / "CropMeta.cs").read_text(encoding="utf-8")
    contracts = (mod / "Contracts.cs").read_text(encoding="utf-8")

    order = ["if (tileChanged) evidence = \"tile\";",
             "else if (readyFlipped || readySourceChanged) evidence = \"ready\";",
             "else if (readyDropped) evidence = \"readyCrops\";",
             "else if (inventoryGrew) evidence = \"inventory\";"]
    idx = [skills.find(x) for x in order]
    check("D1 证据优先级 tile > ready > readyCrops > inventory（格子级优先、全局面垫底）",
          all(i >= 0 for i in idx) and idx == sorted(idx), str(idx))
    check("D2 acted 只由证据决定（不再只看 checkAction 返回值）",
          "bool acted = err == null && evidence != null;" in skills
          and "Ok = err == null && handled" not in skills, "")
    check("D3 actedEvidence 落盘 + 契约声明",
          "ActedEvidence = evidence" in skills
          and '[JsonPropertyName("actedEvidence")] public string ActedEvidence' in contracts, "")
    check("D4 readyCrops 读不到 = -1（不是 0）+ 判据要求 >= 0",
          "return -1;" in skills and "readyCropsBefore >= 0 && readyCropsAfter >= 0" in skills, "")
    check("D5 ClumpRules 零游戏类型（代码行）+ CropMeta 只有一条委托 return",
          all(b not in "\n".join(l for l in rules.splitlines() if not l.strip().startswith("//"))
              for b in ("HoeDirt", "Netcode", "StardewValley"))
          and "return ClumpRules.Ready(gameSaid," in meta, "")
    check("D6 NIT-1：forageCrop 且 whichForageCrop 读不到 ⇒ 判不了",
          "if (forageCrop.Value && whichForageCrop == null) return (null, null);" in rules, "")

    proj = ROOT / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"
    proc = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    check("D7 C# 行为自检工程 exit 0 且 OK（GAP-1 的 18 条断言）",
          proc.returncode == 0 and "OK" in proc.stdout,
          f"rc={proc.returncode} out={proc.stdout.strip()[-200:]} err={proc.stderr.strip()[-200:]}")


def main() -> int:
    print(f"task-183 探针 · 树 = {ROOT}")
    for fn in (case_b1, case_b2, case_b3, case_c1, case_c2, case_c3, case_c4, case_c5,
               case_c6, case_c7, case_c8, case_c9, case_d):
        try:
            fn()
        except Exception as exc:                    # noqa: BLE001
            check(f"{fn.__name__} 未抛异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n== 汇总：PASS={PASS} FAIL={FAIL}；复现发现 {len(FINDINGS)} 条 ==")
    for f in FINDINGS:
        print(f"   - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
